"""Personal reminders, recurring checklists, estimates, and schedule previews."""
import asyncio
import calendar
import hashlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
import discord
from chore_timing import WEEKDAYS, SCHEDULED, day_badge


def install(ns, ui, w, lock):
    db, timing, bot = ns['db'], ui.timing, ns['bot']
    db.executescript('''
    CREATE TABLE IF NOT EXISTS chore_help(id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL,cycle TEXT NOT NULL,reporter TEXT NOT NULL,kind TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL,resolved_at TEXT,resolved_by TEXT,resolution TEXT);
    CREATE INDEX IF NOT EXISTS chore_help_active ON chore_help(quest_id,cycle,resolved_at);
    CREATE TABLE IF NOT EXISTS chore_copies(submission_key TEXT PRIMARY KEY,source_id INTEGER NOT NULL,new_id INTEGER NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chore_plans(quest_id INTEGER PRIMARY KEY,minutes INTEGER,steps TEXT NOT NULL DEFAULT '[]',revision INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS chore_checklist_revisions(quest_id INTEGER PRIMARY KEY,revision INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS checklist_checks(quest_id INTEGER NOT NULL,cycle TEXT NOT NULL,item INTEGER NOT NULL,checked_by TEXT NOT NULL,PRIMARY KEY(quest_id,cycle,item));
    CREATE TABLE IF NOT EXISTS reminder_settings(user_id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 0,times TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS reminder_deliveries(user_id TEXT NOT NULL,slot TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(user_id,slot));
    ''')
    db.commit()
    def chore(qid):
        return db.execute('SELECT id,name,frequency,points,assigned_to,completed,last_completed,reset_after FROM quests WHERE id=?',(qid,)).fetchone()
    def plan(qid):
        row=db.execute('SELECT minutes,steps,revision FROM chore_plans WHERE quest_id=?',(qid,)).fetchone()
        return row if row else (None,'[]',0)
    def steps(qid):return json.loads(plan(qid)[1])
    def cycle(qid):
        q=chore(qid)
        if not q:return ''
        state=timing.state(qid)
        revision=db.execute('SELECT revision FROM chore_checklist_revisions WHERE quest_id=?',(qid,)).fetchone()
        # Unfinished Keep-overdue work retains progress; completion or Skip creates a fresh cycle.
        raw=json.dumps([q[2],q[6],q[7],state,revision,steps(qid),timing.policy_state(qid) if timing.policy(qid)=='skip' else None])
        return hashlib.sha256(raw.encode()).hexdigest()
    def checked(qid):
        return {r[0] for r in db.execute('SELECT item FROM checklist_checks WHERE quest_id=? AND cycle=?',(qid,cycle(qid)))}
    def complete(qid):return len(checked(qid))==len(steps(qid))
    def summary(qid):
        minutes,_,_=plan(qid);items=steps(qid)
        return (' · ~'+str(minutes)+' min' if minutes else '')+(f' · Checklist {len(checked(qid))}/{len(items)}' if items else '')
    def history_state(qid):
        return dict(plan=plan(qid),cycle=cycle(qid),checked=sorted(checked(qid))) if plan(qid)[2] else None
    def save_plan(qid,minutes,text,expected):
        q=chore(qid)
        if not q or ui.is_archived(qid) or plan(qid)!=expected:return 'This chore or checklist changed. Reopen its settings.'
        try:
            value=int(minutes) if str(minutes).strip() else None
            if value==0:value=None
            if value is not None and not 1<=value<=1440:raise ValueError
        except (TypeError,ValueError):return 'Estimate must be a whole number from 1 to 1440 minutes, or blank to clear it.'
        items=[line.strip() for line in text.splitlines() if line.strip()]
        if len(items)>12 or any(len(item)>80 for item in items):return 'Use at most 12 checklist steps, each up to 80 characters.'
        if len(set(i.casefold() for i in items))!=len(items):return 'Give each checklist step different wording.'
        with db:
            db.execute('INSERT OR REPLACE INTO chore_plans VALUES(?,?,?,?)',(qid,value,json.dumps(items),expected[2]+1))
            if items!=json.loads(expected[1]):
                db.execute('INSERT INTO chore_checklist_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))
        return 'Estimate and checklist saved. Changed checklist wording starts fresh progress for this occurrence; estimates do not award points.'
    class PlanModal(discord.ui.Modal):
        def __init__(self,owner,qid,back):
            super().__init__(title='Estimate and checklist')
            self.owner,self.qid,self.back,self.expected=owner,qid,back,plan(qid)
            self.minutes=discord.ui.TextInput(label='Estimated minutes (blank clears)',default=str(self.expected[0] or ''),required=False,max_length=4)
            self.items=discord.ui.TextInput(label='Checklist: one step per line (blank clears)',style=discord.TextStyle.paragraph,default='\n'.join(json.loads(self.expected[1])),required=False,max_length=1000)
            self.add_item(self.minutes);self.add_item(self.items)
        async def on_submit(self,i):
            if not await w.View(self.owner).interaction_check(i):return
            await i.response.defer()
            async with lock:text=save_plan(self.qid,self.minutes.value,self.items.value,self.expected)
            await w.present(i,self.back(),text)
    class Checklist(w.View):
        def __init__(self,owner,qid,guild=None,back=None):
            super().__init__(owner)
            ns['reset_due_quests']()
            q=chore(qid);items=steps(qid);done=checked(qid)
            back=back or (lambda:w.Card(owner,qid,guild=guild))
            self.recovery_context={'screen':'checklist','qid':qid,'parent':w.recovery.bookmark(back())}
            self.expected=(ui.snapshot(qid),plan(qid),cycle(qid),sorted(done))
            self.embed=discord.Embed(title='Checklist · '+w.clean(q[1],100) if q else 'Chore unavailable',description=f'**{len(done)}/{len(items)} steps complete** · Check steps below, then press Done. Points are awarded once; progress stays with this occurrence.',color=0x6B9B77)
            for idx,item in enumerate(items):self.embed.add_field(name=('☑ ' if idx in done else '☐ ')+w.clean(item,80),value='Checked' if idx in done else 'Not checked',inline=False)
            uid,_=w.ownership(qid)
            if q and not ui.is_archived(qid) and not q[5] and timing.ready(qid) and uid==str(owner) and ui.available(owner) and items:
                picker=discord.ui.Select(placeholder='Select all finished steps; unselect to undo',min_values=0,max_values=len(items),row=0,options=[discord.SelectOption(label=item,value=str(idx),default=idx in done) for idx,item in enumerate(items)])
                async def change(i):
                    if not await self.interaction_check(i):return
                    await i.response.defer()
                    async with lock:
                        ns['reset_due_quests']()
                        current=(ui.snapshot(qid),plan(qid),cycle(qid),sorted(checked(qid)))
                        if current!=self.expected or w.ownership(qid)[0]!=str(owner) or not ui.available(owner) or not timing.ready(qid):text='This occurrence or checklist changed. Review its current progress.'
                        else:
                            values={int(v) for v in picker.values}
                            if not values.issubset(set(range(len(items)))):text='Choose valid checklist steps.'
                            else:
                                with db:
                                    db.execute('DELETE FROM checklist_checks WHERE quest_id=? AND cycle=?',(qid,self.expected[2]))
                                    db.executemany('INSERT INTO checklist_checks VALUES(?,?,?,?)',[(qid,self.expected[2],idx,str(owner)) for idx in values])
                                text=f'{len(values)}/{len(items)} steps checked. Mark the chore Done when finished.'
                    await w.present(i,Checklist(owner,qid,i.guild,back),text)
                picker.callback=change;self.step_picker=picker
                self.step_buttons=[]
                for index,item in enumerate(items):
                    async def toggle(i,index=index):
                        values=set(self.expected[3])^{index}
                        picker._values=[str(v) for v in sorted(values)]
                        await change(i)
                    button=self.button(item,toggle,row=index//5,primary=index in done)
                    button.emoji='\u2611' if index in done else '\u2610'
                    button.style=discord.ButtonStyle.success if index in done else discord.ButtonStyle.secondary
                    button._sprig_checklist_step=index
                    self.step_buttons.append(button)
            elif not items:self.embed.add_field(name='No checklist yet',value='Use Estimate / checklist from the chore card to add steps.')
            else:self.embed.add_field(name='View only',value='Only the person responsible for the current due occurrence can check or uncheck steps.')
            if q and items and complete(qid) and not q[5] and not ui.is_archived(qid) and timing.ready(qid) and uid==str(owner) and ui.available(owner):
                async def finish(i):
                    if not await self.interaction_check(i):return
                    await i.response.defer()
                    async with lock:
                        ns['reset_due_quests']()
                        if (ui.snapshot(qid),plan(qid),cycle(qid),sorted(checked(qid)))!=self.expected:text='This occurrence or checklist changed. Review the chore.'
                        else:
                            context=ui.Context(i)
                            await bot.get_command('done').callback(context,qid)
                            text='\n'.join(context.messages)
                    await w.present(i,back(),text)
                self.button('Done',finish,row=3,primary=True)
            self.button('Open chore',lambda i:w.present(i,back()),row=3)
            self.nav(back)

    def settings(uid):
        return db.execute('SELECT enabled,times,revision FROM reminder_settings WHERE user_id=?',(str(uid),)).fetchone() or (0,'["09:00", "17:00"]',0)
    def save_reminders(uid,enabled,text,expected):
        if settings(uid)!=expected:return 'Reminder settings changed. Reopen them before saving.'
        values=sorted(set(v.strip() for v in text.split(',') if v.strip()))
        try:
            if not 1<=len(values)<=10:raise ValueError
            if any(datetime.strptime(v,'%H:%M').strftime('%H:%M')!=v for v in values):raise ValueError
        except ValueError:return 'Use one to ten times in 24-hour HH:MM format, separated by commas; for example 09:00, 17:00.'
        with db:db.execute('INSERT OR REPLACE INTO reminder_settings VALUES(?,?,?,?)',(str(uid),int(enabled),json.dumps(values),expected[2]+1))
        return 'Chore reminders '+('on. Times are Eastern. Only your due responsibilities are included.' if enabled else 'off. Your chores and sign-ups are unchanged.')
    class ReminderTimes(discord.ui.Modal):
        def __init__(self,owner):
            super().__init__(title='Your reminder times')
            self.owner,self.expected=owner,settings(owner)
            self.times=discord.ui.TextInput(label='Up to 10 Eastern times (24-hour, commas)',default=', '.join(json.loads(self.expected[1])),max_length=70)
            self.add_item(self.times)
        async def on_submit(self,i):
            if not await w.View(self.owner).interaction_check(i):return
            async with lock:text=save_reminders(self.owner,self.expected[0],self.times.value,self.expected)
            await w.present(i,Reminders(self.owner),text)
    class Reminders(w.View):
        def __init__(self,owner):
            super().__init__(owner)
            expected=settings(owner)
            self.recovery_context={'screen':'reminders'}
            self.embed=discord.Embed(title='Chore reminders',description='**'+('On' if expected[0] else 'Off')+'** · '+', '.join(json.loads(expected[1]))+' Eastern\nScheduled due-chore DMs at up to 10 daily times. These settings apply to your account, not each task. No reminders while away or when nothing is due.\nTurn on allows private DMs to your account; change times or turn off anytime. Missed reminders are not replayed. Trade proposal DMs have a separate switch under Dashboard → Trade alerts.',color=0x6B9B77)
            last=db.execute('SELECT slot,status FROM reminder_deliveries WHERE user_id=? ORDER BY slot DESC LIMIT 1',(str(owner),)).fetchone()
            if last:
                labels={'sent':'Sent','canceled':'Not sent: chores, preferences, location, or reminder time changed.',
                    'skipped_empty':'Not sent: no due chores at that time.','skipped_away':'Not sent: you were away at that time.',
                    'skipped_week':'Not sent: that reminder time belonged to the previous household week.',
                    'failed_uncertain':'Delivery uncertain or blocked; check Discord DM privacy. No automatic retry.'}
                self.embed.add_field(name='Last reminder attempt',value=last[0]+' · '+labels.get(last[1],last[1]),inline=False)
            async def toggle(i):
                if not await self.interaction_check(i):return
                async with lock:text=save_reminders(owner,not expected[0],','.join(json.loads(expected[1])),expected)
                await w.present(i,Reminders(owner),text)
            self.button('Turn off' if expected[0] else 'Turn on',toggle,row=0)
            self.button('Change times',lambda i:i.response.send_modal(ReminderTimes(owner)),row=0)
            self.nav()

    def reminder_records(uid):
        # Re-read the full set, including newly assigned/due work, after lookup.
        ns['reset_due_quests']()
        return [(qid,name) for qid,name in db.execute('SELECT id,name FROM quests WHERE completed=0 ORDER BY name COLLATE NOCASE,id').fetchall()
            if not ui.is_archived(qid) and timing.ready(qid) and w.ownership(qid)[0]==str(uid)]

    async def send_due_reminders():
        ns['reset_due_quests']()
        now=timing.now()
        location=db.execute('SELECT guild_id,channel_id FROM chore_board WHERE singleton=1').fetchone()
        if not location:return
        for uid,enabled,times,revision in db.execute('SELECT user_id,enabled,times,revision FROM reminder_settings WHERE enabled=1').fetchall():
            expected=(enabled,times,revision)
            if settings(uid)!=expected:continue
            for value in json.loads(times):
                hour,minute=map(int,value.split(':'))
                due=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
                if datetime.fromtimestamp(due.timestamp(),ns['QUEST_TIMEZONE']).strftime('%H:%M')!=value:continue
                elapsed=timing.now().timestamp()-due.timestamp()
                if not 0<=elapsed<900:continue
                slot=now.date().isoformat()+' '+value
                if db.execute('SELECT 1 FROM reminder_deliveries WHERE user_id=? AND slot=?',(uid,slot)).fetchone():continue
                available=ui.available(uid)
                records=reminder_records(uid) if available else []
                skipped=('skipped_week' if due<ui.week_start() else 'skipped_away' if not available else 'skipped_empty' if not records else None)
                # Record empty/away slots too: later ownership changes must not
                # backfill an earlier reminder and duplicate the next chosen time.
                # Claim delivery before network I/O; uncertain sends never get retried.
                with db:
                    claimed=db.execute('INSERT OR IGNORE INTO reminder_deliveries VALUES(?,?,?)',(uid,slot,skipped or 'sending')).rowcount
                if not claimed or skipped:continue
                try:
                    user=bot.get_user(int(uid)) or await asyncio.wait_for(bot.fetch_user(int(uid)),timeout=5)
                    records=reminder_records(uid)
                    current_location=db.execute('SELECT guild_id,channel_id FROM chore_board WHERE singleton=1').fetchone()
                    # No await between this validation and handing the DM to Discord.
                    # An already handed-off message cannot be recalled by later edits.
                    if (settings(uid)!=expected or not ui.available(uid) or not records
                            or current_location!=location or due<ui.week_start() or not 0<=timing.now().timestamp()-due.timestamp()<900):status='canceled'
                    else:
                        text='Your due chores:\n'+'\n'.join('• '+w.clean(name,80)+summary(qid) for qid,name in records[:12])
                        if len(records)>12:text+=f'\n…and {len(records)-12} more.'
                        text+='\nOpen /chores to check steps or mark Done. Change or turn off reminders from Dashboard → Reminders.'
                        view=discord.ui.View();view.add_item(discord.ui.Button(label='Open household channel',url=f'https://discord.com/channels/{location[0]}/{location[1]}'))
                        await asyncio.wait_for(user.send(text,view=view,allowed_mentions=discord.AllowedMentions.none()),timeout=10)
                        status='sent'
                except Exception:status='failed_uncertain'
                with db:db.execute('UPDATE reminder_deliveries SET status=? WHERE user_id=? AND slot=?',(status,uid,slot))

    def owner_on(q,day):
        at=datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE'])
        dated=ui.dated.owner(q[0],at) or ui.dated.owner(q[0],at.replace(hour=12))
        if dated:return dated
        if q[4]:return str(q[4])
        start=day-timedelta(days=(day.weekday()+1)%7 or 7)
        weekly=db.execute('SELECT user_id FROM week_signups WHERE quest_id=? AND week_start=?',(q[0],start.isoformat())).fetchone()
        if weekly:return weekly[0]
        if day==timing.now().date():
            claim=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(q[0],)).fetchone()
            if claim:return claim[0]
        when=datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE'])
        return ui.repeating.owner(q[0],when) or ui.repeating.owner(q[0],when.replace(hour=12))
    def dated(q,day):
        move=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(q[0],)).fetchone()
        if move and move[0]==day.isoformat():return True
        if move and day<=datetime.fromisoformat(move[0]).date():return False
        if q[2] in ('daily','daily-am','daily-pm','twice-daily'):return True
        return timing.matches(day,q[2]) if q[2] in SCHEDULED else False
    def project(day,owner=None,flexible=False):
        result=[]
        for q in db.execute('SELECT id,name,frequency,points,assigned_to,completed,last_completed,reset_after FROM quests ORDER BY name COLLATE NOCASE').fetchall():
            if ui.is_archived(q[0]):continue
            slots=ui.dated.slots(q[0])
            if slots and all(ui.dated.skipped(q[0],ui.dated.when(day,slot)) for slot in slots):continue
            skipped=db.execute('SELECT skipped_at,next_due FROM occurrence_skips WHERE quest_id=? AND NOT EXISTS (SELECT 1 FROM skip_undo_state u WHERE u.skip_id=occurrence_skips.id AND u.undone_at IS NOT NULL) ORDER BY id DESC LIMIT 1',(q[0],)).fetchone()
            if skipped and timing.state(q[0])==(skipped[1],) and datetime.fromisoformat(skipped[0]).date()<=day<datetime.fromisoformat(skipped[1]).date():continue
            if flexible:
                if q[2] not in ('weekly','monthly','one-time') or db.execute('SELECT 1 FROM occurrence_moves WHERE quest_id=?',(q[0],)).fetchone():continue
                if q[2]=='one-time' and q[5]:continue
            elif not dated(q,day):continue
            uid=owner_on(q,day)
            if owner is not None and uid!=str(owner) and not any((ui.dated.owner(q[0],datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).replace(hour=h)) or ui.repeating.owner(q[0],datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).replace(hour=h)))==str(owner) for h in (0,12)):continue
            result.append((q,uid))
        return result
    class Calendar(w.View):
        def __init__(self,owner,guild=None,day=None,mode='week',mine=False):
            super().__init__(owner)
            day=day or timing.now().date();start=day-timedelta(days=day.weekday())
            self.recovery_context={'screen':'calendar','day':day.isoformat(),'mode':mode,'mine':mine}
            self.embed=discord.Embed(title=('My' if mine else 'Household')+' calendar · '+(f'{start:%b %d}–{start+timedelta(days=6):%b %d}' if mode=='week' else f'{day:%B %Y}'),description='Schedule preview · Eastern time. Flexible chores are below; unfinished overdue work stays in Due now. Sunday ownership is shown before the 6 p.m. handoff. Past schedules are not a complete activity history.',color=0x6B9B77)
            def view(**changes):return Calendar(owner,guild,**dict(dict(day=day,mode=mode,mine=mine),**changes))
            self.button('Week',lambda i:w.present(i,view(mode='week')),row=0,primary=mode=='week')
            self.button('Month',lambda i:w.present(i,view(mode='month')),row=0,primary=mode=='month')
            self.button('Mine',lambda i:w.present(i,view(mine=True)),row=0,primary=mine)
            self.button('Everyone',lambda i:w.present(i,view(mine=False)),row=0,primary=not mine)
            if mode=='week':
                for idx in range(7):
                    date=start+timedelta(days=idx);rows=project(date,owner if mine else None)
                    minutes=sum((plan(q[0])[0] or 0)*(2 if q[2]=='twice-daily' else 1) for q,uid in rows)
                    preview='\n'.join(w.clean(q[1],65) for q,uid in rows[:3]) or 'No fixed-day chores'
                    if len(rows)>3:preview+=f'\n+ {len(rows)-3} more'
                    self.embed.add_field(name=f'{day_badge(WEEKDAYS[idx])} {date:%b %d} · {len(rows)} chore(s)',value=preview+(f'\n~{minutes} known minutes' if minutes else ''),inline=False)
                    self.button(f'{WEEKDAYS[idx].title()} {date.day}',lambda i,date=date:w.present(i,Day(owner,date,mine,i.guild,mode=mode)),row=1 if idx<4 else 2)
                earlier=start-timedelta(days=7);later=start+timedelta(days=7)
            else:
                grid=calendar.Calendar(firstweekday=0).monthdayscalendar(day.year,day.month)
                text='Mo Tu We Th Fr Sa Su\n'+'\n'.join(' '.join(f'{d:2}' if d else '  ' for d in week) for week in grid)
                self.embed.add_field(name='🔴 Mon · 🟠 Tue · 🟡 Wed · 🟢 Thu · 🔵 Fri · 🟣 Sat · 🩷 Sun',value='```\n'+text+'\n```\nChoose a date below for its chores.',inline=False)
                count=calendar.monthrange(day.year,day.month)[1]
                for row,values in enumerate((range(1,min(count,16)+1),range(17,count+1)),1):
                    picker=discord.ui.Select(placeholder='Choose date '+('1–16' if row==1 else f'17–{count}'),row=row,options=[discord.SelectOption(label=day.replace(day=d).strftime('%a %b %d')+f' · {len(project(day.replace(day=d),owner if mine else None))} chores',value=str(d)) for d in values])
                    async def select(i,picker=picker):await w.present(i,Day(owner,day.replace(day=int(picker.values[0])),mine,i.guild,mode=mode))
                    picker.callback=select;self.add_item(picker)
                earlier=day.replace(day=1)-timedelta(days=1);later=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
            self.button('Previous',lambda i:w.present(i,view(day=earlier)),row=3)
            self.button('Today',lambda i:w.present(i,view(day=timing.now().date())),row=3)
            self.button('Next',lambda i:w.present(i,view(day=later)),row=3)
            self.button('No fixed day',lambda i:w.present(i,Day(owner,day,mine,i.guild,flexible=True,mode=mode)),row=0)
            self.nav()
    class Day(w.View):
        def __init__(self,owner,day,mine=False,guild=None,page=0,flexible=False,mode='week'):
            super().__init__(owner)
            size=w.page_size(owner)
            self.list_page_size=size
            rows=project(day,owner if mine else None,flexible);page=min(max(page,0),max((len(rows)-1)//size,0));chunk=rows[page*size:(page+1)*size]
            self.day,self.page,self.mine,self.flexible,self.mode=day,page,mine,flexible,mode
            self.button('Mine',lambda i:w.present(i,Day(owner,day,True,i.guild,flexible=flexible,mode=mode)),row=2,primary=mine)
            self.button('Everyone',lambda i:w.present(i,Day(owner,day,False,i.guild,flexible=flexible,mode=mode)),row=2,primary=not mine)
            self.name_ids=[uid for q,uid in chunk if uid]+[uid for q,_ in chunk for _,_,uid in ui.repeating.slots(q[0])]
            self.rebuild=lambda:Day(owner,day,mine,guild,page,flexible,mode)
            self.recovery_context={'screen':'day','day':day.isoformat(),'page':page,'mine':mine,'flexible':flexible,'mode':mode,'list_size':size}
            self.paging_labels=('Previous page','Next page')
            self.embed=discord.Embed(title=('No fixed day · '+day.strftime('%b %d')) if flexible else day_badge(WEEKDAYS[day.weekday()])+' '+day.strftime('%b %d, %Y'),description='Schedule preview · Details opens a chore; choosing a date does not reserve or reschedule it.'+(' Weekly/monthly chores are flexible until given a day. Owners are shown for this date’s household week.' if flexible else ''),color=0x6B9B77)
            for q,uid in chunk:
                when=datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).replace(hour=12)
                away=uid and not ui.attendance.at(uid,when)
                self.embed.add_field(name=w.clean(q[1],100),value=((' · '.join(s.upper()+': '+('Skipped' if ui.dated.skipped(q[0],when.replace(hour=12 if s=='pm' else 0)) else w.clean(w.person(ui.dated.owner(q[0],when.replace(hour=12 if s=='pm' else 0)) or ui.dated.base_owner(q[0],when.replace(hour=12 if s=='pm' else 0)),guild),65)) for s in ui.repeating.shifts(q[0]))) if ui.dated.slots(q[0])==('am','pm') or ui.repeating.slots(q[0]) else w.clean(w.person(uid,guild),100))+f' · {q[3]} points'+summary(q[0])+(' · ⚠ Away' if away else ''),inline=False)
            self.embed.set_footer(text=f'Page {page+1} of {max((len(rows)-1)//size+1,1)} · '+(f'Chores {page*size+1}–{page*size+len(chunk)} of {len(rows)}' if rows else '0 chores')+' · Eastern time')
            if chunk:
                picker=discord.ui.Select(placeholder='Choose chore',row=0,options=[discord.SelectOption(label=q[1][:100],value=str(q[0])) for q,uid in chunk])
                async def open_chore(i,qid):
                    q=chore(qid)
                    parent=lambda:Day(owner,day,mine,i.guild,page,flexible,mode)
                    if day==timing.now().date():return await w.present(i,w.Card(owner,qid,back=parent,guild=i.guild))
                    offered=ui.dated.slots(qid)
                    if offered and day>=timing.now().date():
                        if len(offered)>1:return await w.present(i,w.FutureSlots(owner,qid,day,i.guild,parent))
                        if ui.dated.when(day,offered[0])>timing.now() or ui.dated.record(qid,day,offered[0]):
                            return await w.present(i,w.FutureOccurrence(owner,qid,day,offered[0],i.guild,parent))
                    if day==timing.now().date():return await w.present(i,w.Card(owner,qid,back=parent,guild=i.guild))
                    await w.present(i,w.Card(owner,qid,back=parent,guild=i.guild,notice=f'Current occurrence. Calendar selection: {day:%a %b %d, %Y}. Actions below apply to the current occurrence.'))
                self.calendar_details=[(q[0],open_chore) for q,uid in chunk]
                async def select(i):await open_chore(i,int(picker.values[0]))
                picker.callback=select;self.add_item(picker)
            else:self.embed.add_field(name='No chores here',value='Try Household, No fixed day, or Due now for overdue work.')
            if page:self.button('Previous page',lambda i:w.present(i,Day(owner,day,mine,i.guild,page-1,flexible,mode)),row=3)
            if (page+1)*size<len(rows):self.button('Next page',lambda i:w.present(i,Day(owner,day,mine,i.guild,page+1,flexible,mode)),row=3)
            self.button('Previous day',lambda i:w.present(i,Day(owner,day-timedelta(days=1),mine,i.guild,0,flexible,mode)),row=1)
            self.button('Today',lambda i:w.present(i,Day(owner,timing.now().date(),mine,i.guild,0,flexible,mode)),row=1)
            self.button('Next day',lambda i:w.present(i,Day(owner,day+timedelta(days=1),mine,i.guild,0,flexible,mode)),row=1)
            self.button('Week',lambda i:w.present(i,Calendar(owner,i.guild,day,mode='week',mine=mine)),row=2)
            self.button('Month',lambda i:w.present(i,Calendar(owner,i.guild,day,mode='month',mine=mine)),row=2)
            self.nav(lambda:Calendar(owner,guild,day,mode=mode,mine=mine))
    def occurrence(qid):
        q=chore(qid)
        if not q:return ''
        raw=json.dumps([q[2],q[6],q[7],timing.state(qid),timing.policy_state(qid) if timing.policy(qid)=='skip' else None])
        return hashlib.sha256(raw.encode()).hexdigest()
    def help_record(qid):
        return db.execute('SELECT id,quest_id,cycle,reporter,kind,note,created_at FROM chore_help WHERE quest_id=? AND cycle=? AND resolved_at IS NULL ORDER BY id DESC LIMIT 1',(qid,occurrence(qid))).fetchone()
    def help_snapshot(qid):return (ui.snapshot(qid),occurrence(qid),help_record(qid))
    def help_summary(qid):
        q=chore(qid);record=help_record(qid)
        return ' · ⚠ '+record[4] if q and not q[5] and not ui.is_archived(qid) and record else ''
    def help_unavailable(qid,q):
        if not q:return 'This chore is no longer available.'
        if ui.is_archived(qid):return 'This chore is archived. Restore it before reporting a new problem.'
        if q[5]:return 'This occurrence is already done. Earlier help notes are in Status history.'
        return None
    def report_help(actor,qid,kind,note,expected):
        q=chore(qid);note=note.strip()
        reason=help_unavailable(qid,q)
        if reason:return reason
        if help_snapshot(qid)!=expected:return 'This chore or help status changed. Reopen it before saving.'
        if kind not in ('Stuck','Need supplies','Need help') or not 1<=len(note)<=500:return 'Choose a help status and add a note of up to 500 characters.'
        with db:
            db.execute('UPDATE chore_help SET resolved_at=?,resolved_by=?,resolution=? WHERE quest_id=? AND cycle=? AND resolved_at IS NULL',(timing.now().isoformat(),str(actor),'Updated by household member',qid,occurrence(qid)))
            db.execute('INSERT INTO chore_help(quest_id,cycle,reporter,kind,note,created_at) VALUES(?,?,?,?,?,?)',(qid,occurrence(qid),str(actor),kind,note,timing.now().isoformat()))
        return 'Help status saved. Responsibility, completion, and points are unchanged. The household can see this note.'
    def resolve_help(actor,qid,expected):
        q=chore(qid)
        if not q or q[5] or ui.is_archived(qid) or help_snapshot(qid)!=expected or not expected[2]:return 'This help status changed or is no longer active. Nothing cleared.'
        with db:
            db.execute('UPDATE chore_help SET resolved_at=?,resolved_by=?,resolution=? WHERE id=? AND resolved_at IS NULL',(timing.now().isoformat(),str(actor),'Marked resolved',expected[2][0]))
        return 'Help status resolved. The note stays in history; responsibility and points are unchanged.'
    class HelpNote(discord.ui.Modal):
        def __init__(self,owner,qid,kind):
            super().__init__(title=kind+' · chore')
            self.owner,self.qid,self.kind,self.expected=owner,qid,kind,help_snapshot(qid)
            record=help_record(qid)
            self.note=discord.ui.TextInput(label='What is stopping you? Shared with household',style=discord.TextStyle.paragraph,max_length=500,default=record[5] if record and record[3]==str(owner) else '')
            self.add_item(self.note)
        async def on_submit(self,i):
            if not await w.View(self.owner).interaction_check(i):return
            await i.response.defer()
            async with lock:text=report_help(i.user.id,self.qid,self.kind,self.note.value,self.expected)
            await w.present(i,HelpStatus(self.owner,self.qid,i.guild),text)
    class HelpStatus(w.View):
        def __init__(self,owner,qid,guild=None):
            super().__init__(owner)
            q=chore(qid);record=help_record(qid);expected=help_snapshot(qid)
            self.embed=discord.Embed(title='Help status · '+w.clean(q[1],100) if q else 'Chore unavailable',description='Anyone in the household can report a problem with an unfinished chore. No need to claim it first. Notes are shared; no automatic DM is sent.',color=0x6B9B77)
            if record and q and not q[5] and not ui.is_archived(qid):
                self.embed.add_field(name=record[4],value=w.clean(record[5],650)+'\nReported by '+w.clean(w.person(record[3],guild),100),inline=False)
                self.name_ids=[record[3]];self.rebuild=lambda:HelpStatus(owner,qid,guild)
                async def ask(i):
                    if not await self.interaction_check(i):return
                    async def save(event):
                        if not await self.interaction_check(event):return
                        await event.response.defer()
                        async with lock:text=resolve_help(event.user.id,qid,expected)
                        await w.present(event,HelpStatus(owner,qid,event.guild),text)
                    await w.present(i,w.Confirm(owner,'Mark this help status resolved?','This clears the active status, keeping the note in history. It does not complete or release the chore.',save,lambda:HelpStatus(owner,qid,guild)))
                self.button('Mark resolved',ask,row=1)
            else:
                reason=help_unavailable(qid,q)
                self.embed.add_field(name='Reporting unavailable' if reason else 'No help note yet',value=reason or 'Choose what you need below. Responsibility and points stay unchanged.',inline=False)
            if not help_unavailable(qid,q):
                for kind in ('Stuck','Need supplies','Need help'):
                    async def choose(i,kind=kind):
                        if not await self.interaction_check(i):return
                        await i.response.send_modal(HelpNote(owner,qid,kind))
                    self.button(kind,choose,row=0)
            self.button('Status history',lambda i:w.present(i,HelpHistory(owner,qid,i.guild)),row=2)
            self.nav(lambda:w.Card(owner,qid,guild=guild))
    class HelpHistory(w.View):
        def __init__(self,owner,qid,guild=None,page=0):
            super().__init__(owner)
            size=w.page_size(owner)
            self.list_page_size=size
            self.paging_labels=('Previous','Next')
            rows=db.execute('SELECT kind,note,reporter,created_at,resolved_at,resolved_by,resolution FROM chore_help WHERE quest_id=? ORDER BY id DESC',(qid,)).fetchall()
            page=min(max(page,0),max((len(rows)-1)//size,0))
            self.embed=discord.Embed(title='Chore help history',description='Earlier occurrences and resolved or updated notes remain saved.',color=0x6B9B77)
            for kind,note,reporter,created,resolved,by,resolution in rows[page*size:(page+1)*size]:
                self.embed.add_field(name=kind+' · '+created[:16],value=w.clean(note,450)+'\n'+('Resolved by '+w.clean(w.person(by,guild),80)+' · '+str(resolution) if resolved else 'Saved for its occurrence')+'\nReported by '+w.clean(w.person(reporter,guild),80),inline=False)
            if not rows:self.embed.add_field(name='No notes yet',value='Help notes will appear here.')
            if page:self.button('Previous',lambda i:w.present(i,HelpHistory(owner,qid,i.guild,page-1)),row=3)
            if (page+1)*size<len(rows):self.button('Next',lambda i:w.present(i,HelpHistory(owner,qid,i.guild,page+1)),row=3)
            self.nav(lambda:HelpStatus(owner,qid,guild))
    class NeedsHelp(w.View):
        def __init__(self,owner,guild=None,page=0):
            super().__init__(owner)
            size=w.page_size(owner)
            self.list_page_size=size
            self.paging_labels=('Previous','Next')
            rows=[(q,help_record(q[0])) for q in db.execute('SELECT id,name FROM quests WHERE completed=0 ORDER BY name').fetchall() if not ui.is_archived(q[0]) and help_record(q[0])]
            page=min(max(page,0),max((len(rows)-1)//size,0));chunk=rows[page*size:(page+1)*size]
            self.embed=discord.Embed(title='Chores needing help',description=f'{len(rows)} active issue(s). Everyone can read notes and mark resolved when the obstacle is handled.',color=0x6B9B77)
            for q,r in chunk:self.embed.add_field(name=w.clean(q[1],100)+' · '+r[4],value=w.clean(r[5],450),inline=False)
            if chunk:
                picker=discord.ui.Select(placeholder='Open a help status',row=0,options=[discord.SelectOption(label=q[1][:100],value=str(q[0])) for q,r in chunk])
                async def choose(i):await w.present(i,HelpStatus(owner,int(picker.values[0]),i.guild))
                picker.callback=choose;self.add_item(picker)
            else:self.embed.add_field(name='No active issues',value='New status notes appear here; ordinary unfinished work remains in chores.')
            if page:self.button('Previous',lambda i:w.present(i,NeedsHelp(owner,i.guild,page-1)),row=3)
            if (page+1)*size<len(rows):self.button('Next',lambda i:w.present(i,NeedsHelp(owner,i.guild,page+1)),row=3)
            self.recovery_context={'screen':'needs_help','page':page}
            self.button('Refresh',lambda i:w.present(i,NeedsHelp(owner,i.guild,page)),row=3);self.nav()

    def duplicate_snapshot(qid):
        return (db.execute('SELECT name,frequency,points,notes,category,difficulty FROM quests WHERE id=?',(qid,)).fetchone(),plan(qid),timing.policy(qid),ui.is_archived(qid))
    def duplicate(qid,name,expected,key,actor):
        previous=db.execute('SELECT new_id FROM chore_copies WHERE submission_key=?',(key,)).fetchone()
        if previous:return previous[0],'This copy was already saved. No duplicate created.'
        name=' '.join(name.split())
        if not name or len(name)>100:return None,'Use a new name from 1 to 100 characters.'
        if any(' '.join(r[0].split()).casefold()==name.casefold() for r in db.execute('SELECT name FROM quests')):return None,'A chore with that name already exists, including archived chores. Choose a different name.'
        source=duplicate_snapshot(qid)
        if not source[0] or source!=expected or source[3]:return None,'The source chore changed or was archived. Reopen Duplicate chore.'
        _,frequency,points,notes,room,difficulty=source[0]
        if frequency not in ns['VALID_FREQUENCIES']:return None,'The source has an unsupported schedule. Edit it before copying.'
        with db:
            new_id=db.execute('INSERT INTO quests(name,frequency,points,notes,category,difficulty) VALUES(?,?,?,?,?,?)',(name,frequency,points,notes,room,difficulty)).lastrowid
            timing.initialize(new_id,frequency)
            db.execute('INSERT INTO chore_plans SELECT ?,minutes,steps,revision FROM chore_plans WHERE quest_id=?',(new_id,qid))
            db.execute('INSERT INTO chore_checklist_revisions SELECT ?,revision FROM chore_checklist_revisions WHERE quest_id=?',(new_id,qid))
            if source[2]=='skip':db.execute('INSERT INTO missed_chore_policy VALUES(?,?,?)',(new_id,'skip',timing.deadline(new_id,frequency)))
            db.execute('INSERT INTO chore_copies VALUES(?,?,?,?,?)',(key,qid,new_id,str(actor),timing.now().isoformat()))
        return new_id,'New unassigned chore created. Instructions, schedule, points, room, difficulty, estimate, checklist, and missed-work policy were copied. Sign-ups, completion history, checked steps, help notes, and date moves were not copied.'
    class DuplicateModal(discord.ui.Modal):
        def __init__(self,owner,qid):
            from uuid import uuid4
            super().__init__(title='Duplicate chore')
            self.owner,self.qid,self.expected,self.key=owner,qid,duplicate_snapshot(qid),str(uuid4())
            source=chore(qid)
            self.name=discord.ui.TextInput(label='New chore name',max_length=100,default=(source[1][:93]+' (copy)') if source else '')
            self.add_item(self.name)
        async def on_submit(self,i):
            if not await w.View(self.owner).interaction_check(i):return
            name=' '.join(self.name.value.split())
            async def save(event):
                if not await w.View(self.owner).interaction_check(event):return
                await event.response.defer()
                async with lock:qid,text=duplicate(self.qid,name,self.expected,self.key,event.user.id)
                await w.present(event,w.Card(self.owner,qid or self.qid,guild=event.guild),text)
            source=self.expected[0]
            text='Create **'+w.clean(name,100)+'** as a new unassigned chore.\n'+(f'{source[2]} points · '+timing.compact_label(source[1]) if source else 'Source unavailable')+'\nCopies instructions, room, difficulty, estimate, checklist, and missed-work policy. No claims, assignments, sign-ups, completion history, checked steps, help notes, or one-off date moves are copied.'
            await w.present(i,w.Confirm(self.owner,'Create this chore copy?',text,save,lambda:w.Card(self.owner,self.qid,guild=i.guild)))

    return SimpleNamespace(help_record=help_record,help_snapshot=help_snapshot,help_summary=help_summary,report_help=report_help,resolve_help=resolve_help,HelpNote=HelpNote,HelpStatus=HelpStatus,HelpHistory=HelpHistory,NeedsHelp=NeedsHelp,duplicate_snapshot=duplicate_snapshot,duplicate=duplicate,DuplicateModal=DuplicateModal,plan=plan,steps=steps,cycle=cycle,checked=checked,complete=complete,summary=summary,history_state=history_state,save_plan=save_plan,PlanModal=PlanModal,Checklist=Checklist,settings=settings,save_reminders=save_reminders,Reminders=Reminders,ReminderTimes=ReminderTimes,send_due_reminders=send_due_reminders,Calendar=Calendar,Day=Day,project=project,owner_on=owner_on)
