"""A consistent private workspace around the existing household chore rules."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from time import monotonic
import discord
from chore_timing import WEEKDAYS, WEEKLY_FREQUENCIES, DAY_LEGEND, day_badge

OWNER = 301104023405199361


def install(ns, ui, lock):
    bot, db, timing = ns['bot'], ns['db'], ui.timing
    db.executescript('''CREATE TABLE IF NOT EXISTS occurrence_moves(quest_id INTEGER PRIMARY KEY,day TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_preferences(user_id TEXT PRIMARY KEY,trade_dm INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS trade_notifications(trade_id INTEGER PRIMARY KEY,status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chore_shift_splits(original_id INTEGER PRIMARY KEY,pm_id INTEGER UNIQUE NOT NULL);''')
    db.commit()
    original_ready = timing.ready
    def ready(qid):
        move = db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?', (qid,)).fetchone()
        return timing.now().date().isoformat() >= move[0] if move else original_ready(qid)
    timing.ready = ui.ready = ready
    memory = {}
    name_cache = {}

    def clean(value, limit=900):
        return discord.utils.escape_markdown(str(value or ''))[:limit]

    def person(uid, guild=None):
        member = guild.get_member(int(uid)) if guild and uid else None
        cached=name_cache.get((getattr(guild,'id',None),str(uid)))
        return member.display_name if member else (cached[1] if cached else f'<@{uid}>' if uid else 'Needs someone')

    async def prime_names(i,ids):
        if not getattr(i.guild,'get_member',None):return
        gate=asyncio.Semaphore(3)
        async def resolve(uid):
            key=(getattr(i.guild,'id',None),str(uid))
            member=i.guild.get_member(int(uid))
            if member:
                name_cache[key]=(monotonic(),member.display_name)
                return
            if key in name_cache and monotonic()-name_cache[key][0]<300:return
            async with gate:
                try:name=await asyncio.wait_for(ns['get_member_name'](SimpleNamespace(guild=i.guild),uid),timeout=3)
                except Exception:return
                if name and not name.startswith('Unknown user ('):name_cache[key]=(monotonic(),name)
        await asyncio.gather(*(resolve(uid) for uid in set(ids) if uid))

    def chore(qid):
        return db.execute('SELECT id,name,frequency,points,assigned_to,completed,last_completed,reset_after,notes,category FROM quests WHERE id=?', (qid,)).fetchone()

    def ownership(qid, offset=0):
        q = chore(qid)
        if not q: return None, None
        if q[4]: return str(q[4]), 'assignment'
        weekly = ui.weekly_owner(qid, offset)
        if weekly: return str(weekly), 'week1' if offset else 'week0'
        claim = db.execute('SELECT user_id FROM claims WHERE quest_id=?', (qid,)).fetchone() if offset == 0 else None
        return (claim[0], 'occurrence') if claim else (None, None)

    def due_text(q):
        move = db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?', (q[0],)).fetchone()
        if move:
            when = datetime.fromisoformat(move[0])
            return f'Moved occurrence · {day_badge(WEEKDAYS[when.weekday()])} {when:%b %d}'
        if q[5]:
            return 'Completed · returns ' + datetime.fromisoformat(q[7]).strftime('%a %b %d, %I:%M %p') if q[7] else 'Completed · does not repeat'
        if ready(q[0]):
            if q[2] in ('daily-am','daily-pm'):return 'Due now · '+('AM shift' if q[2]=='daily-am' else 'PM shift')
            return 'Due now' + (' · AM slot' if q[2] == 'twice-daily' and timing.now().hour < 12 else ' · PM slot' if q[2] == 'twice-daily' else '')
        state = timing.state(q[0])
        return 'Next due ' + datetime.fromisoformat(state[0]).strftime('%a %b %d') if state else timing.compact_label(q[2])

    class View(discord.ui.View):
        def __init__(self, owner):
            super().__init__(timeout=600)
            self.owner = owner
        async def interaction_check(self, i):
            if i.user.id != self.owner or not ui.allowed(i):
                await i.response.send_message('Open your own private workspace with /chores.', ephemeral=True)
                return False
            return True
        def button(self, label, callback, row=1, primary=False, disabled=False):
            b = discord.ui.Button(label=label, row=row, style=discord.ButtonStyle.primary if primary else discord.ButtonStyle.secondary, disabled=disabled)
            b.callback = callback
            self.add_item(b)
            return b
        def nav(self, back=None):
            if back: self.button('Back', lambda i: present(i, back()), row=4)
            self.button('Dashboard', lambda i: present(i, Dashboard(self.owner, i.guild, i.user)), row=4)
        async def on_error(self, i, error, item):
            import logging
            logging.getLogger('discord.sprig').exception('Workspace action failed', exc_info=error)
            text = 'Check the chore before trying again; an action may already have saved. Reopen /chores if this screen has expired.'
            if i.response.is_done(): await i.followup.send(text, ephemeral=True)
            else: await i.response.send_message(text, ephemeral=True)

    async def present(i, view, notice=None):
        if getattr(view,'name_ids',None):
            task=asyncio.create_task(prime_names(i,view.name_ids))
            finished,_=await asyncio.wait({task},timeout=1.0)
            if not finished and not i.response.is_done():await i.response.defer()
            await task
            if hasattr(view,'rebuild'):view=view.rebuild()
        if hasattr(view, 'owner') and not isinstance(view, View): view = adapt(view, view.owner)
        kwargs = dict(content=None, embeds=[], attachments=[], view=render(view,notice), allowed_mentions=discord.AllowedMentions.none())
        if i.response.is_done(): await i.edit_original_response(**kwargs)
        else: await i.response.edit_message(**kwargs)

    class ResponseProxy:
        def __init__(self, i, owner, back): self.i, self.owner, self.back = i, owner, back
        def __getattr__(self, key): return getattr(self.i.response, key)
        async def send_message(self, *args, **kwargs):
            view = kwargs.get('view')
            if view is None: return await self.i.response.send_message(*args, **kwargs)
            view = adapt(view, self.owner, self.back)
            # Preserve embed-bearing validation/results when they replace the workspace.
            if kwargs.get('embed') is not None: view.embed = kwargs['embed']
            return await present(self.i, view, args[0] if args else kwargs.get('content'))
        async def edit_message(self, **kwargs):
            if kwargs.get('view') is not None:
                view=adapt(kwargs['view'],self.owner,self.back)
                if kwargs.get('embed') is not None:view.embed=kwargs['embed']
                return await present(self.i,view,kwargs.get('content'))
            return await self.i.response.edit_message(**kwargs)
        async def send_modal(self, modal):
            original = modal.on_submit
            async def submit(i): await original(InteractionProxy(i, self.owner, self.back))
            modal.on_submit = submit
            await self.i.response.send_modal(modal)

    class InteractionProxy:
        def __init__(self, i, owner, back):
            self.raw, self.owner, self.back = i, owner, back
            self.response = ResponseProxy(i, owner, back)
        def __getattr__(self, key): return getattr(self.raw, key)
        async def edit_original_response(self, **kwargs):
            if kwargs.get('view') is not None:
                view=adapt(kwargs['view'],self.owner,self.back)
                if kwargs.get('embed') is not None:view.embed=kwargs['embed']
                return await present(self.raw,view,kwargs.get('content'))
            return await self.raw.edit_original_response(**kwargs)

    def adapt(view, owner, back=None):
        if isinstance(view, View) or getattr(view, 'workspace_adapted', False): return view
        view.workspace_adapted = True
        for item in list(view.children):
            if isinstance(item, discord.ui.Button) and item.label in ('Dashboard', 'My chores', 'Back'):
                view.remove_item(item)
                continue
            callback = item.callback
            async def route(i, callback=callback): await callback(InteractionProxy(i, owner, back))
            item.callback = route
        counts = {r: sum(5 if isinstance(c, (discord.ui.Select, discord.ui.UserSelect)) else 1 for c in view.children if c.row == r) for r in range(5)}
        row = next((r for r in (4, 3, 2, 1, 0) if counts[r] <= 3), None)
        if row is not None:
            if back:
                b = discord.ui.Button(label='Back', row=row)
                async def previous(i): await present(i, back())
                b.callback = previous
                view.add_item(b)
            b = discord.ui.Button(label='Dashboard', row=row)
            async def home(i): await present(i, Dashboard(owner, i.guild, i.user))
            b.callback = home
            view.add_item(b)
        return view

    class Dashboard(View):
        def __init__(self, owner, guild=None, member=None):
            super().__init__(owner)
            incoming = db.execute("SELECT COUNT(*) FROM chore_trades WHERE recipient=? AND status='pending'", (str(owner),)).fetchone()[0]
            self.embed = discord.Embed(title='🌱 Your chore workspace', description='Pick a task, then use its chore card. Your controls are private; household changes are shared.\nNeed a hand? Open Help below.', color=0x6B9B77)
            def browse(area):
                saved = memory.get((owner, area), {})
                return Browse(owner, **dict(saved, area=area), guild=guild)
            self.button('My chores', lambda i: present(i, browse('mine')), row=0, primary=True)
            self.button('Pick up chores', lambda i: present(i, browse('pickup')), row=0)
            self.button('Household', lambda i: present(i, browse('household')), row=0)
            self.button('Who’s home?', lambda i: present(i, Trips(owner, i.guild)), row=1)
            self.button('Manage chores', lambda i: present(i, Manage(owner, i.guild)), row=1)
            self.button('Help', lambda i: present(i, Guide(owner)), row=1)
            self.button(f'Trades ({incoming} incoming)', lambda i: present(i, adapt(ui.TradeInboxView(owner), owner)), row=2)
            self.button('Calendar',lambda i:present(i,ui.planning.Calendar(owner,i.guild)),row=3)
            self.button('Needs help',lambda i:present(i,ui.planning.NeedsHelp(owner,i.guild)),row=3)
            self.button('Reminders',lambda i:present(i,ui.planning.Reminders(owner)),row=3)
            self.button('Notifications', lambda i: present(i, Notifications(owner)), row=2)
            self.button('Points & standings',lambda i:present(i,Points(owner,i.guild)),row=2)
            if incoming: self.embed.add_field(name='Waiting for you', value=f'{incoming} incoming trade request(s).', inline=False)
            if owner == OWNER:
                count = db.execute('SELECT COUNT(*) FROM chore_feedback WHERE reviewed=0').fetchone()[0]
                self.button(f'Review inbox ({count})', lambda i: present(i, Inbox(owner, i.guild)), row=2)
            if guild:
                member = member or getattr(guild, 'get_member', lambda uid: None)(owner)
                if member and getattr(getattr(member, 'guild_permissions', None), 'manage_guild', False):
                    self.button('Household setup', lambda i: present(i, adapt(ui.HouseholdSetup(owner), owner)), row=3)
            total = db.execute('SELECT points,streak FROM users WHERE id=?', (str(owner),)).fetchone()
            self.embed.set_footer(text=(f'{total[0]} points · {total[1]} day streak · ' if total else '') + 'Reopen /chores after ten minutes or a restart.')

    class Points(View):
        def __init__(self,owner,guild=None,page=0):
            super().__init__(owner)
            total=db.execute('SELECT points,streak FROM users WHERE id=?',(str(owner),)).fetchone() or (0,0)
            records=db.execute('SELECT id,points FROM users ORDER BY points DESC,id').fetchall()
            page=min(max(page,0),max((len(records)-1)//5,0))
            chunk=records[page*5:(page+1)*5]
            self.name_ids=[r[0] for r in chunk]
            self.rebuild=lambda:Points(owner,guild,page)
            self.embed=discord.Embed(title='Points & standings',description=f'⭐ Your total: **{total[0]} points**\n🔥 Your streak: **{total[1]} day(s)**\nPoints belong to the person who completes the chore. They do not currently redeem rewards.',color=0x6B9B77)
            rank=0;previous=None
            for index,(uid,points) in enumerate(records):
                if points!=previous:rank=index+1
                previous=points
                if page*5<=index<(page+1)*5:
                    self.embed.add_field(name=f'{rank}. '+clean(person(uid,guild),100),value=f'{points} points',inline=False)
            if not records:self.embed.add_field(name='No scores yet',value='Finish a chore to start earning points.')
            if owner==OWNER:self.button('Reset points',lambda i:present(i,ResetPoints(owner,i.guild)),row=2)
            if owner==OWNER:self.button('Reset history / Undo',lambda i:present(i,ResetHistory(owner,i.guild)),row=2)
            if page:self.button('Previous',lambda i:present(i,Points(owner,i.guild,page-1)),row=3)
            if (page+1)*5<len(records):self.button('Next',lambda i:present(i,Points(owner,i.guild,page+1)),row=3)
            self.button('Refresh',lambda i:present(i,Points(owner,i.guild,page)),row=3)
            self.nav()

    def score_rows(target=None):
        return db.execute('SELECT id,points,streak,last_completed FROM users'+(' WHERE id=?' if target else '')+' ORDER BY id', (str(target),) if target else ()).fetchall()

    class ResetPoints(View):
        def __init__(self,owner,guild=None,target=None,reset_streaks=False,confirm=False):
            super().__init__(owner)
            self.target,self.reset_streaks=target,reset_streaks
            self.expected=score_rows(target)
            self.embed=discord.Embed(title='Reset points',color=0x6B9B77)
            if owner!=OWNER:
                self.embed.description='Only ginaria can reset points.'
                self.nav()
                return
            if confirm:
                who=clean(person(target,guild),100) if target else 'Everyone with a saved score'
                self.embed.description=f'Confirm reset for **{who}**: {len(self.expected)} account(s), {sum(r[1] for r in self.expected)} points.\nStreaks: **'+('reset to zero' if reset_streaks else 'keep unchanged')+'**.\nCompletion history and chore responsibilities stay unchanged. Undo is available in reset history only while affected scores remain unchanged; an audit record is kept.'
                self.name_ids=[target] if target else []
                self.rebuild=lambda:ResetPoints(owner,guild,target,reset_streaks,True)
                self.button('Confirm reset',self.apply,row=0,disabled=not self.expected)
                self.button('Cancel',lambda i:present(i,Points(owner,i.guild)),row=0)
            else:
                self.embed.description='Choose one person or everyone, then review the confirmation. Completion history is kept.\nStreaks: **'+('reset too' if reset_streaks else 'keep')+'**.'
                picker=discord.ui.UserSelect(placeholder='Choose one person',min_values=1,max_values=1,row=0)
                async def choose(i):
                    if not await self.interaction_check(i):return
                    chosen=picker.values[0]
                    if getattr(chosen,'bot',False) or not score_rows(chosen.id):
                        await i.response.send_message('Choose a person with a saved score.',ephemeral=True)
                        return
                    await present(i,ResetPoints(owner,i.guild,str(chosen.id),reset_streaks,True))
                picker.callback=choose
                self.add_item(picker)
                self.button('Everyone',lambda i:present(i,ResetPoints(owner,i.guild,None,reset_streaks,True)),row=1)
                self.button('Keep streaks' if reset_streaks else 'Reset streaks too',lambda i:present(i,ResetPoints(owner,i.guild,None,not reset_streaks)),row=1)
                self.nav(lambda:Points(owner,guild))

        async def interaction_check(self,i):
            if self.owner!=OWNER or i.user.id!=OWNER:
                await i.response.send_message('Only ginaria can reset points.',ephemeral=True)
                return False
            return await super().interaction_check(i)

        async def apply(self,i):
            if not await self.interaction_check(i):return
            await i.response.defer()
            async with lock:
                if not self.expected or score_rows(self.target)!=self.expected:
                    await present(i,ResetPoints(self.owner,i.guild),notice='Scores changed. Review a fresh confirmation before resetting.')
                    return
                import json
                with db:
                    details=[]
                    for uid,points,streak,last in self.expected:
                        after=(0,0,None) if self.reset_streaks else (0,streak,last)
                        db.execute('INSERT INTO points_reset_log(actor,user_id,before_state,after_state,created_at) VALUES(?,?,?,?,?)',(str(i.user.id),uid,json.dumps([points,streak,last]),json.dumps(after),timing.now().isoformat()))
                        db.execute('UPDATE users SET points=?,streak=?,last_completed=? WHERE id=?',(*after,uid))
                        epoch=db.execute('SELECT MAX(id) FROM points_reset_log WHERE user_id=?',(uid,)).fetchone()[0]
                        last_event=db.execute('SELECT COALESCE(MAX(id),0) FROM completion_log WHERE user_id=?',(uid,)).fetchone()[0]
                        details.append(dict(uid=uid,before=[points,streak,last],after=list(after),epoch=epoch,last_event=last_event))
                    db.execute('INSERT INTO points_reset_batches(actor,details,created_at) VALUES(?,?,?)',(str(i.user.id),json.dumps(details),timing.now().isoformat()))
                self.expected=[]
            await present(i,Points(self.owner,i.guild),notice='Points reset. '+('Streaks reset too.' if self.reset_streaks else 'Streaks kept.')+' Completion history preserved.')


    def undo_points_reset(actor,batch_id,expected):
        if actor!=OWNER:return 'Only ginaria can undo a points reset.'
        import json
        batch=db.execute('SELECT id,actor,details,created_at,undone_at FROM points_reset_batches WHERE id=?',(batch_id,)).fetchone()
        if not batch or batch!=expected or batch[4]:return 'This reset changed or was already undone. Reopen reset history.'
        details=json.loads(batch[2])
        for entry in details:
            current=db.execute('SELECT points,streak,last_completed FROM users WHERE id=?',(entry['uid'],)).fetchone()
            epoch=db.execute('SELECT COALESCE(MAX(id),0) FROM points_reset_log WHERE user_id=?',(entry['uid'],)).fetchone()[0]
            last_event=db.execute('SELECT COALESCE(MAX(id),0) FROM completion_log WHERE user_id=?',(entry['uid'],)).fetchone()[0]
            if current!=tuple(entry['after']) or epoch!=entry['epoch'] or last_event!=entry['last_event']:
                return 'Someone affected has newer score activity. Nothing restored; undo cannot overwrite later work or another reset.'
        with db:
            for entry in details:
                db.execute('UPDATE users SET points=?,streak=?,last_completed=? WHERE id=?',(*entry['before'],entry['uid']))
                db.execute('INSERT INTO points_reset_log(actor,user_id,before_state,after_state,created_at) VALUES(?,?,?,?,?)',(str(actor),entry['uid'],json.dumps(entry['after']),json.dumps(entry['before']),timing.now().isoformat()))
            db.execute('UPDATE points_reset_batches SET undone_at=? WHERE id=?',(timing.now().isoformat(),batch_id))
            db.execute('INSERT INTO owner_action_log(actor,action,target,details,created_at) VALUES(?,?,?,?,?)',(str(actor),'undo_points_reset',str(batch_id),batch[2],timing.now().isoformat()))
        return 'Points reset undone. The saved totals and streak state were restored together. Completion history is unchanged.'

    class ResetHistory(View):
        def __init__(self,owner,guild=None,page=0):
            super().__init__(owner)
            self.embed=discord.Embed(title='Points reset history',color=0x6B9B77)
            if owner!=OWNER:
                self.embed.description='Only ginaria can view or undo points resets.'
                self.nav()
                return
            import json
            records=db.execute('SELECT id,actor,details,created_at,undone_at FROM points_reset_batches ORDER BY id DESC').fetchall()
            page=min(max(page,0),max(len(records)-1,0))
            if records:
                record=records[page];entries=json.loads(record[2])
                names=', '.join(clean(person(e['uid'],guild),70) for e in entries[:5])
                if len(entries)>5:names+=f' and {len(entries)-5} more'
                self.embed.description=f'Reset #{record[0]} · {record[3][:16]}\n{names}\n{len(entries)} account(s) · {sum(e["before"][0] for e in entries)} points before reset.\n'+('Already undone.' if record[4] else 'Undo restores saved totals and streak state only if none of these people has newer score activity.')
                self.name_ids=[e['uid'] for e in entries[:5]]
                self.rebuild=lambda:ResetHistory(owner,guild,page)
                if not record[4]:
                    async def ask(i):
                        if not await self.interaction_check(i):return
                        async def apply(event):
                            if not await self.interaction_check(event):return
                            await event.response.defer()
                            async with lock:text=undo_points_reset(event.user.id,record[0],record)
                            await present(event,ResetHistory(owner,event.guild,page),text)
                        await present(i,Confirm(owner,'Undo this points reset?',f'Restore {sum(e["before"][0] for e in entries)} points across {len(entries)} account(s): {names}. Saved streak values are restored too. Later score activity blocks the entire undo. Chore history and responsibilities stay unchanged.',apply,lambda:ResetHistory(owner,guild,page)))
                    self.button('Undo points reset',ask,row=0)
                if page:self.button('Previous',lambda i:present(i,ResetHistory(owner,i.guild,page-1)),row=3)
                if page+1<len(records):self.button('Next',lambda i:present(i,ResetHistory(owner,i.guild,page+1)),row=3)
            else:self.embed.description='No recorded points resets yet.'
            self.nav(lambda:Points(owner,guild))
        async def interaction_check(self,i):
            if self.owner!=OWNER or i.user.id!=OWNER:
                await i.response.send_message('Only ginaria can view or undo points resets.',ephemeral=True)
                return False
            return await super().interaction_check(i)


    class Search(discord.ui.Modal):
        def __init__(self, owner, state):
            super().__init__(title='Find chores')
            self.owner, self.state = owner, state
            self.term = discord.ui.TextInput(label='Name or instructions', required=False, default=state.get('query', ''), max_length=100)
            self.add_item(self.term)
        async def on_submit(self, i):
            if not await View(self.owner).interaction_check(i): return
            await present(i, Browse(self.owner, **dict(self.state, query=self.term.value, page=0), guild=i.guild))

    class Browse(View):
        def __init__(self, owner, area='mine', tab=None, page=0, query='', person_id=None, room='', unclaimed=False, group='day', date_filter='', guild=None):
            super().__init__(owner)
            ns['reset_due_quests']()
            tab = tab or ('due' if area in ('mine', 'pickup') else 'week')
            self.state = dict(area=area, tab=tab, page=page, query=query, person_id=person_id, room=room, unclaimed=unclaimed, group=group, date_filter=date_filter)
            offset = 1 if tab == 'next' else 0
            records = [chore(qid) for qid, in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(qid)]
            selected = []
            for q in records:
                uid, scope = ownership(q[0], offset)
                own, due = uid == str(owner), not q[5] and ready(q[0])
                inweek = q[2] not in WEEKLY_FREQUENCIES or timing.in_week(q[2], ui.week_start(offset)) or (offset == 0 and due)
                if area == 'mine':
                    future_own = ownership(q[0], 1)[0] == str(owner)
                    if tab == 'done':
                        if not db.execute('SELECT 1 FROM completion_log WHERE quest_id=? AND user_id=? AND undone_at IS NULL', (q[0], str(owner))).fetchone(): continue
                    elif tab == 'upcoming':
                        if q[5] and not q[7]: continue
                        if not (own or future_own) or (due and own and not future_own): continue
                    elif not own or (tab == 'due' and not due) or (tab == 'week' and not inweek): continue
                elif area == 'pickup':
                    if uid or q[4]: continue
                    if tab == 'due' and not due: continue
                    if tab in ('week', 'next') and (q[2] not in WEEKLY_FREQUENCIES or not inweek): continue
                elif (tab == 'due' and not due) or (tab in ('week', 'next') and not inweek): continue
                if unclaimed and uid: continue
                if person_id is not None and uid != str(person_id): continue
                if room and q[9] != room: continue
                if date_filter:
                    target=datetime.fromisoformat(date_filter).date()
                    move=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(q[0],)).fetchone()
                    if move:
                        if move[0]!=date_filter: continue
                    elif q[2] in ('daily','twice-daily','daily-am','daily-pm'):
                        if q[5] and q[7] and datetime.fromisoformat(q[7]).date()>target: continue
                    elif q[2] in WEEKDAYS or ':' in q[2]:
                        if not timing.matches(target,q[2]): continue
                    else: continue
                if query.casefold() not in (q[1] + ' ' + (q[8] or '')).casefold(): continue
                selected.append(q)
            def groupkey(q):
                if area != 'household' or group == 'chore': return ('Chores A–Z', q[1].casefold())
                if group == 'person': return (person(ownership(q[0], offset)[0], guild), q[1].casefold())
                f = q[2]
                if f in ('daily', 'twice-daily', 'daily-am', 'daily-pm'): return ('Every day', q[1].casefold())
                if f in WEEKDAYS: return (f'{WEEKDAYS.index(f)+1} · {day_badge(f)}', q[1].casefold())
                return (timing.compact_label(f), q[1].casefold())
            selected.sort(key=groupkey)
            self.entries = selected
            rendered = [(groupkey(q)[0],q) for q in selected]
            if area == 'household' and group == 'day':
                rendered = []
                for q in selected:
                    f = q[2]
                    if f in ('daily','twice-daily','daily-am','daily-pm'):
                        rendered.append(('0 · Every day',q))
                    elif f in WEEKDAYS or ':' in f:
                        if not timing.in_week(f,ui.week_start(offset)):
                            rendered.append(('0 · Overdue from an earlier week',q))
                            continue
                        days = f[5:].split(',') if f.startswith('days:') else [f.split(':')[-1]]
                        for day in days:
                            index = WEEKDAYS.index(day)
                            date = ui.week_start(offset)+timedelta(days=index+1)
                            rendered.append((f'{index+1} · {day_badge(day)} {date:%b %d}',q))
                    else: rendered.append(('8 · '+timing.compact_label(f),q))
                rendered.sort(key=lambda r:(r[0],r[1][1].casefold()))
            page = min(max(page, 0), max((len(rendered)-1)//5, 0))
            self.state['page'] = page
            memory[(owner, area)] = dict(self.state)
            self.name_ids=[ownership(q[0],offset)[0] for q in selected]
            self.rebuild=lambda:Browse(owner,**self.state,guild=guild)
            back = lambda: Browse(owner, **self.state, guild=guild)
            chunk = rendered[page*5:(page+1)*5]
            title = {'mine': 'My chores', 'pickup': 'Pick up chores', 'household': 'Household'}[area]
            period = {'due': 'Due now', 'week': 'This week', 'next': 'Next week', 'upcoming': 'Upcoming', 'done': 'Completed', 'all':'All chores'}[tab]
            description = period + f' · {len(selected)} chore(s)' + (' · Search: ' + clean(query, 100) if query else '')
            if date_filter: description+=' · Dated occurrences: '+date_filter
            if tab in ('week','next'):
                description += f'\n{ui.week_start(offset):%b %d}, 6 p.m. → {ui.week_start(offset+1):%b %d}, 6 p.m. Eastern'
            if area=='mine':
                total=db.execute('SELECT points FROM users WHERE id=?',(str(owner),)).fetchone()
                description='⭐ Your total: **'+str(total[0] if total else 0)+' points**\n'+description
            if area == 'mine' and not ui.available(owner): description += '\nYou’re away today. Responsibilities remain saved; review coverage before completing work.'
            self.embed = discord.Embed(title=title, description=description, color=0x6B9B77)
            self.quick_rows=[]
            for heading,q in chunk:
                uid, scope = ownership(q[0], offset)
                heading = (heading + ' · ' if area == 'household' else '') + q[1]
                warning = ui.coverage_warning(q[0], uid, offset) if uid else ''
                status = 'Scheduled next week' if offset else due_text(q)
                if tab=='done':
                    last=db.execute('SELECT completed_at FROM completion_log WHERE quest_id=? AND user_id=? AND undone_at IS NULL ORDER BY id DESC LIMIT 1',(q[0],str(owner))).fetchone()
                    status='Last completed '+last[0][:16].replace('T',' ') if last else status
                self.quick_rows.append((q[0],ui.snapshot(q[0]),tab not in ('next','upcoming','done') and offset==0 and uid==str(owner) and not q[5] and ready(q[0])))
                details=f'{timing.compact_label(q[2])} · {q[3]} points'+ui.planning.summary(q[0])+ui.planning.help_summary(q[0])
                if area=='mine':
                    if tab=='due':
                        slot='AM slot' if q[2]=='twice-daily' and timing.now().hour<12 else 'PM slot' if q[2]=='twice-daily' else ''
                        if slot:details+='\n'+slot
                    else:details+='\n'+status
                else:details+='\n'+clean(person(uid,guild),100)+' · '+status
                if warning:details+='\n⚠ '+clean(warning,180)
                self.embed.add_field(name=clean(heading,200),value=details[:450],inline=False)
            if not chunk: self.embed.add_field(name='Nothing matches', value='Try another tab or clear your filters. Upcoming work and saved responsibilities remain in the other views.')
            if chunk:
                unique = {q[0]:q for heading,q in chunk}
                picker = discord.ui.Select(placeholder='Open a chore card…', row=0, options=[ui.chore_option(q[0], q[1], due_text(q)) for q in unique.values()])
                async def choose(i): await present(i, Card(owner, int(picker.values[0]), back=back, guild=i.guild, offset=offset))
                picker.callback = choose
                self.add_item(picker)
            tabs = [('Due now', 'due'), ('This week', 'week'), ('Next week','next'), ('Upcoming', 'upcoming'), ('Completed', 'done')] if area == 'mine' else [('Due now', 'due'), ('This week', 'week'), ('Next week', 'next'), ('All chores','all')]
            for label, value in tabs:
                async def switch(i, value=value): await present(i, Browse(owner, **dict(self.state, tab=value, page=0), guild=i.guild))
                self.button(label, switch, row=1, primary=value == tab)
            async def search(i): await i.response.send_modal(Search(owner, self.state))
            self.button('Search', search, row=2)
            self.button('Filters', lambda i: present(i, Filters(owner, self.state, i.guild)), row=2)
            if area == 'household':
                self.button('View: ' + group, lambda i: present(i, Groups(owner, self.state, i.guild)), row=2)
                self.button('All' if unclaimed else 'Unclaimed only', lambda i: present(i, Browse(owner, **dict(self.state, unclaimed=not unclaimed, page=0), guild=i.guild)), row=2)
            if page: self.button('Previous', lambda i: present(i, Browse(owner, **dict(self.state, page=page-1), guild=i.guild)), row=3)
            if (page+1)*5 < len(rendered): self.button('Next', lambda i: present(i, Browse(owner, **dict(self.state, page=page+1), guild=i.guild)), row=3)
            self.button('Refresh', lambda i: present(i, Browse(owner, **self.state, guild=i.guild)), row=3)
            self.nav()
            self.embed.set_footer(text=f'Page {page+1} of {max((len(rendered)-1)//5+1,1)} · Eastern time · Weeks change Sunday 6 p.m.')

    class LayoutPanel(discord.ui.LayoutView):
        """V2-only wire layout; the source retains the existing navigation and rules."""
        def __init__(self,source,notice=None):
            super().__init__(timeout=600)
            self.source,self.owner,self.notice=source,source.owner,notice
            embed=getattr(source,'embed',None)
            budget=3900
            def text(value):
                nonlocal budget
                value=str(value or '')
                if not value or budget<=0:return None
                if len(value)>budget:value=value[:max(0,budget-1)]+'…'
                budget-=len(value)
                return discord.ui.TextDisplay(value)
            header=text((('**'+str(notice)+'**\n\n') if notice else '')+(('# '+embed.title+'\n') if embed and embed.title else '')+(embed.description or '' if embed else ''))
            if header:self.add_item(header)
            if embed:
                for index,field in enumerate(embed.fields):
                    content=text('### '+field.name+'\n'+(field.value[:300] if isinstance(source,Browse) else field.value))
                    if not content:break
                    if isinstance(source,Browse) and index<len(source.quick_rows):
                        qid,expected,can_done=source.quick_rows[index]
                        pending_steps=can_done and not ui.planning.complete(qid)
                        button=discord.ui.Button(label='Checklist' if pending_steps else 'Done' if can_done else 'Details',style=discord.ButtonStyle.success if can_done else discord.ButtonStyle.secondary,disabled=can_done and not ui.available(source.owner))
                        async def click(i,qid=qid,expected=expected,can_done=can_done,pending_steps=pending_steps):
                            if not await source.interaction_check(i):return
                            if not can_done:
                                return await present(i,Card(source.owner,qid,lambda:Browse(source.owner,**source.state,guild=i.guild),i.guild,1 if source.state['tab']=='next' else 0))
                            if pending_steps or not ui.planning.complete(qid):return await present(i,ui.planning.Checklist(source.owner,qid,i.guild))
                            async def complete():
                                async with lock:
                                    ns['reset_due_quests']()
                                    if ui.snapshot(qid)!=expected:return 'This occurrence changed. Review the refreshed list.'
                                    context=ui.Context(i)
                                    await bot.get_command('done').callback(context,qid)
                                    return '\n'.join(context.messages)
                            task=asyncio.create_task(complete())
                            finished,_=await asyncio.wait({task},timeout=1.0)
                            if not finished:await i.response.defer()
                            result=await task
                            await present(i,Browse(source.owner,**source.state,guild=i.guild),result[:800])
                        button.callback=click
                        self.add_item(discord.ui.Section(content,accessory=button))
                    else:self.add_item(content)
                footer=text('-# '+embed.footer.text) if embed.footer and embed.footer.text else None
                if footer:self.add_item(footer)
            rows={}
            row_ids={child['custom_id']:index for index,row in enumerate(source.to_components()) for child in row.get('components',[]) if 'custom_id' in child}
            paging=[]
            for item in source.children:
                if isinstance(source,Browse) and isinstance(item,discord.ui.Button) and item.label in ('Previous','Next'):
                    paging.append(item)
                    continue
                row=row_ids.get(item.custom_id,item.row if item.row is not None else 0)
                rows.setdefault(row,[]).append(item)
            if paging:self.add_item(discord.ui.ActionRow(*paging))
            self.add_item(discord.ui.Separator())
            for row,items in sorted(rows.items()):
                self.add_item(discord.ui.ActionRow(*items))

        async def interaction_check(self,i):
            return await self.source.interaction_check(i)

        async def on_error(self,i,error,item):
            await self.source.on_error(i,error,item)

    def render(view,notice=None):
        return view if isinstance(view,LayoutPanel) else LayoutPanel(view,notice)

    def payload(view):
        return dict(view=render(view),allowed_mentions=discord.AllowedMentions.none())

    class Filters(View):
        def __init__(self, owner, state, guild):
            super().__init__(owner)
            self.embed = discord.Embed(title='Filter chores', description='Choose a person or room, or clear the filters.', color=0x6B9B77)
            picker = discord.ui.UserSelect(placeholder='Filter by responsible person', row=0)
            async def by_person(i): await present(i, Browse(owner, **dict(state, person_id=picker.values[0].id, page=0), guild=i.guild))
            picker.callback = by_person
            self.add_item(picker)
            rooms = [r[0] for r in db.execute("SELECT DISTINCT category FROM quests WHERE category IS NOT NULL AND category!='' ORDER BY category")]
            if rooms:
                room_picker = discord.ui.Select(placeholder='Filter by room', row=1, options=[discord.SelectOption(label=r[:100], value=r) for r in rooms[:25]])
                async def by_room(i): await present(i, Browse(owner, **dict(state, room=room_picker.values[0], page=0), guild=i.guild))
                room_picker.callback = by_room
                self.add_item(room_picker)
            self.button('Clear filters', lambda i: present(i, Browse(owner, **dict(state, query='', room='', person_id=None, unclaimed=False, date_filter='', page=0), guild=i.guild)), row=2)
            async def on_date(i): await i.response.send_modal(DateFilter(owner,state))
            self.button('On a date',on_date,row=2)
            self.nav(lambda: Browse(owner, **state, guild=guild))

    class DateFilter(discord.ui.Modal):
        def __init__(self,owner,state):
            super().__init__(title='Filter dated occurrences')
            self.owner,self.state=owner,state
            self.date=discord.ui.TextInput(label='Date, today, or tomorrow; blank clears it',required=False,max_length=20)
            self.add_item(self.date)
        async def on_submit(self,i):
            if not await View(self.owner).interaction_check(i):return
            try: date=parse_date(self.date.value).isoformat() if self.date.value.strip() else ''
            except ValueError:return await i.response.send_message('Use today, tomorrow, or YYYY-MM-DD.',ephemeral=True)
            await present(i,Browse(self.owner,**dict(self.state,date_filter=date,page=0,tab='all'),guild=i.guild))

    class Groups(View):
        def __init__(self, owner, state, guild):
            super().__init__(owner)
            self.embed = discord.Embed(title='Organize the household view', color=0x6B9B77)
            for label, value in [('By person', 'person'), ('By chore', 'chore'), ('By day', 'day')]:
                async def choose(i, value=value): await present(i, Browse(owner, **dict(state, group=value, page=0), guild=i.guild))
                self.button(label, choose)
            self.nav(lambda: Browse(owner, **state, guild=guild))

    def split_daily_shifts(qid,expected):
        existing=db.execute('SELECT pm_id FROM chore_shift_splits WHERE original_id=?',(qid,)).fetchone()
        if existing:return 'Already split into separate AM and PM chores. Nothing duplicated.'
        q=chore(qid)
        if not q or ui.is_archived(qid) or q[2]!='twice-daily' or ui.reassign_snapshot(qid)!=expected:
            return 'This chore changed. Reopen its card before splitting.'
        if db.execute('SELECT 1 FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone():
            return 'Cancel this occurrence’s move before splitting its daily shifts.'
        am_name=q[1][:94]+' · AM';pm_name=q[1][:94]+' · PM'
        names={row[0].casefold() for row in db.execute('SELECT name FROM quests WHERE id!=?',(qid,))}
        if am_name.casefold() in names or pm_name.casefold() in names:
            return 'An AM or PM chore with that name already exists. No changes made.'
        now=timing.now();lasts={'daily-am':None,'daily-pm':None}
        history=[r[0] for r in db.execute('SELECT completed_at FROM completion_log WHERE quest_id=? AND undone_at IS NULL',(qid,))]
        if q[6]:history.append(q[6])
        for value in history:
            try:
                when=datetime.fromisoformat(value)
                if when.tzinfo is None:when=when.replace(tzinfo=ns['QUEST_TIMEZONE'])
                when=when.astimezone(ns['QUEST_TIMEZONE'])
            except (ValueError,TypeError):continue
            shift='daily-am' if when.hour<12 else 'daily-pm'
            if lasts[shift] is None or when>lasts[shift]:lasts[shift]=when
        old_claim=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone()
        keep_claim_on_pm=now.hour>=12 and old_claim and not q[4] and not ui.weekly_owner(qid)
        policy=timing.policy(qid)
        with db:
            db.execute('UPDATE quests SET name=?,frequency=? WHERE id=?',(am_name,'daily-am',qid))
            difficulty=db.execute('SELECT difficulty FROM quests WHERE id=?',(qid,)).fetchone()[0]
            pm_id=db.execute('INSERT INTO quests(name,frequency,points,notes,category,difficulty) VALUES(?,?,?,?,?,?)',(pm_name,'daily-pm',q[3],q[8],q[9],difficulty)).lastrowid
            db.execute('INSERT INTO chore_plans SELECT ?,minutes,steps,revision FROM chore_plans WHERE quest_id=?',(pm_id,qid))
            db.execute('INSERT INTO chore_checklist_revisions SELECT ?,revision FROM chore_checklist_revisions WHERE quest_id=?',(pm_id,qid))
            for key,frequency in [(qid,'daily-am'),(pm_id,'daily-pm')]:
                last=lasts[frequency]
                completed=bool(last and last.date()==now.date())
                timing.initialize(key,frequency)
                reset=timing.calculate_reset(last,frequency) if completed else None
                db.execute('UPDATE quests SET completed=?,last_completed=?,reset_after=? WHERE id=?',(int(completed),last.isoformat() if last else None,reset,key))
                if completed:db.execute('INSERT OR REPLACE INTO chore_timing VALUES(?,?)',(key,reset))
                if policy=='skip':db.execute('INSERT OR REPLACE INTO missed_chore_policy VALUES(?,?,?)',(key,policy,timing.deadline(key,frequency)))
            if keep_claim_on_pm:
                db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
                db.execute('INSERT INTO claims VALUES(?,?)',(pm_id,old_claim[0]))
            db.execute('INSERT INTO chore_shift_splits VALUES(?,?)',(qid,pm_id))
        return 'Split into separate AM and PM chores. Existing weekly/ongoing ownership stays on AM; PM is open except for a current PM single claim. Earned points and old history are unchanged.'

    class Card(View):
        def __init__(self, owner, qid, back=None, guild=None, offset=0, notice=None):
            super().__init__(owner)
            ns['reset_due_quests']()
            q = chore(qid)
            back = back or (lambda: Browse(owner, 'mine', guild=guild))
            self.qid, self.expected = qid, ui.snapshot(qid)
            self.embed = discord.Embed(title=clean(q[1], 200) if q else 'Chore unavailable', description=notice or '', color=0x6B9B77)
            if not q or ui.is_archived(qid):
                self.embed.description = 'This chore is archived or unavailable. Manage chores → Archived chores can restore it.'
                self.nav(back)
                return
            uid, scope = ownership(qid, offset)
            self.name_ids=[uid]
            self.rebuild=lambda:Card(owner,qid,back,guild,offset,notice)
            duration = {'assignment':'Every week · ongoing','week0':'This week · until Sunday 6 p.m.','week1':'Next week · Sunday 6 p.m. to Sunday 6 p.m.','occurrence':'Just this time'}.get(scope, 'Available')
            self.embed.add_field(name='Responsibility', value=f'{clean(person(uid,guild),100)} · {duration}', inline=False)
            self.embed.add_field(name='When', value=f'{timing.label(q[2],qid)}\n{due_text(q)}', inline=False)
            self.embed.add_field(name='Points and room', value=f'{q[3]} points · {clean(q[9] or "Unspecified",100)}', inline=False)
            self.embed.add_field(name='Estimate and checklist',value=(ui.planning.summary(qid).removeprefix(' · ') or 'No estimate or checklist yet'),inline=False)
            help_status=ui.planning.help_record(qid)
            if help_status and not q[5]:self.embed.add_field(name='⚠ '+help_status[4],value=clean(help_status[5],500),inline=False)
            self.button('Stuck / need help',lambda i:present(i,ui.planning.HelpStatus(owner,qid,i.guild)),row=2)
            if ui.planning.steps(qid):self.button('Checklist',lambda i:present(i,ui.planning.Checklist(owner,qid,i.guild)),row=2)
            if q[8]: self.embed.add_field(name='Instructions', value=clean(q[8], 1000), inline=False)
            card = lambda: Card(owner, qid, back, guild, offset)
            async def mutate(i, action):
                async def change():
                    async with lock:
                        ns['reset_due_quests']()
                        if ui.snapshot(qid) != self.expected: return 'This chore changed. Review the refreshed card.'
                        context = ui.Context(i)
                        await bot.get_command(action).callback(context, qid)
                        return '\n'.join(context.messages)
                task=asyncio.create_task(change())
                finished,_=await asyncio.wait({task},timeout=1.0)
                if not finished: await i.response.defer()
                text=await task
                await present(i, Card(owner, qid, back, i.guild, offset, notice=text[:1800]))
            if uid == str(owner) and not q[5] and ready(qid) and offset == 0:
                self.button('Done', lambda i: mutate(i, 'done'), row=0, primary=True, disabled=not ui.available(owner))
            if not uid and not q[5] and ready(qid) and offset == 0:
                self.button('Just this time', lambda i: mutate(i, 'claim'), row=0, primary=True, disabled=not ui.available(owner))
            last_completion=db.execute('SELECT id,quest_id FROM completion_log WHERE user_id=? AND undone_at IS NULL ORDER BY id DESC LIMIT 1',(str(owner),)).fetchone()
            if q[5] and last_completion and last_completion[1]==qid:
                async def undo(i):
                    async def save(event):
                        async with lock: text=ui.undo_completion(owner,last_completion[0])
                        await present(event,card(),text)
                    await present(i,Confirm(owner,'Undo your completion?','This restores the previous chore state and reverses its points and streak changes, if nothing has changed since.',save,card))
                self.button('Undo completion',undo,row=0)
            week_snapshot = tuple(ui.weekly_owner(qid, n) for n in (0, 1))
            if q[2] in WEEKLY_FREQUENCIES and not q[4]:
                for label, week in [('This week', 0), ('Next week', 1)]:
                    current = ui.weekly_owner(qid, week)
                    if current not in (None, str(owner)) or (current is None and not ui.can_take_week(owner, qid, week)): continue
                    if not timing.in_week(q[2],ui.week_start(week)) and not (week==0 and not q[5] and ready(qid)):continue
                    single=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone()
                    if week==0 and single and single[0]!=str(owner): continue
                    async def reserve(i, week=week, current=current):
                        async with lock:
                            if ui.snapshot(qid) != self.expected or tuple(ui.weekly_owner(qid,n) for n in (0,1)) != week_snapshot: text = 'This chore changed. Review the card before reserving it.'
                            elif current == str(owner):
                                with db: db.execute('DELETE FROM week_signups WHERE quest_id=? AND week_start=? AND user_id=?', (qid, ui.week_key(week), str(owner)))
                                text = 'Weekly responsibility released. Earned points stay saved.'
                            else: text = ui.signup(owner, qid, ui.week_key(week))
                        await present(i, Card(owner, qid, back, i.guild, offset, text))
                    self.button(('Release ' if current else 'Take ') + label.lower(), reserve, row=0)
            if not q[4] and uid in (None,str(owner)) and ownership(qid,0)[0] in (None,str(owner)) and not db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,ui.week_key())).fetchone():
                expected_assignment = ui.reassign_snapshot(qid)
                async def ongoing(i):
                    async def save(event):
                        async with lock: text = ui.reassign(qid,owner,'assignment',expected_assignment)
                        await present(event,card(),text)
                    await present(i,Confirm(owner,'Take ongoing responsibility?','This keeps future occurrences assigned to you across weeks, until you drop or reassign it.',save,card))
                self.button('Every week · ongoing',ongoing,row=0)
            options = [('Duplicate chore','duplicate'), ('Estimate / checklist','plan'), ('Give feedback','feedback'), ('Edit chore','edit'), ('Reassign','reassign'), ('Completion history','history')]
            if q[2]=='twice-daily':options.append(('Separate AM and PM sign-ups','split'))
            if not q[5]: options.append(('Move this occurrence','move'))
            if db.execute('SELECT 1 FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone(): options.append(('Cancel occurrence move','unmove'))
            if uid == str(owner) and offset == 0: options.extend([('Drop responsibility','drop'),('Propose trade','trade')])
            if q[2] in ('weekly', *WEEKDAYS): options.append(('Change regular day','day'))
            picker = discord.ui.Select(placeholder='More actions…', row=1, options=[discord.SelectOption(label=l, value=v) for l,v in options])
            async def more(i):
                value = picker.values[0]
                if value == 'duplicate':return await i.response.send_modal(ui.planning.DuplicateModal(owner,qid))
                if value == 'plan':return await i.response.send_modal(ui.planning.PlanModal(owner,qid,card))
                if value == 'history': return await present(i, History(owner, qid, card))
                if value == 'split':
                    expected_split=ui.reassign_snapshot(qid)
                    async def save(event):
                        async with lock:text=split_daily_shifts(qid,expected_split)
                        await present(event,card(),text)
                    return await present(i,Confirm(owner,'Separate morning and evening?',f'This creates two independent  {q[3]}-point daily chores. Existing weekly/ongoing ownership stays on AM. PM starts open, except a current PM single claim moves with it. Earned points and old records stay saved.',save,card))
                if value == 'move': return await i.response.send_modal(MoveModal(owner, qid, self.expected, card))
                if value == 'unmove':
                    async def save(event):
                        async with lock:
                            if ui.snapshot(qid)!=self.expected: text='This occurrence changed. Review the card again.'
                            else:
                                with db:
                                    db.execute('DELETE FROM occurrence_moves WHERE quest_id=?',(qid,))
                                    if timing.policy(qid)=='skip':
                                        db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(timing.deadline(qid,q[2]),qid))
                                text='Occurrence move canceled. The regular schedule applies.'
                        await present(event,card(),text)
                    return await present(i,Confirm(owner,'Cancel this occurrence move?','The chore returns to its regular schedule.',save,card))
                if value == 'feedback': view = ui.FeedbackView(owner, qid)
                elif value == 'edit':
                    ids = [r[0] for r in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(r[0])]
                    view = ui.EditChoreView(owner, ids.index(qid)//20, qid)
                elif value == 'reassign': view = ui.ReassignView(owner, qid=qid, scope=scope, expected=ui.reassign_snapshot(qid))
                elif value == 'drop': view = ui.DropChoreView(owner, qid, ui.snapshot(qid))
                elif value == 'trade': view = ui.TradeOfferView(owner, qid)
                else: view = ui.ChooseDayView(owner, qid, ui.snapshot(qid))
                await present(i, adapt(view, owner, card))
            picker.callback = more
            self.add_item(picker)
            self.nav(back)

    class Confirm(View):
        def __init__(self, owner, title, text, save, back):
            super().__init__(owner)
            self.embed = discord.Embed(title=title, description=text, color=0x6B9B77)
            self.button('Confirm', save, primary=True)
            self.button('Cancel', lambda i: present(i, back()))
            self.nav(back)

    def parse_date(value):
        value = value.strip().lower()
        today = timing.now().date()
        if value in ('today', 'tomorrow'): return today + timedelta(days=value == 'tomorrow')
        for form in ('%Y-%m-%d','%m/%d/%Y','%m/%d'):
            try:
                date = datetime.strptime(value, form).date()
                return date.replace(year=today.year) if form == '%m/%d' else date
            except ValueError: pass
        raise ValueError('Use a date or today/tomorrow')

    class MoveModal(discord.ui.Modal):
        def __init__(self, owner, qid, expected, back):
            super().__init__(title='Move only this occurrence')
            self.owner, self.qid, self.expected, self.back = owner, qid, expected, back
            self.day = discord.ui.TextInput(label='Date: YYYY-MM-DD, today, or tomorrow', max_length=20)
            self.add_item(self.day)
        async def on_submit(self, i):
            if not await View(self.owner).interaction_check(i): return
            try: day = parse_date(self.day.value)
            except ValueError: return await i.response.send_message('Use today, tomorrow, or YYYY-MM-DD.', ephemeral=True)
            if day < timing.now().date() or (day-timing.now().date()).days > 365:
                return await i.response.send_message('Choose today or a date within the next year.', ephemeral=True)
            async def save(event):
                async with lock:
                    q = chore(self.qid)
                    if ui.snapshot(self.qid) != self.expected or not q or q[5] or ui.is_archived(self.qid): text = 'The occurrence changed or is completed. Nothing moved.'
                    else:
                        with db:
                            db.execute('INSERT OR REPLACE INTO occurrence_moves VALUES(?,?)', (self.qid, day.isoformat()))
                            if timing.policy(self.qid)=='skip':
                                deadline=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).isoformat()
                                db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(deadline,self.qid))
                        text = 'Moved only this occurrence. The regular schedule and ownership stay unchanged.'
                await present(event, self.back(), text)
            await present(i, Confirm(self.owner, 'Move this occurrence?', f'{day:%A %B %d} · only this occurrence. Future repeats keep their regular schedule. Weekly ownership still ends at the normal handoff.', save, self.back))

    class History(View):
        def __init__(self, owner, qid, back, page=0):
            super().__init__(owner)
            records = db.execute('SELECT id,user_id,chore_name,points,completed_at,undone_at FROM completion_log WHERE quest_id=? ORDER BY id DESC', (qid,)).fetchall()
            page = min(max(page,0),max((len(records)-1)//5,0))
            chunk = records[page*5:(page+1)*5]
            self.embed = discord.Embed(title='Completion history', description='History begins with this update. Earlier totals stay intact; older individual completions cannot be reconstructed. Undo is available for your most recent recorded completion while its occurrence and points remain unchanged. Ginaria can correct another person’s latest completion with the same safety checks.', color=0x6B9B77)
            for event,uid,name,points,when,undone in chunk:
                self.embed.add_field(name=clean(name,100),value=f'{when[:16].replace("T"," ")} · <@{uid}> · {points} points'+(' · Undone' if undone else ''),inline=False)
            choices = [r for r in chunk if (r[1] == str(owner) or owner==OWNER) and not r[5]]
            if choices:
                picker = discord.ui.Select(placeholder='Choose completion to correct' if owner==OWNER else 'Choose your completion to undo',options=[discord.SelectOption(label=f'{r[4][:16]} · {r[3]} points',value=str(r[0])) for r in choices])
                async def select(i):
                    if not await self.interaction_check(i):return
                    event = int(picker.values[0])
                    async def save(e):
                        if owner==OWNER:
                            if i.user.id!=OWNER or e.user.id!=OWNER or not await View(owner).interaction_check(e):return
                            async with lock:text=ui.owner_undo_completion(e.user.id,event)
                        else:
                            if not await View(owner).interaction_check(e):return
                            async with lock:text=ui.undo_completion(owner,event)
                        await present(e,History(owner,qid,back,page),text)
                    selected=next(r for r in choices if r[0]==event)
                    text=f'This reverses {selected[3]} points for '+clean(person(selected[1]),100)+'. The previous chore responsibility and streak state are restored together. Later work or score changes can block correction.'
                    await present(i,Confirm(owner,'Correct completion?' if owner==OWNER else 'Undo completion?',text,save,lambda:History(owner,qid,back,page)))
                picker.callback = select
                self.add_item(picker)
            if not chunk: self.embed.add_field(name='No recorded completions yet',value='Completions made after this update will appear here.')
            if page: self.button('Previous',lambda i:present(i,History(owner,qid,back,page-1)),row=3)
            if (page+1)*5 < len(records): self.button('Next',lambda i:present(i,History(owner,qid,back,page+1)),row=3)
            self.nav(back)

    class Manage(View):
        def __init__(self, owner, guild=None):
            super().__init__(owner)
            self.embed = discord.Embed(title='Manage chores',description='Everyone can manage shared chores. Open any chore card to edit it. Archiving is reversible.',color=0x6B9B77)
            back = lambda: Manage(owner,guild)
            self.button('Add chore',lambda i:present(i,adapt(ui.AddChoreMenu(owner),owner,back)))
            self.button('Find a chore to edit',lambda i:present(i,Browse(owner,'household',tab='all',guild=i.guild)))
            self.button('Archive chore',lambda i:present(i,adapt(ui.RemoveChoreView(owner),owner,back)))
            self.button('Archived chores',lambda i:present(i,adapt(ui.RemoveChoreView(owner,removed=True),owner,back)))
            self.nav()

    class Notifications(View):
        def __init__(self, owner):
            super().__init__(owner)
            row = db.execute('SELECT trade_dm FROM notification_preferences WHERE user_id=?',(str(owner),)).fetchone()
            enabled = bool(row and row[0])
            self.embed = discord.Embed(title='Private notifications',description='Trade DMs are '+('on' if enabled else 'off')+'. Turning them on authorizes ChoreSprite to DM this account for new trade proposals. Requests always stay on your dashboard. Feedback DMs go to ginaria.',color=0x6B9B77)
            async def toggle(i):
                with db: db.execute('INSERT OR REPLACE INTO notification_preferences VALUES(?,?)',(str(owner),int(not enabled)))
                await present(i,Notifications(owner))
            self.button('Turn trade DMs '+('off' if enabled else 'on'),toggle)
            self.nav()

    async def notify_trade(trade_id):
        row = db.execute("SELECT recipient FROM chore_trades WHERE id=? AND status='pending'",(trade_id,)).fetchone()
        if not row or db.execute('SELECT trade_dm FROM notification_preferences WHERE user_id=?',row).fetchone() != (1,): return
        with db: inserted = db.execute("INSERT OR IGNORE INTO trade_notifications VALUES(?,'sending')",(trade_id,)).rowcount
        if not inserted: return
        async def deliver():
            user = bot.get_user(int(row[0])) or await bot.fetch_user(int(row[0]))
            await user.send('You have a new chore trade proposal. Open /chores in the household server → Trades to review it. Nothing changes until you accept.',allowed_mentions=discord.AllowedMentions.none())
        try:
            await asyncio.wait_for(deliver(),10)
            status = 'sent'
        except Exception: status = 'failed_or_uncertain'
        with db: db.execute('UPDATE trade_notifications SET status=? WHERE trade_id=?',(status,trade_id))

    class Inbox(View):
        def __init__(self, owner, guild=None, page=0, resolved=False):
            super().__init__(owner)
            self.embed = discord.Embed(title='Owner review inbox',color=0x6B9B77)
            if owner != OWNER:
                self.embed.description = 'This inbox belongs to ginaria.'
                self.nav()
                return
            records = db.execute('SELECT f.id,f.quest_id,q.name,f.author_name,f.comment,f.timing,f.suggested_points FROM chore_feedback f JOIN quests q ON q.id=f.quest_id WHERE f.reviewed=? ORDER BY f.id', (int(resolved),)).fetchall()
            page = min(max(page,0),max(len(records)-1,0))
            if records:
                r = records[page]
                self.embed.description = f'{page+1} of {len(records)} '+('resolved' if resolved else 'open')+' reviews · '+clean(r[2],100)
                self.embed.add_field(name='From',value=clean(r[3],100),inline=False)
                if r[4]:
                    escaped = clean(r[4],2000)
                    for at in range(0,len(escaped),900): self.embed.add_field(name='Feedback',value=escaped[at:at+900],inline=False)
                if r[5]: self.embed.add_field(name='Timing',value=clean(r[5]),inline=False)
                if r[6] is not None: self.embed.add_field(name='Suggested points',value=str(r[6]),inline=False)
                async def resolve(i):
                    if not await self.interaction_check(i):return
                    with db: db.execute('UPDATE chore_feedback SET reviewed=1 WHERE id=?',(r[0],))
                    await present(i,Inbox(owner,i.guild,page,resolved))
                if resolved:
                    async def reopen(i):
                        if not await self.interaction_check(i):return
                        async def save(event):
                            if not await self.interaction_check(event):return
                            await event.response.defer()
                            async with lock:
                                with db:
                                    changed=db.execute('UPDATE chore_feedback SET reviewed=0 WHERE id=? AND reviewed=1',(r[0],)).rowcount
                                    if changed:db.execute('INSERT INTO owner_action_log(actor,action,target,details,created_at) VALUES(?,?,?,?,?)',(str(event.user.id),'reopen_review',str(r[0]),'Resolved review returned to the open inbox; no notification sent.',timing.now().isoformat()))
                            await present(event,Inbox(owner,event.guild,page,True),'Review reopened in the open inbox.' if changed else 'This review is already open. Nothing changed.')
                        await present(i,Confirm(owner,'Reopen this review?',clean(r[2],100)+' · '+clean(r[3],100)+'. Return this saved review to the open inbox without sending another DM.',save,lambda:Inbox(owner,guild,page,True)))
                    self.button('Reopen review',reopen,primary=True)
                else:self.button('Resolve and next',resolve,primary=True)
                self.button('Open chore',lambda i:present(i,Card(owner,r[1],lambda:Inbox(owner,guild,page,resolved),i.guild)))
                if not ui.is_archived(r[1]):
                    ids = [v[0] for v in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(v[0])]
                    self.button('Edit chore',lambda i:present(i,adapt(ui.EditChoreView(owner,ids.index(r[1])//20,r[1]),owner,lambda:Inbox(owner,guild,page,resolved))))
                if page: self.button('Previous',lambda i:present(i,Inbox(owner,i.guild,page-1,resolved)),row=3)
                if page+1 < len(records): self.button('Next',lambda i:present(i,Inbox(owner,i.guild,page+1,resolved)),row=3)
            else: self.embed.description = 'No resolved reviews yet.' if resolved else 'All caught up. Resolved reviews stay saved on each chore.'
            self.button('Open reviews' if resolved else 'Resolved reviews',lambda i:present(i,Inbox(owner,i.guild,0,not resolved)),row=2)
            self.button('Refresh',lambda i:present(i,Inbox(owner,i.guild,page,resolved)),row=3)
            self.nav()
        async def interaction_check(self,i):
            if self.owner != OWNER or i.user.id != OWNER:
                await i.response.send_message('The review inbox is for ginaria.',ephemeral=True)
                return False
            return await super().interaction_check(i)

    def save_trip(people, first, last, state, note, editing=None, expected=None):
        people = list(dict.fromkeys(str(p) for p in people))
        if not people or state not in ('home','away') or last < first or (last-first).days > 365:
            return 'Choose people and a date range of at most 366 days.'
        if editing:
            current = db.execute('SELECT id,user_id,start_date,end_date,state,note,active FROM availability_exceptions WHERE id=?',(editing,)).fetchone()
            if current != expected or not current[6] or people != [current[1]]: return 'This exception changed. Reopen it before saving.'
        duplicates = []
        for uid in people:
            overlap = db.execute('SELECT id,start_date,end_date,state,note FROM availability_exceptions WHERE user_id=? AND active=1 AND start_date<=? AND end_date>=? AND id!=?',(uid,last.isoformat(),first.isoformat(),editing or -1)).fetchall()
            if len(overlap) == 1 and overlap[0][1:] == (first.isoformat(),last.isoformat(),state,note.strip()[:300]): duplicates.append(uid)
            elif overlap: return 'These dates overlap another exception. Open that exception and Edit dates instead.'
        if len(duplicates) == len(people): return 'Those exceptions are already saved. Nothing duplicated.'
        with db:
            if editing: db.execute('UPDATE availability_exceptions SET active=0 WHERE id=?',(editing,))
            for uid in people:
                if uid not in duplicates:
                    db.execute('INSERT INTO availability_exceptions(user_id,start_date,end_date,state,note) VALUES(?,?,?,?,?)',(uid,first.isoformat(),last.isoformat(),state,note.strip()[:300]))
        return 'Saved. The normal rotation resumes afterward. Responsibilities stayed saved; check Household for coverage.'

    class TripModal(discord.ui.Modal):
        def __init__(self, owner, people, state, back, first='', last='', editing=None, expected=None):
            super().__init__(title='Edit dates' if editing else 'Plan home or away dates')
            self.owner,self.people,self.state,self.back = owner,people,state,back
            self.editing,self.expected = editing,expected
            self.first = discord.ui.TextInput(label='First day: today, tomorrow, or YYYY-MM-DD',default=first,max_length=20)
            self.last = discord.ui.TextInput(label='Last day included',default=last,max_length=20)
            self.note = discord.ui.TextInput(label='Reason (optional)',required=False,default=expected[5] if expected else '',max_length=300)
            for item in (self.first,self.last,self.note): self.add_item(item)
        async def on_submit(self,i):
            if not await View(self.owner).interaction_check(i): return
            try: first,last = parse_date(self.first.value),parse_date(self.last.value)
            except ValueError: return await i.response.send_message('Use today, tomorrow, YYYY-MM-DD, or MM/DD/YYYY.',ephemeral=True)
            if last < first or (last-first).days > 365:
                return await i.response.send_message('Last day must be on or after the first, within 366 days.',ephemeral=True)
            async def save(event):
                async with lock: text = save_trip(self.people,first,last,self.state,self.note.value,self.editing,self.expected)
                await present(event,self.back(),text)
            await present(i,Confirm(self.owner,'Confirm date changes',f'{len(self.people)} person(s) · {self.state.upper()}\n{first:%A %b %d, %Y} through {last:%A %b %d, %Y}, inclusive full Eastern days.\nExisting chores stay assigned; review coverage afterward.',save,self.back))

    class Trips(View):
        def __init__(self, owner, guild=None, people=None, page=0):
            super().__init__(owner)
            people = people or []
            self.people = people
            self.name_ids=people
            self.rebuild=lambda:Trips(owner,guild,people,page)
            back = lambda: Trips(owner,guild,people,page)
            self.embed = discord.Embed(title='Who’s home? · trips and traded days',description='Select everyone whose dates change. Add an exception, or edit a saved one directly. Full Eastern calendar days; Sunday handoff stays at 6 p.m.',color=0x6B9B77)
            picker = discord.ui.UserSelect(placeholder='Choose one or more people',min_values=1,max_values=10,row=0)
            async def choose(i):
                members = picker.values
                if any(m.bot or getattr(getattr(m,'guild',None),'id',None) != i.guild_id for m in members):
                    return await i.response.send_message('Choose household people, not bots.',ephemeral=True)
                await present(i,Trips(owner,i.guild,[str(m.id) for m in members]))
            picker.callback = choose
            self.add_item(picker)
            if people:
                self.embed.add_field(name='Selected',value=', '.join(clean(person(uid,guild),100) for uid in people),inline=False)
                for label,state in [('Mark home','home'),('Mark away','away')]:
                    async def add(i,state=state): await i.response.send_modal(TripModal(owner,people,state,back))
                    self.button(label,add,row=1)
                shortcuts = discord.ui.Select(placeholder='Quick dates…',row=2,options=[discord.SelectOption(label=l,value=v) for l,v in [('Away today','today'),('Away tomorrow','tomorrow'),('Away this weekend','weekend')]])
                async def quick(i):
                    day,value = timing.now().date(),shortcuts.values[0]
                    first = day+timedelta(days=1 if value == 'tomorrow' else 0 if value=='weekend' and day.weekday()==6 else (5-day.weekday())%7 if value == 'weekend' else 0)
                    last = first+timedelta(days=1 if value == 'weekend' and first.weekday()==5 else 0)
                    await i.response.send_modal(TripModal(owner,people,'away',back,first.isoformat(),last.isoformat()))
                shortcuts.callback = quick
                self.add_item(shortcuts)
                records = db.execute('SELECT id,user_id,start_date,end_date,state,note,active FROM availability_exceptions WHERE active=1 AND user_id IN ('+','.join('?' for _ in people)+') ORDER BY start_date,id',people).fetchall()
                page = min(max(page,0),max((len(records)-1)//10,0))
                chunk = records[page*10:(page+1)*10]
                if chunk:
                    saved = discord.ui.Select(placeholder='Open a saved exception to edit or cancel',row=3,options=[discord.SelectOption(label=(person(r[1],guild)+' · '+r[2]+' → '+r[3]+' · '+r[4])[:100],value=str(r[0])) for r in chunk])
                    async def open_saved(i):
                        record = next(r for r in chunk if r[0] == int(saved.values[0]))
                        await present(i,ExceptionCard(owner,record,back))
                    saved.callback = open_saved
                    self.add_item(saved)
                self.button('Weekly attendance',lambda i:present(i,adapt(ui.AttendanceView(owner,member_id=int(people[0]),member_name=person(people[0],guild)),owner,back)),row=1)
                if page: self.button('Previous',lambda i:present(i,Trips(owner,i.guild,people,page-1)),row=4)
                if (page+1)*10 < len(records): self.button('Next',lambda i:present(i,Trips(owner,i.guild,people,page+1)),row=4)
            self.nav()

    class ExceptionCard(View):
        def __init__(self,owner,record,back):
            super().__init__(owner)
            self.embed = discord.Embed(title='Saved date exception',description=f'{record[2]} → {record[3]} · {record[4]}\n'+clean(record[5]),color=0x6B9B77)
            async def edit(i): await i.response.send_modal(TripModal(owner,[record[1]],record[4],back,record[2],record[3],record[0],record))
            self.button('Edit dates',edit)
            async def cancel(i):
                async def save(event):
                    async with lock:
                        current = db.execute('SELECT id,user_id,start_date,end_date,state,note,active FROM availability_exceptions WHERE id=?',(record[0],)).fetchone()
                        if current != record: text = 'This exception changed. Nothing canceled.'
                        else:
                            with db: db.execute('UPDATE availability_exceptions SET active=0 WHERE id=?',(record[0],))
                            text = 'Exception canceled; history and responsibilities remain.'
                    await present(event,back(),text)
                await present(i,Confirm(owner,'Cancel this exception?','Normal rotation applies again for these dates.',save,back))
            self.button('Cancel exception',cancel)
            self.nav(back)

    TOPICS = {
        'Start here':'My chores shows your points total, Due now, This week, Upcoming, and Completed. Points & standings on the dashboard shows scores without commands. Pick up chores lets you take work just once or for a week. Household shows everyone’s work; every chore opens the same card.',
        'Taking responsibility':'Just this time takes one due occurrence. Take this week / next week reserves repeating work until Sunday 6 p.m. An ongoing assignment continues across weeks. Drop and Reassign show scope before saving. Trades change nothing until accepted.',
        'Dates and colors':DAY_LEGEND+'\nAll times are Eastern. Daily resets at midnight, twice daily at noon and midnight, weekly Sunday 6 p.m., monthly on the first. Flexible weekly/monthly markers do not imply a weekday.',
        'Schedules and missed work':'Daily AM and Daily PM can have different weekly owners. A twice-daily chore card offers Separate AM and PM sign-ups. Change regular day changes future weeks. Move this occurrence changes one unfinished occurrence. Edit chore → Missed chores chooses Keep overdue or Skip if missed. Notes such as “afternoon” are instructions, not automatic reminders.',
        'Trips and traded days':'Who’s home? accepts multiple people, date shortcuts, and full-day ranges. Preview before confirming. Edit saved exceptions directly. Normal rotation resumes afterward; existing responsibilities remain saved. Base home/away chore schedules do not shift with a person’s trip.',
        'Feedback and points':'Give feedback on a chore card to suggest timing, instructions, or points. Ginaria receives feedback DMs and resolves reviews in the owner inbox. Everyone can discuss; only ginaria resolves. Suggestions never apply themselves. Edits affect future points, not points already earned.',
        'History and mistakes':'Done awards points once per occurrence. Completion history records work after this update. Undo your most recent recorded completion only while its state and points remain unchanged. Undo reverses its points and streak changes. Earlier totals remain intact.',
        'Managing chores':'Manage chores groups Add and Archive/Restore. Edit any chore from its card. Room is optional and can be used as a filter. Archiving hides work and keeps records; restoring retains its state.',
        'Planning and reminders':'Calendar previews scheduled chores by week or month; No fixed day keeps flexible work separate. Chore cards offer estimates and per-occurrence checklists. Finish steps before Done. Reminders are personal, off by default, with up to three Eastern times and an off switch.',
        'Help statuses and copies':'Stuck / need help on a chore lets its current responsible person explain the obstacle. Everyone sees active issues under Needs help and can confirm resolution without completing or dropping work. Status history keeps older notes. Duplicate chore copies settings into a fresh unassigned chore after reviewing a new name.',
        'Points and resets':'Points & standings shows your total and streak. Only ginaria can reset one person or everyone, with confirmation and optional streak reset. History stays saved. Ginaria can undo a reset from Reset history / Undo while affected scores have no newer activity.',
        'Notifications and recovery':'Trades appear on the dashboard. Trade DMs are optional: turn them on in Notifications for your own account. Feedback DMs go to ginaria. Reopen /chores after a restart or ten minutes. Private controls edit shared household information.'}

    class Guide(View):
        def __init__(self,owner,topic='Start here'):
            super().__init__(owner)
            self.embed = discord.Embed(title=topic,description=TOPICS[topic],color=0x6B9B77)
            picker = discord.ui.Select(placeholder='What would you like to do?',options=[discord.SelectOption(label=k,value=k,default=k==topic) for k in TOPICS])
            async def choose(i): await present(i,Guide(owner,picker.values[0]))
            picker.callback = choose
            self.add_item(picker)
            self.nav()

    return SimpleNamespace(Confirm=Confirm,clean=clean,person=person,undo_points_reset=undo_points_reset,ResetHistory=ResetHistory,ResetPoints=ResetPoints,split_daily_shifts=split_daily_shifts,Points=Points,LayoutPanel=LayoutPanel,render=render,payload=payload,Dashboard=Dashboard,Browse=Browse,Card=Card,Inbox=Inbox,Trips=Trips,Guide=Guide,Manage=Manage,History=History,Notifications=Notifications,MoveModal=MoveModal,TripModal=TripModal,View=View,adapt=adapt,present=present,save_trip=save_trip,parse_date=parse_date,ownership=ownership,notify_trade=notify_trade,memory=memory)
