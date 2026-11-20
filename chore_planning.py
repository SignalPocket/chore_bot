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
    CREATE TABLE IF NOT EXISTS morning_triage_days(day TEXT PRIMARY KEY,dm_status TEXT NOT NULL DEFAULT 'pending',dm_message_id TEXT,completed_at TEXT,shared_status TEXT NOT NULL DEFAULT 'pending',shared_message_id TEXT);
    CREATE TABLE IF NOT EXISTS morning_triage_items(day TEXT NOT NULL,quest_id INTEGER NOT NULL,position INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',acted_at TEXT,PRIMARY KEY(day,quest_id));
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

    def morning_due_records():
        ns['reset_due_quests']()
        return [q for q in db.execute('SELECT id,name,frequency,points,assigned_to,completed,last_completed,reset_after FROM quests WHERE completed=0 ORDER BY name COLLATE NOCASE,id').fetchall()
            if not ui.is_archived(q[0]) and timing.ready(q[0])]

    def ensure_morning_day(day):
        key=day.isoformat()
        with db:
            created=db.execute("INSERT OR IGNORE INTO morning_triage_days(day) VALUES(?)",(key,)).rowcount
            completed=db.execute('SELECT completed_at FROM morning_triage_days WHERE day=?',(key,)).fetchone()[0]
            if created or not completed:
                existing={qid for qid, in db.execute('SELECT quest_id FROM morning_triage_items WHERE day=?',(key,))}
                position=db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM morning_triage_items WHERE day=?',(key,)).fetchone()[0]
                additions=[q[0] for q in morning_due_records() if q[0] not in existing]
                db.executemany('INSERT INTO morning_triage_items(day,quest_id,position) VALUES(?,?,?)',
                    [(key,qid,position+index) for index,qid in enumerate(additions)])
        return key

    def morning_item(day):
        key=day.isoformat() if hasattr(day,'isoformat') else str(day)
        ns['reset_due_quests']()
        while True:
            row=db.execute('SELECT i.quest_id,q.name,q.frequency,q.points FROM morning_triage_items i LEFT JOIN quests q ON q.id=i.quest_id WHERE i.day=? AND i.status=? ORDER BY i.position LIMIT 1',(key,'pending')).fetchone()
            if not row:
                if not db.execute('SELECT completed_at FROM morning_triage_days WHERE day=?',(key,)).fetchone()[0]:
                    with db:db.execute('UPDATE morning_triage_days SET completed_at=? WHERE day=?',(timing.now().isoformat(),key))
                return None
            qid=row[0]
            current=db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()
            if current and not current[0] and not ui.is_archived(qid) and timing.ready(qid):return row
            with db:db.execute("UPDATE morning_triage_items SET status='resolved_elsewhere',acted_at=? WHERE day=? AND quest_id=?",(timing.now().isoformat(),key,qid))

    def finish_morning_item(day,qid,status):
        key=day.isoformat() if hasattr(day,'isoformat') else str(day)
        with db:
            changed=db.execute("UPDATE morning_triage_items SET status=?,acted_at=? WHERE day=? AND quest_id=? AND status='pending'",(status,timing.now().isoformat(),key,qid)).rowcount
        if changed:morning_item(key)
        return bool(changed)

    def reopen_morning_day(actor,day=None):
        """Reopen today's live due work without replaying either delivery."""
        if str(actor)!=str(ns['REVIEW_OWNER_ID']):return 0
        day=day or timing.now().date();key=day.isoformat();records=morning_due_records()
        with db:
            db.execute('INSERT OR IGNORE INTO morning_triage_days(day) VALUES(?)',(key,))
            existing={qid for qid, in db.execute('SELECT quest_id FROM morning_triage_items WHERE day=?',(key,))}
            position=db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM morning_triage_items WHERE day=?',(key,)).fetchone()[0]
            additions=[q[0] for q in records if q[0] not in existing]
            db.executemany('INSERT INTO morning_triage_items(day,quest_id,position) VALUES(?,?,?)',
                [(key,qid,position+index) for index,qid in enumerate(additions)])
            for q in records:
                db.execute("UPDATE morning_triage_items SET status='pending',acted_at=NULL WHERE day=? AND quest_id=?",(key,q[0]))
            db.execute('UPDATE morning_triage_days SET completed_at=? WHERE day=?',
                (None if records else timing.now().isoformat(),key))
        return len(records)

    def morning_pending(day):
        key=day.isoformat() if hasattr(day,'isoformat') else str(day)
        ns['reset_due_quests']();valid=[];invalid=[]
        for row in db.execute('SELECT i.quest_id,q.name,q.frequency,q.points FROM morning_triage_items i LEFT JOIN quests q ON q.id=i.quest_id WHERE i.day=? AND i.status=? ORDER BY i.position',(key,'pending')).fetchall():
            current=db.execute('SELECT completed FROM quests WHERE id=?',(row[0],)).fetchone()
            if current and not current[0] and not ui.is_archived(row[0]) and timing.ready(row[0]):valid.append(row)
            else:invalid.append(row[0])
        if invalid:
            with db:
                db.executemany("UPDATE morning_triage_items SET status='resolved_elsewhere',acted_at=? WHERE day=? AND quest_id=? AND status='pending'",
                    [(timing.now().isoformat(),key,qid) for qid in invalid])
        if not valid:
            row=db.execute('SELECT completed_at FROM morning_triage_days WHERE day=?',(key,)).fetchone()
            if row and not row[0]:
                with db:db.execute('UPDATE morning_triage_days SET completed_at=? WHERE day=?',(timing.now().isoformat(),key))
        return valid

    def assign_morning_occurrence(actor,qid,target,expected):
        ns['reset_due_quests']()
        if str(actor)!=str(ns['REVIEW_OWNER_ID']):return 'Only ginaria can sort the morning chore list.'
        if ui.snapshot(qid)!=expected or ui.is_archived(qid) or not timing.ready(qid):return 'This chore changed. Review the current morning item.'
        if not ui.available(target):return 'That person is away today. Choose someone who is home.'
        day=timing.now().date();slot=ui.dated.key(qid)[1]
        if not (ui.dated.valid(qid,day,slot) or ui.dated.current_due(qid,day,slot)):return 'This occurrence cannot be assigned for today.'
        before=ui.dated.record(qid,day,slot)
        frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()[0]
        after=(frequency,'claim',str(target),(before[3] if before else 0)+1)
        with db:
            db.execute('INSERT OR REPLACE INTO dated_occurrences VALUES(?,?,?,?,?,?,?)',(qid,day.isoformat(),slot,*after))
            db.execute('INSERT INTO dated_occurrence_changes(quest_id,day,slot,actor,action,changed_at,before_state,after_state) VALUES(?,?,?,?,?,?,?,?)',
                (qid,day.isoformat(),slot,str(actor),'morning_assign',timing.now().isoformat(),json.dumps(before),json.dumps(after)))
            db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            db.execute('INSERT INTO chore_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))
        return 'Claimed for you today.' if str(target)==str(actor) else 'Assigned for today. Future ownership is unchanged.'

    class MorningMove(discord.ui.Modal):
        def __init__(self,day,qid,expected):
            super().__init__(title='Reschedule this occurrence')
            self.day,self.qid,self.expected=day,qid,expected
            self.when=discord.ui.TextInput(label='New date: YYYY-MM-DD or tomorrow',max_length=20)
            self.add_item(self.when)
        async def on_submit(self,i):
            if i.user.id!=ns['REVIEW_OWNER_ID']:return await i.response.send_message('Only ginaria can sort this list.',ephemeral=True)
            try:
                value=self.when.value.strip().lower();target=timing.now().date()+timedelta(days=1) if value=='tomorrow' else datetime.strptime(value,'%Y-%m-%d').date()
            except ValueError:return await i.response.send_message('Use tomorrow or YYYY-MM-DD.',ephemeral=True)
            if not timing.now().date()<target<=timing.now().date()+timedelta(days=365):return await i.response.send_message('Choose a future date within the next year.',ephemeral=True)
            async with lock:
                q=db.execute('SELECT completed FROM quests WHERE id=?',(self.qid,)).fetchone()
                if ui.snapshot(self.qid)!=self.expected or not q or q[0] or ui.is_archived(self.qid):notice='This chore changed. Nothing was rescheduled.'
                else:
                    with db:
                        db.execute('INSERT OR REPLACE INTO occurrence_moves VALUES(?,?)',(self.qid,target.isoformat()))
                        if timing.policy(self.qid)=='skip':
                            deadline=datetime.combine(target+timedelta(days=1),datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).isoformat()
                            db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(deadline,self.qid))
                    finish_morning_item(self.day,self.qid,'rescheduled');notice=f'Rescheduled for {target:%A, %B %d}.'
                view=MorningTriage(self.day,notice)
            await i.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            if view.done:await publish_morning_summary()

    class MorningAssign(discord.ui.View):
        def __init__(self,day,qid,expected,page=0):
            super().__init__(timeout=None)
            self.day,self.qid,self.expected,self.page=day,qid,expected,page
            q=db.execute('SELECT name FROM quests WHERE id=?',(qid,)).fetchone()
            saved=db.execute('SELECT guild_id FROM chore_board WHERE singleton=1').fetchone();guild=bot.get_guild(int(saved[0])) if saved else None
            ids=ui.workspace.household_people(ns['REVIEW_OWNER_ID'],guild,register=False)
            def label(uid):
                value=ui.workspace.person(uid,guild)
                return ('Account …'+uid[-4:]) if '<@' in value else value
            people=sorted(((uid,label(uid)) for uid in ids),key=lambda value:(value[1].casefold(),int(value[0])))
            size=10;pages=max((len(people)-1)//size+1,1);page=max(0,min(page,pages-1));self.page,self.page_count=page,pages
            description='Choose who owns this occurrence today. Future ownership stays unchanged.'
            if not people:description+=' No household accounts are saved yet; open /chores once in the household server.'
            self.embed=discord.Embed(title='Assign today · '+(q[0] if q else 'Chore unavailable'),description=description,color=0x6B9B77)
            if pages>1:self.embed.set_footer(text=f'Page {page+1} of {pages}')
            async def choose(i,target):
                if not await self.interaction_check(i):return
                member=guild.get_member(int(target)) if guild else None
                if guild and not member:
                    try:member=await asyncio.wait_for(guild.fetch_member(int(target)),timeout=5)
                    except Exception:member=None
                if not member or getattr(member,'bot',False):return await i.response.send_message('That saved account is no longer available in the household server.',ephemeral=True)
                async with lock:
                    notice=assign_morning_occurrence(i.user.id,qid,target,expected)
                    if notice.startswith(('Assigned','Claimed')):finish_morning_item(day,qid,'assigned')
                    view=MorningTriage(day,notice)
                await i.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
                if view.done:await publish_morning_summary()
            for index,(uid,name) in enumerate(people[page*size:(page+1)*size]):
                button=discord.ui.Button(label=name[:80],style=discord.ButtonStyle.secondary,row=index//5,custom_id=f'sprig:morning:{day}:assign:{qid}:{uid}')
                button.callback=lambda i,uid=uid:choose(i,uid);self.add_item(button)
            async def turn(i,new_page):
                if not await self.interaction_check(i):return
                view=MorningAssign(day,qid,expected,new_page)
                await i.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            if pages>1:
                previous=discord.ui.Button(label='Previous',style=discord.ButtonStyle.secondary,row=2,disabled=page==0,custom_id=f'sprig:morning:{day}:assign-prev:{qid}:{page}')
                previous.callback=lambda i:turn(i,page-1);self.add_item(previous)
                next_button=discord.ui.Button(label='Next',style=discord.ButtonStyle.secondary,row=2,disabled=page+1>=pages,custom_id=f'sprig:morning:{day}:assign-next:{qid}:{page}')
                next_button.callback=lambda i:turn(i,page+1);self.add_item(next_button)
            back=discord.ui.Button(label='Back',style=discord.ButtonStyle.secondary,custom_id=f'sprig:morning:{day}:assign-back:{qid}')
            async def go_back(i):
                view=MorningTriage(day)
                await i.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            back.callback=go_back
            self.add_item(back)
        async def interaction_check(self,i):
            if i.user.id!=ns['REVIEW_OWNER_ID']:
                await i.response.send_message('Only ginaria can sort this list.',ephemeral=True);return False
            return True

    class MorningTriage(discord.ui.View):
        def __init__(self,day=None,notice=''):
            super().__init__(timeout=None)
            self.day=day or timing.now().date();key=ensure_morning_day(self.day);item=morning_item(self.day)
            total=db.execute('SELECT COUNT(*) FROM morning_triage_items WHERE day=?',(key,)).fetchone()[0]
            remaining=db.execute("SELECT COUNT(*) FROM morning_triage_items WHERE day=? AND status='pending'",(key,)).fetchone()[0]
            self.done=item is None
            if self.done:
                self.embed=discord.Embed(title='Morning chore sort complete',description=(notice+'\n' if notice else '')+f'All {total} due chore'+('s are' if total!=1 else ' is')+' sorted. Sprig will post the household list after 8:00 a.m. Eastern, or now if it is already later.',color=0x6B9B77);return
            qid,name,frequency,points=item;owner=ui.workspace.ownership(qid)[0]
            self.qid,self.expected=qid,ui.snapshot(qid)
            done_count=total-remaining
            self.embed=discord.Embed(title=f'Morning chore sort · {done_count+1} of {total}',description=(notice+'\n\n' if notice else '')+f'**{name}**\n{timing.label(frequency,qid)} · {points} points\nCurrent owner: {ui.workspace.person(owner) if owner else "Needs someone"}\n\n**Keep** accepts this chore without changing it. **Skip** skips this occurrence. Sprig will open the next due chore automatically.',color=0x6B9B77)
            async def act(i,action):
                if not await self.interaction_check(i):return
                if action=='assign':
                    view=MorningAssign(self.day,qid,self.expected)
                    return await i.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
                if action=='reschedule':return await i.response.send_modal(MorningMove(self.day,qid,self.expected))
                await i.response.defer()
                async with lock:
                    if ui.snapshot(qid)!=self.expected:notice='This chore changed. Review it again.'
                    elif action=='claim':
                        notice=assign_morning_occurrence(i.user.id,qid,i.user.id,self.expected)
                        if notice.startswith('Claimed'):finish_morning_item(self.day,qid,'claimed')
                    elif action=='keep':
                        finish_morning_item(self.day,qid,'kept')
                        notice='Left as is. Its owner, due status, schedule, and points are unchanged.'
                    elif action=='skip':
                        if frequency=='one-time':
                            finish_morning_item(self.day,qid,'skipped_for_today')
                            notice='Skipped for today. This one-time chore stays open and will return in tomorrow’s morning sort unless it is completed or rescheduled.'
                        else:
                            notice=ui.workspace.skip_occurrence(i.user.id,qid,self.expected)
                            if notice.startswith('Occurrence skipped'):finish_morning_item(self.day,qid,'skipped')
                    else:
                        responsible=ui.workspace.ownership(qid)[0] or str(i.user.id)
                        if not complete(qid):notice='Finish the checklist before marking this chore Done.'
                        else:
                            if not ui.workspace.ownership(qid)[0]:assign_morning_occurrence(i.user.id,qid,responsible,self.expected)
                            context=ui.Context(i);context.completion_user_id=responsible;context.allow_proxy_completion=True
                            await bot.get_command('done').callback(context,qid);notice='\n'.join(context.messages)
                            if db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()==(1,):finish_morning_item(self.day,qid,'done')
                    view=MorningTriage(self.day,notice)
                await i.edit_original_response(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
                if view.done:await publish_morning_summary()
            for label,action in [('Claim','claim'),('Assign','assign'),('Done','done'),('Keep','keep'),('Skip','skip'),('Reschedule','reschedule')]:
                button=discord.ui.Button(label=label,style=discord.ButtonStyle.success if action in ('claim','done') else discord.ButtonStyle.danger if action=='skip' else discord.ButtonStyle.secondary,custom_id=f'sprig:morning:{self.day}:{qid}:{action}')
                button.callback=lambda i,action=action:act(i,action);self.add_item(button)
        async def interaction_check(self,i):
            if i.user.id!=ns['REVIEW_OWNER_ID']:
                await i.response.send_message('Only ginaria can sort this private list.',ephemeral=True);return False
            return True

    def morning_batch_valid(day,selected,expected):
        key=day.isoformat() if hasattr(day,'isoformat') else str(day)
        pending={qid for qid, in db.execute("SELECT quest_id FROM morning_triage_items WHERE day=? AND status='pending'",(key,))}
        return bool(selected) and all(qid in pending and ui.snapshot(qid)==expected.get(qid) and not ui.is_archived(qid) and timing.ready(qid) for qid in selected)

    def apply_morning_batch(actor,day,selected,expected,action,target=None):
        selected=tuple(dict.fromkeys(int(qid) for qid in selected))
        if str(actor)!=str(ns['REVIEW_OWNER_ID']):return 0,'Only ginaria can sort the morning chore list.'
        if not morning_batch_valid(day,selected,expected):return 0,'The selected chores changed. Review the refreshed list before trying again.'
        if action=='assign' and not ui.available(target):return 0,'That person is away today. Choose someone who is home.'
        changed=0
        for qid in selected:
            frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()[0]
            if action=='assign':
                notice=assign_morning_occurrence(actor,qid,target,expected[qid])
                if notice.startswith(('Assigned','Claimed')):changed+=finish_morning_item(day,qid,'assigned')
            elif action=='skip':
                if frequency=='one-time':changed+=finish_morning_item(day,qid,'skipped_for_today')
                else:
                    notice=ui.workspace.skip_occurrence(actor,qid,expected[qid])
                    if notice.startswith('Occurrence skipped'):changed+=finish_morning_item(day,qid,'skipped')
            elif action=='keep':changed+=finish_morning_item(day,qid,'kept')
        label={'assign':'assigned','skip':'skipped','keep':'kept'}[action]
        return changed,f'{changed} chore'+('s' if changed!=1 else '')+f' {label}.'

    class MorningBatchAssign(w.View):
        def __init__(self,owner,day,selected,expected,page=0,guild=None,return_page=0):
            super().__init__(owner);self.day,self.selected,self.expected=day,tuple(selected),expected
            ids=ui.workspace.household_people(ns['REVIEW_OWNER_ID'],guild,register=False)
            def label(uid):
                value=ui.workspace.person(uid,guild)
                return ('Account …'+uid[-4:]) if '<@' in value else value
            people=sorted(((uid,label(uid)) for uid in ids),key=lambda value:(value[1].casefold(),int(value[0])))
            size=10;pages=max((len(people)-1)//size+1,1);page=max(0,min(page,pages-1));self.page=page
            self.embed=discord.Embed(title=f'Assign {len(selected)} morning chore'+('s' if len(selected)!=1 else ''),description='Choose one person. Every selected chore is assigned to that person for today only; regular and future ownership stays unchanged.',color=0x6B9B77)
            async def choose(i,target):
                member=guild.get_member(int(target)) if guild else None
                if guild and not member:
                    try:member=await asyncio.wait_for(guild.fetch_member(int(target)),timeout=5)
                    except Exception:member=None
                if not member or getattr(member,'bot',False):return await i.response.send_message('That saved account is no longer available in the household server.',ephemeral=True)
                await i.response.defer()
                async with lock:changed,notice=apply_morning_batch(i.user.id,day,selected,expected,'assign',target)
                view=MorningBatch(owner,day,return_page,guild=guild)
                await w.present(i,view,notice)
                if view.done:await publish_morning_summary()
            for index,(uid,name) in enumerate(people[page*size:(page+1)*size]):
                self.button(name[:80],lambda i,uid=uid:choose(i,uid),row=index//5)
            if pages>1:
                self.button('Previous',lambda i:w.present(i,MorningBatchAssign(owner,day,selected,expected,page-1,i.guild,return_page)),row=2,disabled=page==0)
                self.button('Next',lambda i:w.present(i,MorningBatchAssign(owner,day,selected,expected,page+1,i.guild,return_page)),row=2,disabled=page+1>=pages)
            self.nav(lambda:MorningBatch(owner,day,return_page,selected,guild))

    class MorningBatch(w.View):
        def __init__(self,owner,day=None,page=0,selected=(),guild=None):
            super().__init__(owner);today=timing.now().date();self.day=day if day==today else today;rows=morning_pending(self.day);size=10
            page=max(0,min(page,max((len(rows)-1)//size,0)));chunk=rows[page*size:(page+1)*size]
            self.page,self.done=page,not rows;available={q[0] for q in chunk};selected=tuple(qid for qid in selected if qid in available)
            self.expected={q[0]:ui.snapshot(q[0]) for q in chunk};self.name_ids=[ui.workspace.ownership(q[0])[0] for q in chunk if ui.workspace.ownership(q[0])[0]]
            self.recovery_context={'screen':'morning_batch','day':self.day.isoformat(),'page':page}
            if self.done:
                self.embed=discord.Embed(title='Morning chore sort complete',description='No due chores remain in this sort. Run morning sort from /chores later to reload anything still due.',color=0x6B9B77)
                self.button('Run again',lambda i:self.rerun(i),row=1);self.nav();return
            self.embed=discord.Embed(title=f'Morning chore sort · {len(rows)} left',description='Select several chores on this page, then Skip, Keep, or assign them together. Assign uses one person for the whole selection. One at a time keeps the detailed Claim, Done, and Reschedule choices.',color=0x6B9B77)
            for qid,name,frequency,points in chunk:
                current=ui.workspace.ownership(qid)[0]
                self.embed.add_field(name=w.clean(name,100),value=f'{timing.label(frequency,qid)} · {points} points · '+(ui.workspace.person(current,guild) if current else 'Needs someone'),inline=False)
            picker=discord.ui.Select(placeholder='Choose chores on this page…',min_values=1,max_values=len(chunk),row=0,options=[discord.SelectOption(label=q[1][:100],value=str(q[0]),default=q[0] in selected) for q in chunk])
            async def select(i):await w.present(i,MorningBatch(owner,self.day,page,tuple(int(value) for value in picker.values),i.guild),f'{len(picker.values)} selected.')
            picker.callback=select;self.add_item(picker)
            async def apply(i,action):
                await i.response.defer()
                async with lock:changed,notice=apply_morning_batch(i.user.id,self.day,selected,self.expected,action)
                view=MorningBatch(owner,self.day,page,guild=i.guild)
                await w.present(i,view,notice)
                if view.done:await publish_morning_summary()
            self.button('Assign selected',lambda i:w.present(i,MorningBatchAssign(owner,self.day,selected,{qid:self.expected[qid] for qid in selected},guild=i.guild,return_page=page)),row=1,disabled=not selected)
            self.button('Skip selected',lambda i:apply(i,'skip'),row=1,disabled=not selected)
            self.button('Keep selected',lambda i:apply(i,'keep'),row=1,disabled=not selected)
            self.button('Previous',lambda i:w.present(i,MorningBatch(owner,self.day,page-1,guild=i.guild)),row=2,disabled=page==0)
            self.button('Next',lambda i:w.present(i,MorningBatch(owner,self.day,page+1,guild=i.guild)),row=2,disabled=(page+1)*size>=len(rows))
            async def one_at_a_time(i):
                await w.present(i,w.adapt(MorningTriage(self.day),owner,lambda:MorningBatch(owner,self.day,page,guild=i.guild)))
            self.button('One at a time',one_at_a_time,row=3)
            self.button('Refresh',lambda i:w.present(i,MorningBatch(owner,self.day,page,guild=i.guild)),row=3)
            self.nav()
        async def interaction_check(self,i):
            if i.user.id!=ns['REVIEW_OWNER_ID']:
                await i.response.send_message('Only ginaria can sort this private list.',ephemeral=True);return False
            return await super().interaction_check(i)
        async def rerun(self,i):
            async with lock:count=reopen_morning_day(i.user.id,self.day)
            await w.present(i,MorningBatch(self.owner,self.day,guild=i.guild),f'Reloaded {count} currently due chore'+('s.' if count!=1 else '.'))

    async def publish_morning_summary():
        now=timing.now();key=now.date().isoformat();row=db.execute('SELECT completed_at,shared_status FROM morning_triage_days WHERE day=?',(key,)).fetchone()
        if not row or not row[0] or now.hour<8 or row[1]!='pending':return False
        location=db.execute('SELECT guild_id,channel_id FROM chore_board WHERE singleton=1').fetchone()
        if not location:return False
        with db:
            claimed=db.execute("UPDATE morning_triage_days SET shared_status='sending' WHERE day=? AND shared_status='pending'",(key,)).rowcount
        if not claimed:return False
        try:
            channel=bot.get_channel(int(location[1])) or await asyncio.wait_for(bot.fetch_channel(int(location[1])),timeout=5)
            guild=getattr(channel,'guild',None)
            if str(getattr(channel,'id',''))!=str(location[1]) or str(getattr(guild,'id',''))!=str(location[0]):raise ValueError('Configured morning summary destination changed')
            groups={}
            for qid,name,item_status in db.execute('SELECT i.quest_id,q.name,i.status FROM morning_triage_items i JOIN quests q ON q.id=i.quest_id WHERE i.day=? ORDER BY i.position',(key,)).fetchall():
                q=db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()
                if item_status not in ('claimed','assigned','kept') or not q or q[0] or ui.is_archived(qid) or not timing.ready(qid):continue
                owner=ui.workspace.ownership(qid)[0];groups.setdefault(owner,[]).append(name)
            lines=[f'**Today’s chores · {now:%A, %B} {now.day}**']
            labels={None:'Needs someone'}
            for owner in (uid for uid in groups if uid):
                label=ui.workspace.person(owner,guild)
                if '<@' in label:
                    try:label=await asyncio.wait_for(ns['get_member_name'](SimpleNamespace(guild=guild),owner),timeout=5)
                    except Exception:label='Account '+str(owner)
                labels[owner]=label
            for owner,names in sorted(groups.items(),key=lambda pair:(pair[0] is None,labels[pair[0]].casefold())):
                lines.append('\n**'+labels[owner]+'**')
                lines.extend('• '+discord.utils.escape_markdown(name) for name in names)
            if not groups:lines.append('\nNo chores remain due today.')
            message=await asyncio.wait_for(channel.send('\n'.join(lines),allowed_mentions=discord.AllowedMentions.none()),timeout=10)
            status,message_id='sent',str(message.id)
        except Exception:status,message_id='failed_uncertain',None
        with db:db.execute('UPDATE morning_triage_days SET shared_status=?,shared_message_id=? WHERE day=?',(status,message_id,key))
        return status=='sent'

    registered_morning=set()
    def register_morning_view(day,message_id):
        view=MorningTriage(day)
        key=(str(day),str(message_id),getattr(view,'qid',None))
        if key in registered_morning or view.done:return
        bot.add_view(view,message_id=int(message_id))
        first=MorningAssign(day,view.qid,view.expected)
        bot.add_view(first,message_id=int(message_id))
        for page in range(1,first.page_count):bot.add_view(MorningAssign(day,view.qid,view.expected,page),message_id=int(message_id))
        registered_morning.add(key)

    async def send_morning_triage():
        now=timing.now()
        if now.hour<6:return False
        key=ensure_morning_day(now.date());row=db.execute('SELECT dm_status,completed_at FROM morning_triage_days WHERE day=?',(key,)).fetchone()
        if row[0]=='pending':
            with db:claimed=db.execute("UPDATE morning_triage_days SET dm_status='sending' WHERE day=? AND dm_status='pending'",(key,)).rowcount
            if claimed:
                try:
                    recipient=bot.get_user(ns['REVIEW_OWNER_ID']) or await asyncio.wait_for(bot.fetch_user(ns['REVIEW_OWNER_ID']),timeout=5)
                    view=MorningTriage(now.date())
                    message=await asyncio.wait_for(recipient.send(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none()),timeout=10)
                    status,message_id='sent',str(message.id)
                except Exception:status,message_id='failed_uncertain',None
                with db:db.execute('UPDATE morning_triage_days SET dm_status=?,dm_message_id=? WHERE day=?',(status,message_id,key))
        row=db.execute('SELECT dm_status,dm_message_id FROM morning_triage_days WHERE day=?',(key,)).fetchone()
        if row and row[0]=='sent' and row[1]:
            try:register_morning_view(now.date(),row[1])
            except Exception:
                import logging
                logging.getLogger('discord.sprig').exception('Morning triage recovery registration failed')
        await publish_morning_summary()
        return True

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
            start=datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE'])
            end=start+timedelta(days=7 if flexible else 1)
            if not flexible and q[2]=='daily-am':end=start.replace(hour=12)
            elif not flexible and q[2]=='daily-pm':start=start.replace(hour=12)
            if uid and not ui.attendance.during(uid,start,end):continue
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
                self.embed.add_field(name=w.clean(q[1],100),value=((' · '.join(s.upper()+': '+('Skipped' if ui.dated.skipped(q[0],when.replace(hour=12 if s=='pm' else 0)) else w.clean(w.person(ui.dated.effective_owner(q[0],when.replace(hour=12 if s=='pm' else 0)),guild),65)) for s in ui.repeating.shifts(q[0]))) if ui.dated.slots(q[0])==('am','pm') or ui.repeating.slots(q[0]) else w.clean(w.person(uid,guild),100))+f' · {q[3]} points'+summary(q[0])+(' · ⚠ Away' if away else ''),inline=False)
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

    return SimpleNamespace(help_record=help_record,help_snapshot=help_snapshot,help_summary=help_summary,report_help=report_help,resolve_help=resolve_help,HelpNote=HelpNote,HelpStatus=HelpStatus,HelpHistory=HelpHistory,NeedsHelp=NeedsHelp,duplicate_snapshot=duplicate_snapshot,duplicate=duplicate,DuplicateModal=DuplicateModal,plan=plan,steps=steps,cycle=cycle,checked=checked,complete=complete,summary=summary,history_state=history_state,save_plan=save_plan,PlanModal=PlanModal,Checklist=Checklist,settings=settings,save_reminders=save_reminders,Reminders=Reminders,ReminderTimes=ReminderTimes,send_due_reminders=send_due_reminders,send_morning_triage=send_morning_triage,publish_morning_summary=publish_morning_summary,register_morning_view=register_morning_view,ensure_morning_day=ensure_morning_day,morning_due_records=morning_due_records,morning_item=morning_item,finish_morning_item=finish_morning_item,reopen_morning_day=reopen_morning_day,morning_pending=morning_pending,apply_morning_batch=apply_morning_batch,assign_morning_occurrence=assign_morning_occurrence,MorningTriage=MorningTriage,MorningAssign=MorningAssign,MorningMove=MorningMove,MorningBatch=MorningBatch,MorningBatchAssign=MorningBatchAssign,Calendar=Calendar,Day=Day,project=project,owner_on=owner_on)
