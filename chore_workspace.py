"""A consistent private workspace around the existing household chore rules."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from time import monotonic
import discord
from chore_pages import PagePlan, page_spec, list_capacity
from chore_timing import WEEKDAYS, WEEKLY_FREQUENCIES, SCHEDULED, DAILY_SHIFTS, DAY_LEGEND, day_badge

OWNER = 301104023405199361


def action_style(label, fallback=discord.ButtonStyle.secondary):
    """Use the same supported Discord color for the same kind of action."""
    label=str(label)
    if label=='Dashboard':return discord.ButtonStyle.primary
    if label in ('Home today','Claim','Claim just this time','Just this occurrence','Done','Mark done') or label.startswith(('Save ','Checked: ')):
        return discord.ButtonStyle.success
    if label in ('Away today','Skip','Skip this occurrence','Skip just this time') or label.startswith(('Undo','Drop ')):
        return discord.ButtonStyle.danger
    return fallback


def install(ns, ui, lock):
    bot, db, timing = ns['bot'], ns['db'], ui.timing
    db.executescript('''CREATE TABLE IF NOT EXISTS occurrence_moves(quest_id INTEGER PRIMARY KEY,day TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_preferences(user_id TEXT PRIMARY KEY,trade_dm INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS workspace_preferences(user_id TEXT PRIMARY KEY,list_size INTEGER NOT NULL CHECK(list_size BETWEEN 1 AND 10));
    CREATE TABLE IF NOT EXISTS trade_notifications(trade_id INTEGER PRIMARY KEY,status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chore_shift_splits(original_id INTEGER PRIMARY KEY,pm_id INTEGER UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS attention_windows(quest_id INTEGER PRIMARY KEY,cycle TEXT NOT NULL,deadline TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS occurrence_skips(id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL,actor TEXT NOT NULL,skipped_at TEXT NOT NULL,next_due TEXT NOT NULL,previous_state TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS skip_undo_state(skip_id INTEGER PRIMARY KEY,expected TEXT NOT NULL,previous_policy TEXT NOT NULL,undone_at TEXT);''')
    db.execute("CREATE TABLE IF NOT EXISTS person_colors(user_id TEXT PRIMARY KEY,color TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS household_identities(role TEXT PRIMARY KEY CHECK(role IN ('kas','zel')),user_id TEXT UNIQUE NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS household_profiles(user_id TEXT PRIMARY KEY,display_name TEXT NOT NULL DEFAULT '',icon TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 0)")
    db.commit()
    COLORS={'lavender':('🟣','Lavender'),'blue':('🔵','Blue'),'pink':('🩷','Pink'),'orange':('🟠','Orange'),'green':('🟢','Green'),'yellow':('🟡','Yellow'),'red':('🔴','Red'),'white':('⚪','White'),'black':('⚫','Black'),'brown':('🟤','Brown'),'star':('🌟','Star'),'flower':('🌸','Flower'),'leaf':('🍃','Leaf'),'moon':('🌙','Moon'),'paws':('🐾','Paw prints'),'none':('','No marker')}
    def color_key(uid,guild=None,name=None):
        saved=db.execute('SELECT color FROM person_colors WHERE user_id=?',(str(uid),)).fetchone()
        if saved and saved[0] in COLORS:return saved[0]
        if str(uid)==str(OWNER):return 'green'
        member=guild.get_member(int(uid)) if guild and uid else None
        aliases={str(v).strip().casefold() for v in (name,getattr(member,'display_name',None),getattr(member,'name',None)) if v}
        defaults={'dar':'lavender','john':'blue','kas':'pink','z':'orange','zel':'orange'}
        return next((defaults[a] for a in defaults if a in aliases),'none')
    def page_size(owner):
        row=db.execute('SELECT list_size FROM workspace_preferences WHERE user_id=?',(str(owner),)).fetchone()
        return min(row[0],5) if row and isinstance(row[0],int) and 1<=row[0]<=10 else 5

    def sheet_size(owner):
        row=db.execute('SELECT list_size FROM workspace_preferences WHERE user_id=?',(str(owner),)).fetchone()
        return row[0] if row and isinstance(row[0],int) and 1<=row[0]<=10 else 8

    original_ready = timing.ready
    def ready(qid, initialize=True):
        if ui.dated.skipped(qid):return False
        move = db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?', (qid,)).fetchone()
        if initialize:
            due=original_ready(qid) if not move else timing.now().date().isoformat()>=move[0]
        else:
            state=timing.state(qid)
            q=chore(qid)
            now=timing.now()
            due=not state or now>=datetime.fromisoformat(state[0])
            if not state and q:
                if q[2] in SCHEDULED:due=now>=timing.next_due(now,q[2])
                elif q[2]=='daily-am':due=now.hour<12
                elif q[2]=='daily-pm':due=now.hour>=12
            if move:due=now.date().isoformat()>=move[0]
        if not due:return False
        uid=ownership(qid)[0]
        if not uid:return True
        now=timing.now()
        if not ui.attendance.at(uid,now):return False
        q=chore(qid)
        start=now.replace(hour=0,minute=0,second=0,microsecond=0)
        if q[2] in SCHEDULED:
            for offset in range(29):
                candidate=start-timedelta(days=offset)
                if timing.matches(candidate.date(),q[2]):
                    start=candidate
                    break
            else:return False
        elif q[2] not in ('daily','twice-daily',*DAILY_SHIFTS):
            return True
        if q[2]=='daily-pm' or (q[2]=='twice-daily' and now.hour>=12):start=start.replace(hour=12)
        end=(start.replace(hour=0)+timedelta(days=1)) if q[2]!='daily-am' and not (q[2]=='twice-daily' and now.hour<12) else start.replace(hour=12)
        return ui.attendance.during(uid,start,end)
    timing.ready = ui.ready = ready
    memory = {}
    name_cache = {}

    def clean(value, limit=900):
        return discord.utils.escape_markdown(str(value or ''))[:limit]

    def person(uid, guild=None):
        member = guild.get_member(int(uid)) if guild and uid else None
        cached=name_cache.get((getattr(guild,'id',None),str(uid)))
        if cached is None and guild is None:
            saved=db.execute('SELECT guild_id FROM chore_board WHERE singleton=1').fetchone()
            if saved:cached=name_cache.get((int(saved[0]),str(uid)))
        name=member.display_name if member else (cached[1] if cached else f'<@{uid}>' if uid else 'Needs someone')
        profile=db.execute('SELECT display_name,icon FROM household_profiles WHERE user_id=?',(str(uid),)).fetchone() if uid else None
        marker=COLORS[color_key(uid,guild,name)][0] if uid else ''
        if profile and profile[0]:name=profile[0]
        icon=profile[1] if profile else ''
        return ' '.join(v for v in (marker,icon,name) if v)

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
        dated=ui.dated.owner(qid) if offset==0 else None
        if dated:return dated,'dated'
        if q[4]: return str(q[4]), 'assignment'
        weekly = ui.weekly_owner(qid, offset)
        if weekly: return str(weekly), 'week1' if offset else 'week0'
        claim = db.execute('SELECT user_id FROM claims WHERE quest_id=?', (qid,)).fetchone() if offset == 0 else None
        if claim:return claim[0],'occurrence'
        recurring=ui.repeating.owner(qid,ui.week_start(offset)+timedelta(days=1) if offset else None)
        return (recurring,'repeating') if recurring else (None,None)

    def due_text(q):
        uid=ownership(q[0])[0]
        if uid and not ui.attendance.at(uid,timing.now()):return 'Paused while away; responsibility saved'
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
            b = discord.ui.Button(label=str(label)[:80], row=row, style=action_style(label,discord.ButtonStyle.primary if primary else discord.ButtonStyle.secondary), disabled=disabled)
            b.callback = callback
            self.add_item(b)
            return b
        def nav(self, back=None):
            self.recovery_parent = back
            if back: self.button('Back', lambda i: present(i, back()), row=4)
            self.button('Dashboard', lambda i: present(i, Dashboard(self.owner, i.guild, i.user)), row=4)
        async def on_error(self, i, error, item):
            import logging
            logging.getLogger('discord.sprig').exception('Workspace action failed', exc_info=error)
            text = 'An action may already have saved. Use Refresh to check the current state before trying again; it never repeats the old action.'
            if i.response.is_done(): await i.followup.send(text, ephemeral=True)
            else: await i.response.send_message(text, ephemeral=True)

    async def present(i, view, notice=None):
        while isinstance(i,InteractionProxy):i=i.raw
        view._choice_guild=i.guild
        drafts=getattr(view,'_choice_drafts',{})
        pages=getattr(view,'_choice_pages',{})
        if getattr(view,'name_ids',None):
            task=asyncio.create_task(prime_names(i,view.name_ids))
            finished,_=await asyncio.wait({task},timeout=1.0)
            if not finished and not i.response.is_done():await i.response.defer()
            await task
            if hasattr(view,'rebuild'):
                view=view.rebuild();view._choice_drafts=drafts;view._choice_pages=pages;view._choice_guild=i.guild
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
        if isinstance(view, (View,LayoutPanel)) or getattr(view, 'workspace_adapted', False): return view
        view.workspace_adapted = True
        view.recovery_parent = back
        if not getattr(view,'embed',None):
            headings={
                'AddChoreMenu':('Chore schedule','Choose how often the chore repeats, then fill in its details.'),
                'WeekdayMenu':('Choose a weekday','Choose the regular day for this chore.'),
                'RepeatMenu':('Repeat days','Choose the days and repeating pattern.'),
                'HouseholdSetup':('Household setup','Select Kas and Zel’s accounts, then Save household. Weeks change Sunday at 6 p.m. Eastern.')}
            heading=headings.get(type(view).__name__)
            if heading:view.embed=discord.Embed(title=heading[0],description=heading[1],color=0x6B9B77)
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
            b = discord.ui.Button(label='Dashboard', row=row, style=discord.ButtonStyle.primary)
            async def home(i): await present(i, Dashboard(owner, i.guild, i.user))
            b.callback = home
            view.add_item(b)
        return view

    class ListLength(View):
        def __init__(self,owner):
            super().__init__(owner)
            self.recovery_context={'screen':'list_length'}
            self.embed=discord.Embed(title='Your list length',description=f'**{sheet_size(owner)} items per page**\nChoose 1–10 items. This applies to your chore lists, calendar days, standings, and paged history. It changes only your display; chores and points stay as they are. Navigation buttons stay visible below the list.',color=0x6B9B77)
            picker=discord.ui.Select(placeholder='Items per page',options=[discord.SelectOption(label=f'{n} items'+(' · default' if n==8 else ''),value=str(n),default=n==sheet_size(owner)) for n in range(1,11)])
            async def save(i):
                if not await self.interaction_check(i):return
                try:value=int(picker.values[0])
                except (ValueError,IndexError):return await i.response.send_message('Choose a list length from 1 to 10.',ephemeral=True)
                if not 1<=value<=10:return await i.response.send_message('Choose a list length from 1 to 10.',ephemeral=True)
                async with lock:
                    with db:db.execute('INSERT OR REPLACE INTO workspace_preferences VALUES(?,?)',(str(owner),value))
                await present(i,ListLength(owner),'List length saved for your account.')
            picker.callback=save;self.add_item(picker)
            self.nav()

    class HouseholdAdmin(View):
        async def interaction_check(self,i):
            if not await super().interaction_check(i):return False
            if not getattr(getattr(i.user,'guild_permissions',None),'manage_guild',False):
                await i.response.send_message('Household setup is managed by a server administrator.',ephemeral=True)
                return False
            return True

    def profile_snapshot(uid):
        return (db.execute('SELECT display_name,icon,revision FROM household_profiles WHERE user_id=?',(str(uid),)).fetchone(),
                db.execute('SELECT color FROM person_colors WHERE user_id=?',(str(uid),)).fetchone())

    def save_profile(uid,name,icon,color,expected):
        uid=str(uid);name=str(name).strip();icon=str(icon).strip()
        if not uid.isdecimal() or len(name)>60 or len(icon)>16 or any(ord(c)<32 for c in name+icon) or color not in COLORS:
            return 'Choose a listed color, a single-line name up to 60 characters, and an icon up to 16 characters.'
        if profile_snapshot(uid)!=expected:return 'This person’s settings changed. Reopen their profile before saving.'
        with db:
            row=expected[0];revision=(row[2] if row else 0)+1
            db.execute('INSERT INTO household_profiles VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name,icon=excluded.icon,revision=excluded.revision',(uid,name,icon,revision))
            db.execute('INSERT INTO person_colors VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET color=excluded.color',(uid,color))
            db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)',(uid,))
        return 'Person settings saved. Refresh chore lists to see the changes.'

    class People(HouseholdAdmin):
        def __init__(self,owner,guild=None,page=0,query=''):
            super().__init__(owner);self.guild=guild;query=str(query).strip()[:100]
            known=household_people(owner,guild)
            known=sorted([uid for uid in known if not query or query.casefold() in person(uid,guild).casefold() or query in uid],key=lambda uid:(person(uid,guild).casefold(),int(uid)))
            size=page_size(owner);page=min(max(int(page),0),max((len(known)-1)//size,0))
            self.recovery_context={'screen':'people','page':page,'query':query}
            self.rebuild=lambda:People(owner,guild,page,query)
            self.name_ids=known[page*size:(page+1)*size]
            self.embed=discord.Embed(title='People',description='Choose a person to manage their name, color, icon, regular home/away schedule, date exceptions, or calendar. Add anyone through the Discord account picker.',color=0x6B9B77)
            for index,uid in enumerate(self.name_ids):
                self.embed.add_field(name=clean(person(uid,guild),100),value=f'Discord ID {uid} · '+ui.attendance.describe(uid),inline=False)
                self.button('Open '+clean(person(uid,guild),45)+' · '+uid,lambda i,uid=uid:present(i,PersonProfile(owner,uid,i.guild,page,query)),row=index//5)
            picker=discord.ui.UserSelect(placeholder='Find or add a Discord account',row=2)
            async def choose(i):
                if not await self.interaction_check(i):return
                member=picker.values[0]
                if member.bot or getattr(getattr(member,'guild',None),'id',None)!=i.guild_id:
                    return await i.response.send_message('Choose a person in this household server.',ephemeral=True)
                await present(i,PersonProfile(owner,str(member.id),i.guild,page,query))
            picker.callback=choose;self.add_item(picker)
            self.button('Search people',lambda i:i.response.send_modal(PeopleSearch(self)),row=3)
            self.button('Previous',lambda i:present(i,People(owner,i.guild,page-1,query)),row=3,disabled=page==0)
            self.button('Next',lambda i:present(i,People(owner,i.guild,page+1,query)),row=3,disabled=(page+1)*size>=len(known))
            self.embed.set_footer(text=f'Page {page+1} · {len(known)} people')
            self.nav(lambda:adapt(ui.HouseholdSetup(owner),owner))

    class PeopleSearch(discord.ui.Modal):
        def __init__(self,source):
            super().__init__(title='Find a person');self.source=source
            self.term=discord.ui.TextInput(label='Name or Discord account ID',required=False,max_length=100,default=source.recovery_context['query']);self.add_item(self.term)
        async def on_submit(self,i):
            if not await self.source.interaction_check(i):return
            await present(i,People(self.source.owner,i.guild,query=self.term.value))

    class ProfileModal(discord.ui.Modal):
        def __init__(self,source):
            super().__init__(title='Person name and icon');self.source=source
            profile=source.expected[0]
            self.name=discord.ui.TextInput(label='Display name (blank uses Discord name)',required=False,max_length=60,default=profile[0] if profile else '')
            self.icon=discord.ui.TextInput(label='Icon or emoji (optional)',required=False,max_length=16,default=profile[1] if profile else '')
            self.add_item(self.name);self.add_item(self.icon)
        async def on_submit(self,i):
            source=self.source
            if not await source.interaction_check(i):return
            async with lock:notice=save_profile(source.uid,self.name.value,self.icon.value,source.color,source.expected)
            await present(i,PersonProfile(source.owner,source.uid,i.guild,source.page,source.query),notice)

    class PersonProfile(HouseholdAdmin):
        def __init__(self,owner,uid,guild=None,page=0,query=''):
            super().__init__(owner);uid=str(uid);self.uid=uid;self.page=page;self.query=query
            self.expected=profile_snapshot(uid);self.color=color_key(uid,guild)
            self.recovery_context={'screen':'person_profile','uid':uid,'page':page,'query':query}
            self.rebuild=lambda:PersonProfile(owner,uid,guild,page,query)
            self.name_ids=[uid]
            self.embed=discord.Embed(title='Person settings',description=clean(person(uid,guild),150)+f'\nDiscord account ID: {uid}',color=0x6B9B77)
            self.embed.add_field(name='Regular schedule',value=ui.attendance.describe(uid),inline=False)
            self.button('Name and icon',lambda i:i.response.send_modal(ProfileModal(self)),row=0)
            picker=discord.ui.Select(placeholder='Color or marker',row=1,options=[discord.SelectOption(label=label,value=key,emoji=emoji or None,default=key==self.color) for key,(emoji,label) in COLORS.items()])
            async def choose_color(i):
                if not await self.interaction_check(i):return
                profile=self.expected[0]
                async with lock:notice=save_profile(uid,profile[0] if profile else '',profile[1] if profile else '',picker.values[0],self.expected)
                await present(i,PersonProfile(owner,uid,i.guild,page,query),notice)
            picker.callback=choose_color;self.add_item(picker)
            self.button('Regular schedule',lambda i:present(i,UsualSchedule(owner,[uid],i.guild)),row=2)
            self.button('Trips and date exceptions',lambda i:present(i,Trips(owner,i.guild,[uid])),row=2)
            self.button('Calendar',lambda i:present(i,Chores(owner,i.guild,mode='date',who=uid)),row=2)
            self.nav(lambda:People(owner,guild,page,query))

    def household_color_snapshot():
        return (db.execute('SELECT role,user_id FROM household_identities ORDER BY role').fetchall(),
                db.execute('SELECT user_id,color FROM person_colors ORDER BY user_id').fetchall())

    class HouseholdColors(View):
        def __init__(self,owner,guild=None,identities=None,colors=None,expected=None):
            super().__init__(owner)
            self.guild=guild
            self.identities=dict(db.execute('SELECT role,user_id FROM household_identities')) if identities is None else dict(identities)
            self.colors=dict(colors or {'kas':'keep','zel':'keep'})
            self.expected=household_color_snapshot() if expected is None else expected
            self.recovery_context={'screen':'household_colors'}
            self.embed=discord.Embed(title='Household colors',description='Choose Kas and Zel by their Discord accounts. Keep current color preserves a saved choice; otherwise Kas starts pink and Zel orange. Save colors once when ready.',color=0x6B9B77)
            for index,(role,label) in enumerate((('kas','Kas'),('zel','Zel'))):
                uid=self.identities.get(role)
                self.embed.add_field(name=label,value=(clean(person(uid,guild),100)+f' · ID {uid}') if uid else 'Choose the Discord account below.',inline=False)
                picker=discord.ui.UserSelect(placeholder=label+' — Discord account',row=index)
                if uid:picker.default_values=[discord.SelectDefaultValue(id=int(uid),type=discord.SelectDefaultValueType.user)]
                async def choose(i,role=role,picker=picker):
                    if not await self.interaction_check(i):return
                    member=picker.values[0]
                    if member.bot or getattr(getattr(member,'guild',None),'id',None)!=i.guild_id:
                        return await i.response.send_message('Choose a person in this household server.',ephemeral=True)
                    identities=dict(self.identities);identities[role]=str(member.id)
                    await present(i,HouseholdColors(owner,i.guild,identities,self.colors,self.expected))
                picker.callback=choose;self.add_item(picker)
                color=discord.ui.Select(placeholder=label+' — color',row=index+2,options=[discord.SelectOption(label='Keep current color / use default',value='keep',default=self.colors.get(role)=='keep')]+[discord.SelectOption(label=name,value=key,emoji=emoji or None,default=self.colors.get(role)==key) for key,(emoji,name) in COLORS.items()])
                async def choose_color(i,role=role,picker=color):
                    if not await self.interaction_check(i):return
                    value=picker.values[0]
                    if value!='keep' and value not in COLORS:return await i.response.send_message('Choose a listed color.',ephemeral=True)
                    colors=dict(self.colors);colors[role]=value
                    await present(i,HouseholdColors(owner,i.guild,self.identities,colors,self.expected))
                color.callback=choose_color;self.add_item(color)
            self.button('Save colors',self.save,row=4,primary=True)
            self.nav(lambda:adapt(ui.HouseholdSetup(owner),owner))

        async def interaction_check(self,i):
            if not await super().interaction_check(i):return False
            if not getattr(getattr(i.user,'guild_permissions',None),'manage_guild',False):
                await i.response.send_message('Household colors are managed by a server administrator.',ephemeral=True)
                return False
            return True

        async def save(self,i):
            if not await self.interaction_check(i):return
            ids=[self.identities.get(role) for role in ('kas','zel')]
            if any(not uid or not str(uid).isdecimal() for uid in ids) or ids[0]==ids[1]:
                return await i.response.send_message('Choose two different Discord accounts for Kas and Zel.',ephemeral=True)
            for uid in ids:
                member=i.guild.get_member(int(uid))
                if member is None and hasattr(i.guild,'fetch_member'):
                    try:member=await i.guild.fetch_member(int(uid))
                    except discord.HTTPException:member=None
                if member is None or getattr(member,'bot',True) or getattr(getattr(member,'guild',None),'id',None)!=i.guild_id:
                    return await i.response.send_message('Choose current household members before saving colors.',ephemeral=True)
            async with lock:
                if household_color_snapshot()!=self.expected:
                    return await present(i,HouseholdColors(self.owner,i.guild),'Household accounts or colors changed. Review the current settings.')
                if any(self.colors.get(role)!='keep' and self.colors.get(role) not in COLORS for role in ('kas','zel')):
                    return await i.response.send_message('Choose a listed color.',ephemeral=True)
                with db:
                    db.execute('DELETE FROM household_identities')
                    for role,uid,default in zip(('kas','zel'),ids,('pink','orange')):
                        db.execute('INSERT INTO household_identities VALUES(?,?)',(role,uid))
                        value=self.colors.get(role,'keep')
                        if value=='keep':db.execute('INSERT OR IGNORE INTO person_colors VALUES(?,?)',(uid,default))
                        else:db.execute('INSERT OR REPLACE INTO person_colors VALUES(?,?)',(uid,value))
            await present(i,HouseholdColors(self.owner,i.guild),'Household colors saved. Refresh chore lists to see them.')

    class PersonColor(View):
        def __init__(self,owner,guild=None,back=None):
            super().__init__(owner)
            back=back or (lambda:PersonalSettings(owner,guild))
            self.recovery_context={'screen':'person_color','parent':recovery.bookmark(back())}
            current=color_key(owner,guild)
            self.embed=discord.Embed(title='Your name marker',description='Choose a color dot or symbol beside your name. Changes save immediately; names stay visible.',color=0x6B9B77)
            picker=discord.ui.Select(placeholder='Choose your name marker',options=[discord.SelectOption(label=label,value=key,emoji=emoji or None,default=key==current) for key,(emoji,label) in COLORS.items()])
            async def save(i):
                if not await self.interaction_check(i):return
                value=picker.values[0] if picker.values else None
                if value not in COLORS:return await i.response.send_message('Choose one of the listed colors.',ephemeral=True)
                async with lock:
                    with db:db.execute('INSERT OR REPLACE INTO person_colors(user_id,color) VALUES(?,?)',(str(owner),value))
                await present(i,PersonColor(owner,i.guild,back),'Your color is saved. Everyone will see it when they refresh.')
            picker.callback=save;self.add_item(picker);self.nav(back)

    class PersonalSettings(View):
        def __init__(self,owner,guild=None,back=None):
            super().__init__(owner)
            back=back or (lambda:Dashboard(owner,guild))
            self.recovery_context={'screen':'personal_settings','parent':recovery.bookmark(back())}
            expected=ui.planning.settings(owner)
            trade=db.execute('SELECT trade_dm FROM notification_preferences WHERE user_id=?',(str(owner),)).fetchone()
            trade_on=bool(trade and trade[0])
            self.embed=discord.Embed(title='Settings',description='Changes save immediately.\nReminder times: '+', '.join(json.loads(expected[1]))+' Eastern.',color=0x6B9B77)
            async def refresh(i,notice=None):
                if notice and notice.startswith('Chore reminders '):notice='Reminder settings saved.'
                await present(i,PersonalSettings(owner,i.guild,back),notice)
            color=discord.ui.Select(placeholder='Name marker',row=0,options=[discord.SelectOption(label='Marker · '+label,value=key,emoji=emoji or None,default=key==color_key(owner,guild)) for key,(emoji,label) in COLORS.items()])
            async def save_color(i):
                if not await self.interaction_check(i):return
                value=color.values[0] if color.values else None
                if value not in COLORS:return await i.response.send_message('Choose a listed color.',ephemeral=True)
                async with lock:
                    with db:db.execute('INSERT OR REPLACE INTO person_colors VALUES(?,?)',(str(owner),value))
                await refresh(i,'Name marker saved.')
            color.callback=save_color;self.add_item(color)
            size=discord.ui.Select(placeholder='Chores per page',row=1,options=[discord.SelectOption(label=f'List length · {n} chores',value=str(n),default=n==sheet_size(owner)) for n in range(1,11)])
            async def save_size(i):
                if not await self.interaction_check(i):return
                try:value=int(size.values[0])
                except (ValueError,IndexError):value=0
                if not 1<=value<=10:return await i.response.send_message('Choose 1–10 chores.',ephemeral=True)
                async with lock:
                    with db:db.execute('INSERT OR REPLACE INTO workspace_preferences VALUES(?,?)',(str(owner),value))
                await refresh(i,'List length saved.')
            size.callback=save_size;self.add_item(size)
            async def reminders(i):
                if not await self.interaction_check(i):return
                async with lock:notice=ui.planning.save_reminders(owner,not expected[0],','.join(json.loads(expected[1])),expected)
                await refresh(i,notice)
            async def times(i):
                if not await self.interaction_check(i):return
                modal=ui.planning.ReminderTimes(owner)
                async def submit(event):
                    if not await self.interaction_check(event):return
                    async with lock:notice=ui.planning.save_reminders(owner,modal.expected[0],modal.times.value,modal.expected)
                    await refresh(event,notice)
                modal.on_submit=submit
                await i.response.send_modal(modal)
            async def toggle_trade(i):
                if not await self.interaction_check(i):return
                async with lock:
                    current=db.execute('SELECT trade_dm FROM notification_preferences WHERE user_id=?',(str(owner),)).fetchone()
                    if bool(current and current[0])!=trade_on:notice='Trade alerts changed. Review the current setting.'
                    else:
                        with db:db.execute('INSERT OR REPLACE INTO notification_preferences VALUES(?,?)',(str(owner),int(not trade_on)))
                        notice='Trade alerts '+('off.' if trade_on else 'on · private DMs for new trade proposals.')
                await refresh(i,notice)
            self.button('Chore reminders: '+('On' if expected[0] else 'Off'),reminders,row=2)
            self.button('Change times',times,row=2)
            self.button('Trade alerts: '+('On' if trade_on else 'Off'),toggle_trade,row=3)
            self.nav(back)

    class ChoresSearch(discord.ui.Modal):
        def __init__(self,source):
            super().__init__(title='Find a chore')
            self.source=source
            self.term=discord.ui.TextInput(label='Name, instructions, or room',required=False,default=source.state['query'],max_length=100)
            self.add_item(self.term)
        async def on_submit(self,i):
            if not await self.source.interaction_check(i):return
            await present(i,Chores(self.source.owner,i.guild,**dict(self.source.state,query=self.term.value,page=0)))

    class Chores(View):
        def __init__(self,owner,guild=None,mode='today',day=None,who='mine',query='',page=0):
            super().__init__(owner)
            ns['reset_due_quests']()
            day=datetime.fromisoformat(day).date() if isinstance(day,str) else day or timing.now().date()
            mode=mode if mode in ('today','date','week','all') else 'today'
            self.guild=guild
            self.state=dict(mode=mode,day=day.isoformat(),who=str(who),query=str(query).strip()[:100],page=max(0,int(page)))
            self.recovery_context=dict(screen='chores',**self.state)
            self.embed=discord.Embed(title='Chores',description='Choose a chore to read its instructions.',color=0x6B9B77)
            self.entries=[]
            if mode=='all':
                self.entries=[(None,chore(qid),ownership(qid)[0]) for qid, in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(qid)]
            else:
                start=day-timedelta(days=day.weekday()) if mode=='week' else day
                for n in range(7 if mode=='week' else 1):
                    date=start+timedelta(days=n)
                    self.entries.extend((date,chore(q[0]),uid) for q,uid in ui.planning.project(date))
                if mode=='week':
                    self.entries.extend((None,chore(q[0]),uid) for q,uid in ui.planning.project(start,flexible=True))
                # Flexible and overdue work remains findable on Today.
                if mode in ('today','date') and day==timing.now().date():
                    seen={q[0] for _,q,_ in self.entries}
                    for qid, in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id'):
                        q=chore(qid)
                        if qid not in seen and not ui.is_archived(qid) and not q[5] and ready(qid):self.entries.append((day,q,ownership(qid)[0]))
            self.attention={r[0][0]:r for r in attention_rows()} if who=='attention' and day==timing.now().date() else {}
            if who=='attention' and day==timing.now().date():
                self.entries=[(day,r[0],ownership(r[0][0])[0]) for r in self.attention.values()]
            def matches(entry):
                _,q,uid=entry
                if mode in ('today','date') and day==timing.now().date() and (q[5] or (uid and not ready(q[0]))):return False
                person_id=str(owner) if who=='mine' else str(who)
                return (who=='everyone' or (who=='attention' and (q[0] in self.attention or (day!=timing.now().date() and not uid))) or (who=='unclaimed' and not uid) or str(uid)==person_id) and (not query or query.casefold() in ' '.join(str(q[n] or '') for n in (1,8,9)).casefold())
            self.entries=[entry for entry in self.entries if matches(entry)]
            self.size=min(sheet_size(owner),4) if who=='attention' else sheet_size(owner)
            self.page=min(self.state['page'],max((len(self.entries)-1)//self.size,0))
            self.state['page']=self.page;self.recovery_context['page']=self.page
            self.name_ids=[uid for _,_,uid in self.entries[self.page*self.size:(self.page+1)*self.size] if uid]
            self.rebuild=lambda:Chores(owner,guild,**self.state)

        def build(self,frame,notice=None):
            owner=self.owner;state=self.state;day=datetime.fromisoformat(state['day']).date()
            def target(i,**changes):return Chores(owner,i.guild,**dict(state,**changes))
            def button(label,callback,disabled=False):
                item=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary,disabled=disabled);item.callback=callback;return item
            catalog=state['mode']=='all'
            personal=state['who'] not in ('mine','unclaimed','everyone','attention')
            title='Manage chores' if catalog else clean(person(state['who'],self.guild),80)+' · Calendar' if personal else 'Chores'
            frame.heading(discord.ui.TextDisplay('# '+title),page_help_button(self))
            if not catalog:
                tabs=[]
                for label,who in [('Mine','mine'),('Available','unclaimed'),('Everyone','everyone'),('Needs attention','attention')]:
                    tab=button(label,lambda i,who=who:present(i,target(i,who=who,page=0)))
                    tab.style=discord.ButtonStyle.primary if state['who']==who else discord.ButtonStyle.secondary
                    tabs.append(tab)
                frame.rows(tabs)
            if not catalog:
                frame.add_item(discord.ui.TextDisplay('-# '+('Today · ' if state['mode']=='today' else '')+day.strftime('%A, %B %d')))
                if state['mode']=='date':
                    frame.rows([button('<< Prev day',lambda i:present(i,target(i,day=(day-timedelta(days=1)).isoformat(),page=0))),button('Today',lambda i:present(i,target(i,day=timing.now().date().isoformat(),page=0))),button('Next day >>',lambda i:present(i,target(i,day=(day+timedelta(days=1)).isoformat(),page=0)))])
            chunk=self.entries[self.page*self.size:(self.page+1)*self.size]
            lines=[]
            for index,(date,q,uid) in enumerate(chunk,self.page*self.size+1):
                suffix=''
                if state['who']=='everyone' and not catalog:
                    name=person(uid,self.guild) if uid else 'Unclaimed'
                    if uid and '<@' in name:name=name[:name.index('<@')]+'Assigned'
                    suffix=' · '+clean(name,60)
                # A middle dot avoids Discord treating numbered rows as Markdown lists.
                lines.append(f'{index} · {clean(q[1],100)}'+suffix)
                if state['who']=='attention':
                    row=self.attention.get(q[0])
                    labels=(['Overdue'] if row and row[1] else [])+(['Needs someone'] if not uid else [])+(['Blocked · '+row[3][4]] if row and row[3] else [])
                    lines.append('-# '+' · '.join(labels+([clean(person(uid,self.guild),60)] if uid else [])))
            heading='CHORE CATALOG' if catalog else {'mine':'YOUR CHORES','unclaimed':'AVAILABLE TO CLAIM','attention':'NEEDS ATTENTION'}.get(state['who'],'EVERYONE’S CHORES')
            if personal and not catalog:heading=clean(person(state['who'],self.guild),80)+' — CHORES'
            listing=discord.ui.Container(accent_colour=0x6B9B77)
            empty='You’re caught up ✅' if state['who']=='mine' and not catalog and not state['query'] else 'All clear. No chores match this view. Try Everyone or another date.'
            listing.add_item(discord.ui.TextDisplay('**'+heading+'**\n\n'+('\n'.join(lines) if lines else empty)))
            if state['who']=='attention' and not catalog and day==timing.now().date():
                listing.clear_items()
                listing.add_item(discord.ui.TextDisplay('**'+heading+'**'+('\n'+empty if not chunk else '')))
                for index,(date,q,uid) in enumerate(chunk):
                    expected=ui.snapshot(q[0])
                    async def quick_claim(i,qid=q[0],expected=expected):
                        await claim_now(i,self,qid,expected,lambda:self.rebuild(),stay_on_list=True)
                    row=frame.detail_row('**'+clean(q[1],100)+'**\n'+lines[index*2+1].removeprefix('-# '),label='Claim',callback=quick_claim)
                    row.accessory.disabled=bool(uid) or q[5] or not ready(q[0]) or not ui.available(owner)
                    listing.add_item(row)
            frame.add_item(listing)
            parent=lambda:self.rebuild()
            if chunk:
                picker=discord.ui.Select(placeholder='Choose a chore to edit…' if catalog else 'Choose a chore…',options=[discord.SelectOption(label=clean(q[1],100),value=str(n)) for n,(_,q,_) in enumerate(chunk)])
                async def choose(i):
                    if not await self.interaction_check(i):return
                    try:
                        index=int(picker.values[0])
                        if not 0<=index<len(chunk):raise ValueError('Invalid choice')
                        date,q,_=chunk[index]
                    except (ValueError,IndexError):return await i.response.send_message('Choose a chore from this sheet.',ephemeral=True)
                    if catalog:
                        modal=ui.EditChoreModal(owner,q[0],q[2],ui.snapshot(q[0]))
                        async def save(event):
                            if not await self.interaction_check(event):return
                            async with lock:
                                result=ui.update_chore(q[0],modal.name.value,modal.repeat_frequency(),modal.points.value,modal.notes.value,modal.expected,modal.room.value)
                            await present(event,self.rebuild(),result)
                        modal.on_submit=save
                        return await i.response.send_modal(modal)
                    if date is not None and date!=timing.now().date():
                        offered=ui.dated.slots(q[0])
                        if len(offered)>1:return await present(i,FutureSlots(owner,q[0],date,i.guild,parent))
                        if offered and date>=timing.now().date():return await present(i,FutureOccurrence(owner,q[0],date,offered[0],i.guild,parent))
                        return await present(i,ui.planning.Day(owner,date,mine=state['who']=='mine',guild=i.guild))
                    await present(i,Card(owner,q[0],parent,i.guild))
                picker.callback=choose;frame.add_item(discord.ui.ActionRow(picker))
            count=max((len(self.entries)-1)//self.size+1,1)
            frame.add_item(discord.ui.TextDisplay(f'-# {self.page*self.size+1 if chunk else 0}–{self.page*self.size+len(chunk)} of {len(self.entries)} · Page {self.page+1} of {count}'))
            frame.rows([button('< Prev',lambda i:present(i,target(i,page=self.page-1)),self.page==0),button('Next >',lambda i:present(i,target(i,page=self.page+1)),self.page+1>=count)])
            if notice:frame.add_item(discord.ui.TextDisplay('-# '+str(notice)))
            if catalog:
                frame.rows([button('Add chore',lambda i:present(i,adapt(ui.AddChoreMenu(owner),owner,parent))),button('Archive chore',lambda i:present(i,adapt(ui.RemoveChoreView(owner),owner,parent))),button('Archived chores',lambda i:present(i,adapt(ui.RemoveChoreView(owner,removed=True),owner,parent))),button('Search',lambda i:i.response.send_modal(ChoresSearch(self)))])
                frame.rows([button('Back to chores',lambda i:present(i,target(i,mode='today',day=timing.now().date().isoformat(),who='mine',query='',page=0))),button('Household tools',lambda i:present(i,Dashboard(owner,i.guild,i.user)))])
            else:
                navigation=[button('Back to today',lambda i:present(i,target(i,mode='today',day=timing.now().date().isoformat(),page=0))),button('Week calendar',lambda i:present(i,ui.planning.Calendar(owner,i.guild,day=day,mine=state['who']=='mine')))] if state['mode']=='date' else [button('Other dates',lambda i:present(i,target(i,mode='date',page=0)))]
                if personal:
                    navigation=[button('Day view',lambda i:present(i,target(i,mode='date',page=0))),button('Week view',lambda i:present(i,target(i,mode='week',page=0))),button('Person settings',lambda i:present(i,PersonProfile(owner,state['who'],i.guild)))]
                if state['who']=='mine':navigation.append(button('Quick Done',lambda i:present(i,Browse(owner,area='mine',tab='due',guild=i.guild))))
                navigation.append(button('Manage chores',lambda i:present(i,target(i,mode='all',who='everyone',query='',page=0))))
                frame.rows(navigation)
            refresh=button('Refresh',lambda i:present(i,target(i)))
            # A refresh action lives with contextual help instead of a permanent toolbar.
            return refresh

    class Dashboard(View):
        def __init__(self, owner, guild=None, member=None):
            super().__init__(owner)
            incoming = db.execute("SELECT COUNT(*) FROM chore_trades WHERE recipient=? AND status='pending'", (str(owner),)).fetchone()[0]
            self.embed = discord.Embed(title='🌱 Dashboard', description='Your controls are private. Chore changes are shared with the household.', color=0x9B59B6)
            self.recovery_context = {'screen':'dashboard'}
            if recovery.latest(owner):
                self.button('Continue where I left off', recovery.resume_latest, row=3)
            def browse(area):
                saved = memory.get((owner, area), {})
                return Browse(owner, **dict(saved, area=area), guild=guild)
            self.button('Household chores', lambda i: present(i, browse('household')), row=0)
            self.button('Who’s home?', lambda i: present(i, Trips(owner, i.guild)), row=1)
            self.button('Manage chores', lambda i: present(i, Chores(owner,i.guild,mode='all',who='everyone')), row=1)
            self.button('Help', lambda i: present(i, Guide(owner)), row=1)
            self.button(f'Trades ({incoming} incoming)', lambda i: present(i, adapt(ui.TradeInboxView(owner), owner)), row=2)
            self.button('Chores',lambda i:present(i,Chores(owner,i.guild)),row=3)
            self.button('Calendar',lambda i:present(i,Chores(owner,i.guild,mode='date',who='everyone')),row=3)
            self.button('Needs attention',lambda i:present(i,Chores(owner,i.guild,who='attention')),row=0)
            self.button('Quick Done',lambda i:present(i,Browse(owner,area='mine',tab='due',guild=i.guild)),row=0)
            self.button('Chore reminders',lambda i:present(i,ui.planning.Reminders(owner)),row=3)
            self.button('Trade alerts', lambda i: present(i, Notifications(owner)), row=2)
            self.button('List length',lambda i:present(i,ListLength(owner)),row=1)
            self.button('Workload & pace',lambda i:ui.insights.show(i,owner),row=1)
            self.button('Points & standings',lambda i:present(i,Points(owner,i.guild)),row=2)
            if incoming: self.embed.add_field(name='Waiting for you', value=f'{incoming} incoming trade request(s).', inline=False)
            if owner == OWNER:
                count = db.execute('SELECT COUNT(*) FROM chore_feedback WHERE reviewed=0').fetchone()[0]
                self.button(f'Review inbox ({count})', lambda i: present(i, Inbox(owner, i.guild)), row=2)
                self.button('Update announcements',lambda i:present(i,Announcements(owner,i.guild)),row=2)
            if guild:
                member = member or getattr(guild, 'get_member', lambda uid: None)(owner)
                if member and getattr(getattr(member, 'guild_permissions', None), 'manage_guild', False):
                    self.button('Household setup', lambda i: present(i, adapt(ui.HouseholdSetup(owner), owner)), row=3)
            total = db.execute('SELECT points,streak FROM users WHERE id=?', (str(owner),)).fetchone()
            self.embed.set_footer(text=f'{total[0]} points · {total[1]} day streak' if total else '0 points · 0 day streak')

    def attention_deadline(q):
        """Use explicit dates first; persist the first known flexible period end."""
        move=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(q[0],)).fetchone()
        if move:
            return datetime.fromisoformat(move[0]).replace(tzinfo=ns['QUEST_TIMEZONE'])+timedelta(days=1)
        if q[2] in SCHEDULED | DAILY_SHIFTS:
            state=timing.state(q[0])
            if state:
                start=datetime.fromisoformat(state[0])
                return start+timedelta(hours=12) if q[2] in DAILY_SHIFTS else start+timedelta(days=1)
        if q[2]=='one-time':return None
        cycle=repr((q[2],q[6],q[7],timing.state(q[0]),timing.policy_state(q[0]) if timing.policy(q[0])=='skip' else None))
        saved=db.execute('SELECT cycle,deadline FROM attention_windows WHERE quest_id=?',(q[0],)).fetchone()
        if saved and saved[0]==cycle:return datetime.fromisoformat(saved[1])
        deadline=timing.calculate_reset(timing.now(),q[2])
        if deadline:
            with db:db.execute('INSERT OR REPLACE INTO attention_windows VALUES(?,?,?)',(q[0],cycle,deadline))
            return datetime.fromisoformat(deadline)
        return None

    def attention_rows():
        ns['reset_due_quests']()
        rows=[]
        for qid, in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id').fetchall():
            q=chore(qid)
            if q[5] or ui.is_archived(qid):continue
            due=ready(qid)
            if ownership(qid)[0] and not ui.attendance.at(ownership(qid)[0],timing.now()):continue
            deadline=attention_deadline(q)
            overdue=due and deadline is not None and timing.now()>=deadline
            unclaimed=due and not ownership(qid)[0]
            issue=ui.planning.help_record(qid)
            blocked=bool(issue)
            if overdue or unclaimed or blocked:
                rows.append((q,overdue,unclaimed,issue,deadline))
        rows.sort(key=lambda r:(not r[1],not bool(r[3]),r[0][1].casefold(),r[0][0]))
        return rows

    class Attention(View):
        def __init__(self,owner,guild=None,page=0):
            super().__init__(owner)
            size=page_size(owner)
            self.list_page_size=size
            rows=attention_rows()
            page=min(max(page,0),max((len(rows)-1)//size,0))
            self.page,self.entries=page,rows
            self.recovery_context={'screen':'attention','page':page}
            self.name_ids=[ownership(r[0][0])[0] for r in rows[page*size:(page+1)*size]]
            self.rebuild=lambda:Attention(owner,guild,page)
            back=lambda:Attention(owner,guild,page)
            self.embed=discord.Embed(title='Needs attention',description=f'{len(rows)} chore(s) · Overdue: {sum(r[1] for r in rows)} · Needs someone: {sum(r[2] for r in rows)} · Blocked: {sum(bool(r[3]) for r in rows)}\nChores appear once; labels can overlap. Due today does not mean overdue.',color=0x6B9B77)
            chunk=rows[page*size:(page+1)*size]
            self.attention_details=[r[0][0] for r in chunk]
            for q,overdue,unclaimed,issue,deadline in chunk:
                labels=(['Overdue'] if overdue else [])+(['Needs someone'] if unclaimed else [])+(['Blocked · '+issue[4]] if issue else [])
                details=' · '.join(labels)+'\n'+timing.compact_label(q[2])+f' · {q[3]} points\n'+clean(person(ownership(q[0])[0],guild),100)
                if overdue:details+='\nPeriod ended '+deadline.strftime('%a %b %d, %I:%M %p Eastern')
                if issue:details+='\n'+clean(issue[5],500)
                self.embed.add_field(name=clean(q[1],200),value=details,inline=False)
            if chunk:
                picker=discord.ui.Select(placeholder='Open a chore card…',row=0,options=[ui.chore_option(r[0][0],r[0][1],'Review responsibility, help status, or completion') for r in chunk])
                async def choose(i):await present(i,Card(owner,int(picker.values[0]),back,i.guild))
                picker.callback=choose;self.add_item(picker)
            else:self.embed.add_field(name='Nothing needs attention',value='No overdue, due unclaimed, or actively blocked chores. Scheduled work remains in Household and Calendar.')
            self.embed.set_footer(text=f'Page {page+1} of {max(1,(len(rows)+size-1)//size)} · Eastern time')
            self.paging_labels=('Previous','Next')
            if page:self.button('Previous',lambda i:present(i,Attention(owner,i.guild,page-1)),row=1)
            if (page+1)*size<len(rows):self.button('Next',lambda i:present(i,Attention(owner,i.guild,page+1)),row=1)
            self.button('Refresh',lambda i:present(i,Attention(owner,i.guild,page)),row=2)
            self.nav()

    class Points(View):
        def __init__(self,owner,guild=None,page=0):
            super().__init__(owner)
            size=page_size(owner)
            self.list_page_size=size
            total=db.execute('SELECT points,streak FROM users WHERE id=?',(str(owner),)).fetchone() or (0,0)
            scores=dict(db.execute('SELECT id,points FROM users'))
            records=sorted(((uid,scores.get(uid) or 0) for uid in household_people(owner,guild,register=False)),key=lambda row:(-row[1],int(row[0])))
            page=min(max(page,0),max((len(records)-1)//size,0))
            chunk=records[page*size:(page+1)*size]
            self.name_ids=[r[0] for r in chunk]
            self.rebuild=lambda:Points(owner,guild,page)
            self.recovery_context={'screen':'points','page':page}
            self.embed=discord.Embed(title='Points & standings',description=f'⭐ **{total[0]} points** · 🔥 **{total[1]} day streak**\nEarn points by completing chores.',color=0x6B9B77)
            rank=0;previous=None
            for index,(uid,points) in enumerate(records):
                if points!=previous:rank=index+1
                previous=points
                if page*size<=index<(page+1)*size:
                    self.embed.add_field(name=f'{rank}. '+clean(person(uid,guild),100),value=f'{points} points',inline=False)
            if not records:self.embed.add_field(name='No scores yet',value='Finish a chore to start earning points.')
            self.embed.set_footer(text=f'Page {page+1} of {max((len(records)-1)//size+1,1)} · {len(records)} household member(s)')
            if owner==OWNER:self.button('Reset points',lambda i:present(i,ResetPoints(owner,i.guild)),row=2)
            if owner==OWNER:self.button('Reset history / Undo',lambda i:present(i,ResetHistory(owner,i.guild)),row=2)
            if page:self.button('Previous',lambda i:present(i,Points(owner,i.guild,page-1)),row=3)
            if (page+1)*size<len(records):self.button('Next',lambda i:present(i,Points(owner,i.guild,page+1)),row=3)
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
            self.recovery_context={'screen':'points'}
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

    def browse_page_size(owner,area='mine'):
        # Undo controls stay visible without overflowing Discord's 40-component cap.
        return list_capacity(page_size(owner),undo_count=bool(undoable_skip(owner))+bool(ui.dated.latest_undo(owner))+bool(ui.undoable_completion(owner)),grouped=area=='household',tab_count=5 if area=='mine' else 4)

    def browse_return(source,guild):
        state=dict(source.state)
        state['page']=state['page']*source.list_page_size//browse_page_size(source.owner,source.state['area'])
        return Browse(source.owner,**state,guild=guild)

    class Browse(View):
        def __init__(self, owner, area='mine', tab=None, page=0, query='', person_id=None, room='', unclaimed=False, group='day', date_filter='', guild=None):
            super().__init__(owner)
            size=browse_page_size(owner,area)
            self.list_page_size=size
            self.guild=guild
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
                    future_own = ownership(q[0], 1)[0] == str(owner) or ui.repeating.in_week(owner,q[0],1) or ui.repeating.in_week(owner,q[0],0) or ui.dated.in_week(owner,q[0],offset) or ui.dated.in_week(owner,q[0],1)
                    if tab == 'done':
                        if not db.execute('SELECT 1 FROM completion_log WHERE quest_id=? AND user_id=? AND undone_at IS NULL', (q[0], str(owner))).fetchone(): continue
                    elif tab == 'upcoming':
                        if q[5] and not q[7]: continue
                        if not (own or future_own) or (due and own and not future_own): continue
                    elif not (own or (tab in ('week','next') and (ui.repeating.in_week(owner,q[0],offset) or ui.dated.in_week(owner,q[0],offset)))) or (tab == 'due' and not due) or (tab == 'week' and not inweek): continue
                elif area == 'pickup':
                    future_open=bool(uid or q[4]) and tab in ('week','next','upcoming') and any(not ui.dated.skipped(q[0],ui.dated.when(day,slot)) and not (ui.dated.owner(q[0],ui.dated.when(day,slot)) or ui.dated.base_owner(q[0],ui.dated.when(day,slot))) for day,slot in ui.dated.upcoming(q[0],ui.week_start(offset).date(),ui.week_start(offset+1).date()+timedelta(days=1)))
                    if (uid or q[4]) and not future_open: continue
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
            page = min(max(page, 0), max((len(rendered)-1)//size, 0))
            self.state['page'] = page
            memory[(owner, area)] = dict(self.state)
            self.name_ids=[ownership(q[0],offset)[0] for q in selected]
            self.rebuild=lambda:Browse(owner,**self.state,guild=guild)
            self.recovery_context={'screen':'browse','state':dict(self.state),'list_size':size}
            back = lambda: Browse(owner, **self.state, guild=guild)
            chunk = rendered[page*size:(page+1)*size]
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
                elif area=='pickup' and not uid:
                    if tab!='due':details+='\n'+status
                    elif q[2] in ('twice-daily','daily-am','daily-pm'):details+=' · '+status.removeprefix('Due now · ')
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
            if (page+1)*size < len(rendered): self.button('Next', lambda i: present(i, Browse(owner, **dict(self.state, page=page+1), guild=i.guild)), row=3)
            self.button('Refresh', lambda i: present(i, Browse(owner, **self.state, guild=i.guild)), row=3)
            self.nav()
            self.embed.set_footer(text=f'Page {page+1} of {max((len(rendered)-1)//size+1,1)} · Eastern time · Weeks change Sunday 6 p.m.')

    class ButtonChoices(View):
        """Button counterpart of an existing selector; keep its validated callback."""
        def __init__(self,source,picker,guild=None,page=0,selected=None,members=(),inline=False):
            super().__init__(source.owner)
            self.recovery_context=getattr(source,'recovery_context',{'screen':'dashboard'})
            self.inline=inline
            title=(picker.placeholder or 'Choose an option').rstrip('… .')
            self.embed=discord.Embed(title=title,description='Choose an option.' if picker.max_values==1 else 'Choose items, then Apply. Changes are not saved until Apply.',color=0x6B9B77)
            if isinstance(picker,discord.ui.UserSelect):
                people={str(getattr(member,'id','')):member for member in list(getattr(guild,'members',[]))+list(members) if not getattr(member,'bot',False)}
                ids={str(uid) for uid, in db.execute('SELECT id FROM users')}
                ids.update(str(uid) for uid, in db.execute('SELECT user_id FROM alternating_members'))
                ids.add(str(source.owner))
                for uid in ids:
                    member=guild.get_member(int(uid)) if guild else None
                    if member and not getattr(member,'bot',False):people.setdefault(uid,member if hasattr(member,'id') else SimpleNamespace(id=int(uid),display_name=member.display_name))
                values=[(uid,clean(getattr(member,'display_name',uid),80),member) for uid,member in people.items() if uid]
                if not values:self.embed.description='No household accounts are cached yet. Open /chores in the household server after members have used it.'
            else:
                values=[(str(option.value),option.label,option.value) for option in picker.options]
            self.choice_count=len(values)
            if inline:page=getattr(source,'_choice_pages',{}).get(picker.placeholder,page)
            page=max(0,min(page,max((len(values)-1)//10,0)))
            selected=getattr(source,'_choice_drafts',{}).get(picker.placeholder,selected) if inline else selected
            selected=set(selected if selected is not None else [str(o.value) for o in getattr(picker,'options',[]) if o.default])
            async def apply(i,chosen):
                if not await source.interaction_check(i):return
                picker._values=[value for key,label,value in values if key in chosen]
                # Source callbacks continue to enforce ownership, stale state and permissions.
                await picker.callback(i)
            for index,(key,label,value) in enumerate(values[page*10:(page+1)*10]):
                async def choose(i,key=key):
                    if not await self.interaction_check(i):return
                    if picker.max_values==1:return await apply(i,{key})
                    changed=selected^{key}
                    if len(changed)>picker.max_values:return await i.response.send_message('Choose at most '+str(picker.max_values)+' items.',ephemeral=True)
                    if inline:
                        source._choice_drafts=dict(getattr(source,'_choice_drafts',{}),**{picker.placeholder:changed})
                        return await present(i,source)
                    await present(i,ButtonChoices(source,picker,i.guild,page,changed,members))
                option=self.button(('✓ ' if key in selected else '')+label,choose,row=index//3,primary=key in selected)
                option._sprig_choice_source=picker.custom_id
                option._sprig_choice_value=key
            if picker.max_values>1:
                self.button('Apply selection',lambda i:apply(i,selected),row=3,primary=True,disabled=not picker.min_values<=len(selected)<=picker.max_values)
            async def turn(i,offset):
                if not await self.interaction_check(i):return
                if inline:
                    source._choice_pages=dict(getattr(source,'_choice_pages',{}),**{picker.placeholder:page+offset})
                    return await present(i,source)
                await present(i,ButtonChoices(source,picker,i.guild,page+offset,selected,members))
            if inline or page:self.button('Previous',lambda i:turn(i,-1),row=4,disabled=page==0)
            if inline or (page+1)*10<len(values):self.button('Next',lambda i:turn(i,1),row=4,disabled=(page+1)*10>=len(values))
            if isinstance(picker,discord.ui.UserSelect):
                outer=self
                class FindPerson(discord.ui.Modal):
                    def __init__(self):
                        super().__init__(title='Find a household member')
                        self.name=discord.ui.TextInput(label='Beginning of Discord name or nickname',min_length=1,max_length=32)
                        self.add_item(self.name)
                    async def on_submit(self,i):
                        if not await source.interaction_check(i):return
                        await i.response.defer()
                        from discord.http import Route
                        try:
                            result=await asyncio.wait_for(bot.http.request(Route('GET','/guilds/{guild_id}/members/search',guild_id=i.guild_id),params={'query':self.name.value.strip(),'limit':25}),timeout=5)
                        except Exception:
                            return await present(i,outer,'Could not look up members. Nothing changed; try Find a person again.')
                        found=[SimpleNamespace(id=int(m['user']['id']),display_name=m.get('nick') or m['user'].get('global_name') or m['user']['username'],bot=False,guild=i.guild) for m in result if not m['user'].get('bot',False)]
                        await present(i,ButtonChoices(source,picker,i.guild,0,selected,tuple(members)+tuple(found)),'Choose a result below.' if found else 'No matching members. Try a different name.')
                self.button('Find a person',lambda i:i.response.send_modal(FindPerson()),row=4)
            self.button('Back',lambda i:present(i,source),row=4)

    async def claim_now(i,source,qid,expected,back=None,stay_on_list=False):
        if not await source.interaction_check(i):return
        async def change():
            async with lock:
                ns['reset_due_quests']()
                if ui.snapshot(qid)!=expected:return 'This occurrence changed. Review the current chore.'
                context=ui.Context(i);await bot.get_command('claim').callback(context,qid)
                return '\n'.join(context.messages)
        task=asyncio.create_task(change())
        finished,_=await asyncio.wait({task},timeout=1.0)
        if not finished:await i.response.defer()
        await present(i,back() if stay_on_list and back else Card(source.owner,qid,back,i.guild),await task)

    class ClaimChoices(View):
        def __init__(self,owner,qid,guild=None,back=None,include_once=True):
            super().__init__(owner)
            back=back or (lambda:Card(owner,qid,guild=guild))
            self.recovery_context={'screen':'card','qid':qid,'offset':0,'parent':recovery.bookmark(back())}
            q=chore(qid);expected=ui.snapshot(qid)
            self.embed=discord.Embed(title='Sign up · '+clean(q[1],100),description='Choose how long to take responsibility. Repeating days can be shared among people and pause when you are away.',color=0x6B9B77)
            async def once(i):
                if not await self.interaction_check(i):return
                async def change():
                    async with lock:
                        ns['reset_due_quests']()
                        if ui.snapshot(qid)!=expected:return 'This chore changed. Review it again.'
                        context=ui.Context(i);await bot.get_command('claim').callback(context,qid)
                        return '\n'.join(context.messages)
                task=asyncio.create_task(change())
                finished,_=await asyncio.wait({task},timeout=1.0)
                if not finished:await i.response.defer()
                await present(i,back(),await task)
            if include_once:self.button('Just this occurrence',once,row=0,primary=True,disabled=q[5] or not ready(qid) or bool(ownership(qid)[0]) or not ui.available(owner))
            if q[2] in WEEKLY_FREQUENCIES:
                for offset,label in ((0,'This week'),(1,'Next week')):
                    async def week(i,offset=offset):
                        if not await self.interaction_check(i):return
                        async with lock:
                            notice=ui.signup(owner,qid,ui.week_key(offset)) if ui.snapshot(qid)==expected else 'This chore changed. Review it again.'
                        await present(i,back(),notice)
                    self.button(label,week,row=1)
            if ui.repeating.shifts(qid):self.button('Repeating weekdays / shifts',lambda i:present(i,Repeating(owner,qid,i.guild)),row=2)
            self.nav(back)


    def attach_quiet_undo(frame,source):
        undo_candidates=[]
        pending=undoable_skip(source.owner) if isinstance(source,(Browse,Card,Chores)) else None
        if pending:
            skip_id,qid,_,_=pending
            label='Undo skip: '+chore(qid)[1]
            undo_button=discord.ui.Button(label=label[:80],style=discord.ButtonStyle.danger)
            async def undo_click(i):
                if not await source.interaction_check(i):return
                await i.response.defer()
                async with lock:notice=undo_skip(i.user.id,skip_id)
                target=browse_return(source,i.guild) if isinstance(source,Browse) else source.rebuild() if isinstance(source,Chores) else source.return_to()
                await present(i,target,notice)
            undo_button.callback=undo_click
            stamp=db.execute('SELECT skipped_at FROM occurrence_skips WHERE id=?',(skip_id,)).fetchone()[0]
            undo_candidates.append((stamp,undo_button,'Skipped · '+chore(qid)[1]))
        dated_pending=ui.dated.latest_undo(source.owner) if isinstance(source,(Browse,Card,Chores)) else None
        if dated_pending:
            event_id,qid,day,slot=dated_pending
            dated_undo=discord.ui.Button(label=('Undo skip: '+day.strftime('%a %b %d')+' '+('All day' if slot=='day' else slot.upper())+' '+chore(qid)[1])[:80],style=discord.ButtonStyle.danger)
            async def undo_dated(i,event_id=event_id):
                if not await source.interaction_check(i):return
                await i.response.defer()
                async with lock:notice=ui.dated.undo(i.user.id,event_id)
                target=browse_return(source,i.guild) if isinstance(source,Browse) else source.rebuild() if isinstance(source,Chores) else source.return_to()
                await present(i,target,notice)
            dated_undo.callback=undo_dated
            stamp=db.execute('SELECT changed_at FROM dated_occurrence_changes WHERE id=?',(event_id,)).fetchone()[0]
            undo_candidates.append((stamp,dated_undo,'Skipped · '+chore(qid)[1]+' · '+day.strftime('%a %b %d')))
        if getattr(source,'dated_undo_id',None):
            undo=discord.ui.Button(label='Undo skip for this occurrence',style=discord.ButtonStyle.danger)
            undo.callback=source.dated_undo_callback
            stamp=db.execute('SELECT changed_at FROM dated_occurrence_changes WHERE id=?',(source.dated_undo_id,)).fetchone()[0]
            undo_candidates.append((stamp,undo,'Skipped this dated occurrence'))

        done_pending=ui.undoable_completion(source.owner) if isinstance(source,(Browse,Card,Chores)) else None
        if done_pending:
            event_id,qid,name=done_pending
            undo_done=discord.ui.Button(label=('Undo Done: '+name)[:80],style=discord.ButtonStyle.danger)
            async def undo_done_click(i,event_id=event_id):
                if not await source.interaction_check(i):return
                await i.response.defer()
                async with lock:notice=ui.undo_completion(i.user.id,event_id)
                target=browse_return(source,i.guild) if isinstance(source,Browse) else source.rebuild() if isinstance(source,Chores) else source.return_to()
                await present(i,target,notice)
            undo_done.callback=undo_done_click
            stamp=db.execute('SELECT completed_at FROM completion_log WHERE id=?',(event_id,)).fetchone()[0]
            undo_candidates.append((stamp,undo_done,'Done · '+name))

        if undo_candidates:
            _,undo_control,description=max(undo_candidates,key=lambda candidate:datetime.fromisoformat(candidate[0]))
            undo_control.label='↶ Undo'
            undo_control.style=discord.ButtonStyle.secondary
            frame.add_item(discord.ui.Section(discord.ui.TextDisplay('-# '+description),accessory=undo_control),slot='undo')

    ACTION_ICONS={'Your color':'🎨','Claim':'✋','Done':'✅','Skip':'⏭','Skip this occurrence':'⏭','Need help':'🙋','Stuck / need help':'🙋','Other dates':'📅','Manage chores':'✏️','Settings':'⚙','Chore reminders':'🔔','Trade alerts':'🔁','Add chore':'➕','Archived chores':'🗃️','Back':'↩','Back to list':'↩','Back to chores':'↩','Checklist':'☑','Reassign':'👥','Propose trade':'🔁','Completion history':'📜','Change schedule':'📅','Edit chore':'✏️'}
    ACTION_ICONS.update({'Signup options':'📅','Sign-up schedule':'📅','Take this week':'✋','Take next week':'✋','Release this week':'↩','Release next week':'↩','Every week · ongoing':'🔁','Choose occurrence':'📅','Duplicate chore':'💠','Estimate / checklist':'☑','Give feedback':'💬','Change regular day':'📅','Move this occurrence':'📅','Cancel occurrence move':'↩','Drop responsibility':'↩','Separate AM and PM sign-ups':'🌗','List length':'📏','Household tools':'🧰','Search':'🔎'})
    def decorate_actions(frame):
        for item in frame.walk_children():
            if isinstance(item,discord.ui.Button) and item.label in ACTION_ICONS:item.emoji=ACTION_ICONS[item.label]
            if isinstance(item,discord.ui.Select):
                for option in item.options:
                    if option.label in ACTION_ICONS:option.emoji=ACTION_ICONS[option.label]

    SIGNUP_ACTIONS={'Sign-up schedule','Every week · ongoing','Take this week','Take next week','Release this week','Release next week'}
    MENU_DETAILS={
        'Reassign':('People · Reassign','Give responsibility to someone else.'),
        'Propose trade':('People · Propose trade','Offer an exchange.'),
        'Drop responsibility':('People · Drop responsibility','Release your current responsibility.'),
        'Choose occurrence':('Schedule · Choose occurrence','Choose an exact date and slot.'),
        'Move this occurrence':('Schedule · Move occurrence','Change this occurrence’s date.'),
        'Cancel occurrence move':('Schedule · Cancel move','Return to the regular schedule.'),
        'Change regular day':('Schedule · Change regular day','Set the repeating weekday.'),
        'Change schedule':('Schedule · Repeat pattern','Change how often this chore repeats.'),
        'Separate AM and PM sign-ups':('Schedule · Split AM / PM','Make morning and evening independent chores.'),
        'Edit chore':('Edit · Chore details','Change instructions, room or points.'),
        'Estimate / checklist':('Edit · Checklist & estimate','Change steps or estimated time.'),
        'Duplicate chore':('Edit · Duplicate chore','Create a separate copy.'),
        'Give feedback':('Review · Give feedback','Suggest an improvement or point value.'),
        'Completion history':('History · Completions','See past work.')}
    SIGNUP_DESCRIPTIONS={'Take this week':'Take responsibility for this household week.','Take next week':'Take responsibility for the next household week.','Release this week':'Release this week; keep later signups.','Release next week':'Release only the next household week.','Every week · ongoing':'Keep responsibility until you release it.','Sign-up schedule':'Choose repeating weekdays or shifts.'}
    def action_picker(source,actions,placeholder):
        grouped=placeholder in ('Actions…','More…','Choose a tool…')
        if grouped:
            ranks={label:n for n,label in enumerate(list(SIGNUP_DESCRIPTIONS)+list(MENU_DETAILS))}
            actions=sorted(actions,key=lambda b:ranks.get(b.label,len(ranks)))
        options=[]
        for n,b in enumerate(actions):
            label,description=(('Sign up · '+b.label,SIGNUP_DESCRIPTIONS[b.label]) if b.label in SIGNUP_DESCRIPTIONS else MENU_DETAILS.get(b.label,('Other · '+b.label,'Open this chore tool.'))) if grouped else (b.label,SIGNUP_DESCRIPTIONS.get(b.label))
            emoji=ACTION_ICONS.get(b.label)
            if grouped:
                category,_,action=label.partition(' · ')
                if not action:category,action='Other',label
                action={'Chore details':'Edit chore details','Checklist & estimate':'Edit checklist & estimate','Repeat pattern':'Change repeat pattern','Completions':'Completion history'}.get(action,action)
                if category in ('People','Schedule'):
                    action_icon={'Reassign':'➡️','Propose trade':'🔁','Drop responsibility':'↩️','Choose occurrence':'🔎','Move this occurrence':'➡️','Cancel occurrence move':'↩️','Change regular day':'🔁','Change schedule':'🔁','Separate AM and PM sign-ups':'➗'}.get(b.label,emoji)
                    action=action_icon+' '+action
                    emoji={'People':'👥','Schedule':'📅'}[category]
                label=action
                description=category+' · '+(description or 'Open this chore tool.')
            options.append(discord.SelectOption(label=label[:100],value=str(n),description='Unavailable right now' if b.disabled else description,emoji=emoji))
        picker=discord.ui.Select(placeholder=placeholder,options=options)
        async def choose(i):
            if not await source.interaction_check(i):return
            try:
                index=int(picker.values[0])
                if not 0<=index<len(actions):raise ValueError('Invalid action')
                action=actions[index]
            except (ValueError,IndexError):return await i.response.send_message('Choose an action from this list.',ephemeral=True)
            if action.disabled:return await i.response.send_message('That action is unavailable. Refresh this screen.',ephemeral=True)
            await getattr(action,'_sprig_recovery_callback',action.callback)(i)
        picker.callback=choose;picker._sprig_menu_actions=tuple(actions)
        return picker

    class ChoreMore(View):
        def __init__(self,owner,card):
            super().__init__(owner)
            self.recovery_context={'screen':'chore_more','qid':card.qid,'offset':card.recovery_context.get('offset',0),'parent':card.recovery_context.get('parent',{'screen':'dashboard'})}
            self.embed=discord.Embed(title='More · '+card.embed.title,description='Occasional tools for this chore.',color=0x6B9B77)
            actions=[b for b in card.children if isinstance(b,discord.ui.Button) and b.label not in SIGNUP_ACTIONS|{'Claim','Done','Checklist','Skip this occurrence','Stuck / need help','Need help','Back','Dashboard','Refresh','Refresh / Resume'}]
            if actions:self.add_item(action_picker(self,actions,'Choose a tool…'))
            self.nav(card.return_to)

    def work_card(frame,source,notice=None):
        q=chore(source.qid)
        just_finished=bool(q and q[5] and not ui.is_archived(source.qid) and 'completed quest #' in str(notice or source.embed.description or ''))
        frame.heading(discord.ui.TextDisplay('# Done' if just_finished else '# Chore details' if q else '# Chore unavailable'),page_help_button(source))
        if just_finished:
            card=discord.ui.Container(accent_colour=0x6B9B77)
            card.add_item(discord.ui.TextDisplay('## ✅ '+clean(q[1],100)))
            card.add_item(discord.ui.TextDisplay(f'Done — nice work! · +{q[3]} points'))
            card.add_item(discord.ui.TextDisplay('-# '+due_text(q).replace('Completed · returns ','Returns ').replace('Completed · does not repeat','Does not repeat')))
            card.add_item(discord.ui.TextDisplay('**Repeats:** '+timing.repeat_text(q[2])))
            frame.add_item(card)
            back=next((b for b in source.children if getattr(b,'label',None)=='Back'),None)
            if back:
                button=discord.ui.Button(label='Back to chores',style=discord.ButtonStyle.primary)
                button.callback=getattr(back,'_sprig_recovery_callback',back.callback)
                frame.rows([button])
            return discord.ui.Button(label='Refresh')
        if not q or ui.is_archived(source.qid):
            frame.add_item(discord.ui.TextDisplay('This chore is archived or unavailable.'))
        else:
            uid,scope=ownership(source.qid,getattr(source,'offset',0))
            status=('Yours' if str(uid)==str(source.owner) else clean(person(uid,getattr(source,'guild',None)),80))
            card=discord.ui.Container(accent_colour=0x6B9B77)
            card.add_item(discord.ui.TextDisplay('## '+clean(q[1],100)))
            card.add_item(discord.ui.TextDisplay('**Repeats:** '+timing.repeat_text(q[2])))
            if q[5]:
                card.add_item(discord.ui.TextDisplay('### ✅ Done — nice work!'))
                card.add_item(discord.ui.Separator())
                instructions=clean(q[8] or 'No extra instructions.',1200)
                card.add_item(discord.ui.TextDisplay('**Completed**\n'+'\n'.join('-# '+line for line in instructions.splitlines())))
                card.add_item(discord.ui.TextDisplay('-# '+(due_text(q).replace('Completed · returns ','Returns ').replace('Completed · does not repeat','Does not repeat'))))
            else:
                card.add_item(discord.ui.TextDisplay(status+f' · {q[3]} points · '+due_text(q)))
                card.add_item(discord.ui.Separator())
                card.add_item(discord.ui.TextDisplay('**To do**\n'+clean(q[8] or 'No extra instructions.',1200)))
            frame.add_item(card)
            if notice or source.embed.description:
                message=str(notice or source.embed.description)
                if q[5] and 'completed quest #' in message:message=''
                if message:frame.add_item(discord.ui.TextDisplay('-# '+message),slot='undo')
            for field in source.embed.fields:
                if field.name.startswith('⚠'):card.add_item(discord.ui.TextDisplay('**'+field.name+'**\n'+field.value))
            controls=[b for b in source.children if isinstance(b,discord.ui.Button) and b.label not in ('Back','Dashboard','Refresh','Refresh / Resume')]
            main=[];secondary=[];signups=[];occasional=[]
            for item in controls:
                if item.label in ('Claim','Done','Checklist','Skip this occurrence','Stuck / need help','Need help'):
                    copy=discord.ui.Button(label={'Skip this occurrence':'Skip','Stuck / need help':'Need help'}.get(item.label,item.label),style=item.style if item.label in ('Claim','Done') else discord.ButtonStyle.secondary,disabled=item.disabled)
                    copy.callback=getattr(item,'_sprig_recovery_callback',item.callback)
                    (main if item.label in ('Claim','Done','Checklist') else secondary).append(copy)
                elif item.label in SIGNUP_ACTIONS:signups.append(item)
                else:occasional.append(item)
            back=next((b for b in source.children if getattr(b,'label',None)=='Back'),None)
            if back:
                copy=discord.ui.Button(label='Back to chores',style=discord.ButtonStyle.primary if q[5] else discord.ButtonStyle.secondary)
                copy.callback=getattr(back,'_sprig_recovery_callback',back.callback)
                if any(b.label=='Done' for b in main):main.insert(0,copy)
                else:main.append(copy)
            if not q[5]:frame.add_item(discord.ui.TextDisplay('-# ACTIONS'),slot='actions')
            frame.rows(main)
            if any(b.label=='Claim' for b in main):frame.add_item(discord.ui.TextDisplay('-# Just this occurrence'))
            if signups or occasional:frame.add_item(discord.ui.ActionRow(action_picker(source,signups+occasional,'Actions…')))
            secondary.sort(key=lambda b:{'Skip':0,'Need help':1}.get(b.label,2))
            if not q[5]:frame.rows(secondary)
        if not q or ui.is_archived(source.qid):
            back=next((b for b in source.children if getattr(b,'label',None)=='Back'),None)
            if back:
                copy=discord.ui.Button(label='Back to list',style=discord.ButtonStyle.secondary)
                copy.callback=getattr(back,'_sprig_recovery_callback',back.callback);frame.rows([copy])
        refresh=discord.ui.Button(label='Refresh')
        return refresh

    class LayoutPanel(discord.ui.LayoutView):
        """V2-only wire layout; the source retains the existing navigation and rules."""
        def __init__(self,source,notice=None):
            super().__init__(timeout=600)
            self.source,self.owner,self.notice=source,source.owner,notice
            for item in source.children:
                if isinstance(item,discord.ui.Button):
                    if hasattr(item,'_sprig_original_label'):item.label=item._sprig_original_label
                    if (not getattr(item,'_sprig_navigation',False) and not hasattr(item,'_sprig_checklist_step')) or item.label=='Dashboard':
                        item.style=action_style(item.label,item.style)
                    if item.label in ('Previous','Next','Previous page','Next page','Previous day','Next day'):
                        item.emoji=None

            if isinstance(source,(Chores,Card)):
                source.page_name=screen_name(source)
                self.page_spec=page_spec('Card' if isinstance(source,Card) else 'Browse','Work card' if isinstance(source,Card) else 'Daily sheet','Finish a chore' if isinstance(source,Card) else 'Start here')
                frame=self.layout_plan=PagePlan(self.page_spec)
                refresh=work_card(frame,source,notice) if isinstance(source,Card) else source.build(frame,notice)
                section=frame.slots['header'][0]
                frame.slots['header']=[section.children[0]]
                refresh.label='↻'
                home=discord.ui.Button(label='🏠',style=discord.ButtonStyle.primary)
                home.callback=lambda i:present(i,Dashboard(source.owner,i.guild,i.user))
                gear=discord.ui.Button(label='⚙',style=discord.ButtonStyle.secondary)
                gear.callback=lambda i:present(i,PersonalSettings(source.owner,i.guild,lambda:recovery.restore(source.owner,recovery.bookmark(source),i.guild)))
                frame.rows([home,refresh,gear,section.accessory],slot='header')
                attach_quiet_undo(frame,source)
                decorate_actions(frame)
                frame.commit(self)
                recovery.attach(self,source,resume=refresh)
                return
            embed=getattr(source,'embed',None)
            if embed is None:
                source.embed=embed=discord.Embed(title=screen_name(source),color=0x6B9B77)
            elif not embed.title:embed.title=screen_name(source)
            source.page_name=screen_name(source)
            self.page_spec=page_spec(type(source).__name__,source.page_name,PAGE_TOPICS.get(type(source).__name__,'Start here'))
            frame=self.layout_plan=PagePlan(self.page_spec)
            budget=3900
            def text(value):
                nonlocal budget
                value=str(value or '')
                if not value or budget<=0:return None
                if len(value)>budget:value=value[:max(0,budget-1)]+'…'
                budget-=len(value)
                return discord.ui.TextDisplay(value)
            header=text((('**'+str(notice)+'**\n\n') if notice and not isinstance(source,PersonalSettings) else '')+(('# '+source.page_name+'\n') if embed and embed.title else '')+(embed.description or '' if embed else ''))
            if isinstance(source,PersonalSettings):header=text('# '+source.page_name)
            if header and not isinstance(source,Dashboard):frame.heading(header,page_help_button(source))
            if isinstance(source,PersonalSettings):frame.add_item(discord.ui.TextDisplay('-# '+str(embed.description).replace('\n','\n-# ')))
            if isinstance(source,Dashboard):
                buttons={item.label:item for item in source.children if isinstance(item,discord.ui.Button)}
                heading=text((('**'+str(notice)+'**\n\n') if notice else '')+'# '+embed.title+'\n'+embed.footer.text)
                help_button=buttons.get('Help') or buttons.get('?')
                help_button.label='?'
                help_button.callback=page_help_button(source).callback
                help_button._sprig_recovery_callback=help_button.callback
                help_button._sprig_navigation=True
                if heading:frame.add_item(discord.ui.Section(heading,accessory=help_button),slot='header')
                for field in embed.fields:
                    item=text('**'+field.name+'** · '+field.value)
                    if item:frame.add_item(item)
                trade=next(label for label in buttons if label.startswith('Trades ('))
                review=next((label for label in buttons if label.startswith('Review inbox (')),None)
                planning=['Who’s home?','Workload & pace',trade]
                if source.owner!=OWNER:planning.append('Household setup')
                groups=[('Do chores',['Chores','Needs attention']),
                    ('Plan & coordinate',planning),
                    ('Your activity',['Points & standings','Continue where I left off']),
                    ('Owner tools',[review,'Update announcements','Household setup'] if source.owner==OWNER else [])]
                settings_row=None
                menu=discord.ui.Container(accent_colour=self.page_spec.accent)
                for title,labels in groups:
                    items=[buttons[label] for label in labels if label in buttons]
                    if not items:continue
                    menu.add_item(discord.ui.TextDisplay('**'+title+'**'))
                    width=4 if title=='My settings' else 5
                    for start in range(0,len(items),width):
                        row=discord.ui.ActionRow(*items[start:start+width])
                        menu.add_item(row)
                        if title=='My settings':settings_row=row
                frame.add_item(menu,slot='content')
                refresh=discord.ui.Button(label='Refresh',style=discord.ButtonStyle.secondary)
                heading_section=frame.slots['header'][0]
                frame.slots['header']=[heading_section.children[0]]
                top=discord.ui.ActionRow()
                for label,callback in [('🏠',lambda i:present(i,Dashboard(source.owner,i.guild,i.user))),('↻',lambda i:present(i,Dashboard(source.owner,i.guild,i.user))),('⚙',lambda i:present(i,PersonalSettings(source.owner,i.guild,lambda:recovery.restore(source.owner,source.recovery_context if hasattr(source,'recovery_context') else recovery.bookmark(source),i.guild)))),('?',page_help_button(source).callback)]:
                    b=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if label=='🏠' else discord.ButtonStyle.secondary);b.callback=callback;top.add_item(b)
                    if label=='↻':refresh=b
                frame.add_item(top,slot='header')
                decorate_actions(frame)
                frame.commit(self)
                recovery.attach(self,source,resume=refresh)
                return
            calendar_scope=getattr(source,'recovery_context',{}).get('screen') in ('calendar','day')
            if calendar_scope:
                scopes=[c for c in source.children if isinstance(c,discord.ui.Button) and c.label in ('Mine','Everyone')]
                frame.rows(scopes,slot='toolbar')
            if isinstance(source,Manage):frame.rows(source.top_actions,slot='actions')
            points_screen=isinstance(source,Points)
            calendar_day=getattr(source,'recovery_context',{}).get('screen')=='day'
            calendar_details=getattr(source,'calendar_details',[])
            context=getattr(source,'recovery_context',{})
            calendar_week=context.get('screen')=='calendar' and context.get('mode')=='week'
            checklist=context.get('screen')=='checklist'
            browse_screen=isinstance(source,Browse)
            body=discord.ui.Container(accent_colour=self.page_spec.accent) if embed and embed.fields else None
            def add_body(item):
                if body is not None:body.add_item(item)
                else:frame.add_item(item,slot='content')
            card_metadata=None
            if embed:
                for index,field in enumerate(embed.fields):
                    # Lists stay compact; instructions and warnings keep their line breaks.
                    summary_limit=max(24,(budget-250)//max(1,len(embed.fields)-index)-len(field.name)-12)
                    list_summary=browse_screen or calendar_day or hasattr(source,'list_page_size')
                    value=(field.value[:min(450,summary_limit)]+('…' if len(field.value)>min(450,summary_limit) else '')).replace('\n',' · ') if list_summary else field.value
                    if checklist and field.value in ('Checked','Not checked'):
                        content=text(field.name)
                    else:
                        inline=points_screen or calendar_week or (not browse_screen and not calendar_day and '\n' not in value and len(value)<=130 and field.name not in ('Instructions','Feedback'))
                        if calendar_week or (isinstance(source,Card) and field.name in ('Responsibility','When','Points and room','Estimate and checklist')):
                            value=value.replace('\n',' · ')
                            inline=True
                        content=text('**'+field.name+'**'+(' · ' if inline else '\n')+value)
                    if not content:break
                    if checklist and index<len(getattr(source,'step_buttons',[])):
                        add_body(discord.ui.ActionRow(source.step_buttons[index]))
                    elif isinstance(source,Trips) and not source.people and index<len(source.people_details):
                        uid=source.people_details[index]
                        async def change_person(i,uid=uid):
                            if not await source.interaction_check(i):return
                            await present(i,Trips(source.owner,i.guild,[uid],roster_page=source.recovery_context['page']))
                        add_body(frame.detail_row(content,label='Change',callback=change_person,navigation=True))
                    elif isinstance(source,Attention) and index<len(source.attention_details):
                        qid=source.attention_details[index]
                        async def attention_details(i,qid=qid):
                            if not await source.interaction_check(i):return
                            parent=lambda:Attention(source.owner,i.guild,source.page)
                            await present(i,Card(source.owner,qid,parent,i.guild))
                        add_body(frame.detail_row(content,label='Details',callback=attention_details,navigation=True))
                    elif isinstance(source,Manage) and index<len(source.manage_details):
                        qid,expected=source.manage_details[index]
                        async def edit(i,qid=qid,expected=expected):await source.edit(i,qid,expected)
                        add_body(frame.detail_row(content,label='Edit',callback=edit))
                    elif calendar_day and index<len(calendar_details):
                        qid,open_chore=calendar_details[index]
                        async def details(i,qid=qid,open_chore=open_chore):
                            if not await source.interaction_check(i):return
                            await open_chore(i,qid)
                        add_body(frame.detail_row(content,label='Details',callback=details,navigation=True))
                    elif isinstance(source,Browse) and index<len(source.quick_rows):
                        qid,expected,can_done=source.quick_rows[index]
                        q=chore(qid);uid=ownership(qid)[0]
                        current=source.state['tab'] not in ('next','upcoming','done') and not q[5] and ready(qid)
                        back=lambda:Browse(source.owner,**source.state,guild=getattr(source,'guild',None))
                        name=discord.ui.Button(label=((timing.emoji(q[2])+' ' if timing.emoji(q[2]) else '')+q[1][:55]+(' · AM slot' if q[2] in ('daily-am','twice-daily') and (q[2]!='twice-daily' or timing.now().hour<12) else ' · PM slot' if q[2] in ('daily-pm','twice-daily') else '')+f' · {q[3]} points')[:80],style=discord.ButtonStyle.secondary)
                        async def details(i,qid=qid):
                            if not await source.interaction_check(i):return
                            parent=lambda:Browse(source.owner,**source.state,guild=i.guild)
                            await present(i,Card(source.owner,qid,parent,i.guild,1 if source.state['tab']=='next' else 0))
                        name.callback=details
                        name._sprig_navigation=True
                        action=discord.ui.Button(label='Done' if can_done else 'Claim' if not uid else ('Taken: '+clean(person(uid,getattr(source,'guild',None)),30)),style=discord.ButtonStyle.success if can_done else discord.ButtonStyle.primary if not uid else discord.ButtonStyle.secondary,disabled=not current or (bool(uid) and uid!=str(source.owner)) or not ui.available(source.owner))
                        future_picker=source.state['tab'] in ('next','upcoming','week') and not current and bool(ui.dated.slots(qid))
                        if future_picker:action.label='Choose date';action.disabled=False
                        pending_steps=can_done and not ui.planning.complete(qid)
                        async def act(i,qid=qid,expected=expected,can_done=can_done,pending_steps=pending_steps,current=current):
                            if not await source.interaction_check(i):return
                            parent=lambda:Browse(source.owner,**source.state,guild=i.guild)
                            if source.state['tab'] in ('next','upcoming','week') and not current and ui.dated.slots(qid):
                                return await present(i,OccurrenceDates(source.owner,qid,i.guild,back=parent,week=1 if source.state['tab']=='next' else 0))
                            if not can_done:return await claim_now(i,source,qid,expected,parent)
                            if pending_steps or not ui.planning.complete(qid):return await present(i,ui.planning.Checklist(source.owner,qid,i.guild,lambda:Card(source.owner,qid,parent,i.guild)))
                            async def change():
                                async with lock:
                                    ns['reset_due_quests']()
                                    if ui.snapshot(qid)!=expected:return 'This occurrence changed. Review the refreshed list.'
                                    context=ui.Context(i);await bot.get_command('done').callback(context,qid)
                                    return '\n'.join(context.messages)
                            task=asyncio.create_task(change())
                            finished,_=await asyncio.wait({task},timeout=1.0)
                            if not finished:await i.response.defer()
                            await present(i,parent(),await task)
                        action.callback=act
                        skip=discord.ui.Button(label='Skip',style=discord.ButtonStyle.secondary,disabled=(not current and not future_picker) or q[2]=='one-time')
                        async def skip_click(i,qid=qid,expected=expected,future_picker=future_picker):
                            if not await source.interaction_check(i):return
                            parent=lambda:Browse(source.owner,**source.state,guild=i.guild)
                            if future_picker:return await present(i,OccurrenceDates(source.owner,qid,i.guild,back=parent,week=1 if source.state['tab']=='next' else 0))
                            await i.response.defer()
                            async with lock:notice=skip_occurrence(i.user.id,qid,expected)
                            await present(i,parent(),notice)
                        skip.callback=skip_click
                        add_body(discord.ui.ActionRow(name,action,skip))
                    elif isinstance(source,Card) and field.name in ('Responsibility','When','Points and room','Estimate and checklist'):
                        if card_metadata is None:
                            card_metadata=content;add_body(card_metadata)
                        else:card_metadata.content+='\n'+content.content
                    else:add_body(content)
                if body is not None and body.children:frame.add_item(body,slot='content')
                footer_value=embed.footer.text if embed.footer and embed.footer.text else ''
                if browse_screen:footer_value=footer_value.split(' · Eastern time')[0]+' · Eastern time'
                footer=text('-# '+footer_value) if footer_value else None
                if footer:frame.add_item(footer,slot='footer')
            rows={}
            inline_room=max(0,33-len(list(frame.walk_children()))-2*len(source.children))
            row_ids={child['custom_id']:index for index,row in enumerate(source.to_components()) for child in row.get('components',[]) if 'custom_id' in child}
            paging=[]
            week_days=[]
            paging_labels=getattr(source,'paging_labels',None)
            if paging_labels is None and isinstance(source,(Browse,Attention,Points,ResetHistory,History,Inbox,Trips)):
                paging_labels=('Previous','Next')
            if paging_labels is None and embed and embed.footer and 'Page ' in (embed.footer.text or ''):
                paging_labels=('Previous','Next')
                for item in source.children:
                    if isinstance(item,discord.ui.Button) and item.label in ('Previous page','Next page'):
                        item.label='Previous' if item.label=='Previous page' else 'Next'
            for item in source.children:
                if calendar_scope and isinstance(item,discord.ui.Button) and item.label in ('Mine','Everyone'):continue
                if isinstance(source,Manage) and item in source.top_actions:continue
                if hasattr(item,'_sprig_checklist_step'):continue
                if calendar_week and isinstance(item,discord.ui.Button) and item.row in (1,2):
                    week_days.append(item);continue
                if isinstance(item,discord.ui.Button) and item.label in ('Refresh','Refresh / Resume'):continue
                if calendar_day and isinstance(item,discord.ui.Select) and item.placeholder=='Choose chore':continue
                if isinstance(source,(Browse,Attention)) and isinstance(item,discord.ui.Select) and item.placeholder=='Open a chore card…':
                    continue  # Each chore already has its own Details button.
                # Paired pickup controls use the existing Refresh / Resume;
                # omit the duplicate Refresh to stay within Discord's limit.
                if isinstance(source,Browse) and source.state['area'] in ('pickup','household') and isinstance(item,discord.ui.Button) and item.label=='Refresh':
                    continue
                if isinstance(item,discord.ui.Button) and paging_labels and item.label in paging_labels:
                    paging.append(item)
                    continue
                row=row_ids.get(item.custom_id,item.row if item.row is not None else 0)
                if isinstance(item,discord.ui.Select) and item.placeholder=='Choose a chore' and (getattr(source,'qid',None) is not None or getattr(source,'selected',None) is not None):continue
                if isinstance(item,(discord.ui.Select,discord.ui.UserSelect)):
                    # Preserve compact native choices and their guarded callbacks.
                    rows.setdefault(row,[]).append(item)
                    continue
                rows.setdefault(row,[]).append(item)
            if week_days:
                rows[1]=week_days[:4]
                rows[2]=week_days[4:]
            if paging_labels:frame.paging(paging_labels,paging)
            if body is not None or paging_labels:frame.add_item(discord.ui.Separator(),optional=True)
            utility_row=None
            if points_screen:
                controls={getattr(item,'label',None):item for items in rows.values() for item in items}
                owner_tools=[controls[label] for label in ('Reset points','Reset history / Undo') if label in controls]
                if owner_tools:
                    frame.add_item(discord.ui.TextDisplay('### Owner controls'))
                    frame.add_item(discord.ui.ActionRow(*owner_tools))
                utility_row=discord.ui.ActionRow(controls['Dashboard'])
            elif calendar_day:
                controls={getattr(item,'label',None):item for items in rows.values() for item in items}
                frame.add_item(discord.ui.ActionRow(*(controls[label] for label in ('Previous day','Today','Next day'))))
                frame.rows(controls[label] for label in ('Week','Month'))
                utility_row=discord.ui.ActionRow(*(controls[label] for label in ('Back','Dashboard')))
            elif isinstance(source,Card):
                controls=[item for items in rows.values() for item in items]
                navigation=[item for label in ('Back','Dashboard') for item in controls if isinstance(item,discord.ui.Button) and item.label==label]
                actions=[item for item in controls if item not in navigation]
                everyday=self.page_spec.action_groups[0]
                primary=[item for item in actions if everyday.accepts(item)]
                priority={label:n for n,label in enumerate(everyday.labels)}
                primary.sort(key=lambda item:priority.get(item.label,99))
                for item in primary:
                    item.label={'Stuck / need help':'Need help','Choose occurrence':'Choose date'}.get(item.label,item.label)
                frame.rows(primary)
                async def more_options(i):
                    if not await source.interaction_check(i):return
                    await present(i,CardActions(source.owner,source,'More options'))
                button=discord.ui.Button(label='More options',style=discord.ButtonStyle.secondary)
                button.callback=more_options
                frame.rows([button])
                utility_row=discord.ui.ActionRow(*navigation)
            elif browse_screen:
                utilities={getattr(item,'label',None):item for items in rows.values() for item in items
                    if isinstance(item,discord.ui.Button) and item.label in ('Search','Filters','Dashboard')}
                filters=[utilities[label] for label in ('Search','Filters')]
                for row,items in sorted(rows.items()):
                    remaining=[item for item in items if item not in utilities.values()]
                    if remaining and all(str(getattr(item,'label','')).startswith('View: ') or getattr(item,'label',None) in ('Unclaimed only','All') for item in remaining):filters.extend(remaining)
                    elif remaining:frame.rows(remaining)
                frame.rows(filters)
                utility_row=discord.ui.ActionRow(utilities['Dashboard'])
            else:
                # Keep selects and meaningful action groups intact, with one
                # consistent Back / Refresh / Dashboard row below them.
                navigation={getattr(item,'label',None):item for items in rows.values() for item in items
                    if isinstance(item,discord.ui.Button) and item.label in ('Back','Dashboard')}
                pending=[]
                form=discord.ui.Container(accent_colour=self.page_spec.accent) if body is None and not paging_labels else None
                def add_controls(row):
                    if form is not None:form.add_item(row)
                    else:frame.add_item(row)
                def flush():
                    if pending:
                        add_controls(discord.ui.ActionRow(*pending))
                        pending.clear()
                calendar_overview=getattr(source,'recovery_context',{}).get('screen')=='calendar'
                for row,items in sorted(rows.items()):
                    remaining=[item for item in items if item not in navigation.values()]
                    if not remaining:continue
                    if any(not isinstance(item,discord.ui.Button) for item in remaining):
                        flush();add_controls(discord.ui.ActionRow(*remaining));continue
                    if calendar_overview or len(pending)+len(remaining)>5:flush()
                    pending.extend(remaining)
                    if calendar_overview:flush()
                flush()
                utility_row=discord.ui.ActionRow(*(navigation[label] for label in ('Back','Dashboard') if label in navigation))
                if form is not None and form.children:frame.add_item(form)
            for item in frame.walk_children():
                if isinstance(item,discord.ui.Button):
                    if (not getattr(item,'_sprig_navigation',False) and not hasattr(item,'_sprig_checklist_step')) or item.label=='Dashboard':
                        item.style=action_style(item.label,item.style)
                    if item.label in ('Previous','Next','Previous page','Next page','Previous day','Next day'):
                        item.emoji=None
                        item._sprig_original_label=item.label
                        item.label={'Previous':'< Prev','Previous page':'< Prev','Next':'Next >','Next page':'Next >','Previous day':'<< Prev day','Next day':'Next day >>'}[item.label]
            refresh=frame.navigation(utility_row.children)
            if frame.slots['header']:
                section=frame.slots['header'][0]
                help_control=section.accessory
                title=section.children[0]
                frame.slots['header']=[title]
                home=discord.ui.Button(label='🏠',style=discord.ButtonStyle.primary)
                home.callback=lambda i:present(i,Dashboard(source.owner,i.guild,i.user))
                refresh.label='↻'
                gear=discord.ui.Button(label='⚙',style=discord.ButtonStyle.secondary)
                gear.callback=lambda i:present(i,PersonalSettings(source.owner,i.guild,lambda:recovery.restore(source.owner,source.recovery_context if hasattr(source,'recovery_context') else recovery.bookmark(source),i.guild)))
                frame.slots['navigation']=[]
                back=[b for b in utility_row.children if b.label=='Back']
                if back:frame.rows(back,slot='navigation')
                frame.rows([home,refresh,gear,help_control],slot='header')
            attach_quiet_undo(frame,source)
            decorate_actions(frame)
            if isinstance(source,PersonalSettings) and notice:frame.add_item(discord.ui.TextDisplay('-# '+str(notice)),slot='footer')
            frame.commit(self)
            recovery.attach(self,source,resume=refresh)

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
        if db.execute("SELECT 1 FROM dated_occurrences WHERE quest_id=? AND day>=? AND state!='released'",(qid,timing.now().date().isoformat())).fetchone():
            return 'Release dated claims and undo dated skips before splitting this chore.'
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
            db.execute("UPDATE repeating_signups SET quest_id=? WHERE quest_id=? AND shift='pm'",(pm_id,qid))
            db.execute('INSERT INTO chore_shift_splits VALUES(?,?)',(qid,pm_id))
        return 'Split into separate AM and PM chores. Existing weekly/ongoing ownership stays on AM; PM is open except for a current PM single claim. Earned points and old history are unchanged.'

    def skip_occurrence(actor,qid,expected):
        # Call under the shared mutation lock; validation and all writes are one transaction.
        ns['reset_due_quests']()
        q=chore(qid)
        if not q or ui.is_archived(qid) or ui.snapshot(qid)!=expected:
            return 'This chore changed. Review the refreshed card. Nothing skipped.'
        if q[5] or not ready(qid):return 'There is no due occurrence to skip.'
        if q[2]=='one-time':return 'This chore does not repeat. Archive it instead if it is no longer needed.'
        now=timing.now()
        next_due=timing.calculate_reset(now,q[2])
        if not next_due:return 'No next scheduled occurrence was found. Nothing skipped.'
        import json
        previous=json.dumps(dict(chore=q,timing=timing.state(qid),
            claim=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone(),
            move=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone()))
        previous_policy=json.dumps(timing.policy_state(qid))
        with db:
            cursor=db.execute('INSERT INTO occurrence_skips(quest_id,actor,skipped_at,next_due,previous_state) VALUES(?,?,?,?,?)',
                (qid,str(actor),now.isoformat(),next_due,previous))
            db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            db.execute('DELETE FROM occurrence_moves WHERE quest_id=?',(qid,))
            db.execute('INSERT OR REPLACE INTO chore_timing VALUES(?,?)',(qid,next_due))
            if timing.policy(qid)=='skip':
                db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(timing.deadline(qid,q[2]),qid))
            db.execute('INSERT INTO skip_undo_state(skip_id,expected,previous_policy) VALUES(?,?,?)',(cursor.lastrowid,json.dumps(ui.snapshot(qid)),previous_policy))
        return ('Occurrence skipped. No points awarded; weekly sign-ups and ongoing assignments stay saved. '
                +'Next due '+datetime.fromisoformat(next_due).strftime('%a %b %d, %I:%M %p %Z')+'.')

    def undoable_skip(actor):
        row=db.execute('SELECT s.id,s.quest_id,s.next_due,u.expected FROM occurrence_skips s JOIN skip_undo_state u ON u.skip_id=s.id WHERE s.actor=? AND u.undone_at IS NULL ORDER BY s.id DESC LIMIT 1',(str(actor),)).fetchone()
        if row and timing.now()<datetime.fromisoformat(row[2]) and json.dumps(ui.snapshot(row[1]))==row[3]:return row
        return None

    def undo_skip(actor,skip_id):
        ns['reset_due_quests']()
        row=db.execute('SELECT s.quest_id,s.actor,s.next_due,s.previous_state,u.expected,u.previous_policy,u.undone_at FROM occurrence_skips s JOIN skip_undo_state u ON u.skip_id=s.id WHERE s.id=?',(skip_id,)).fetchone()
        if not row or row[1]!=str(actor):return 'Only the person who skipped this occurrence can undo it.'
        qid,_,next_due,previous,expected,policy,undone=row
        if undone:return 'This skip was already undone.'
        if timing.now()>=datetime.fromisoformat(next_due) or ui.is_archived(qid) or json.dumps(ui.snapshot(qid))!=expected:
            return 'The chore changed or its next occurrence started. Nothing restored.'
        previous=json.loads(previous);policy=json.loads(policy)
        with db:
            for table in ('claims','occurrence_moves','chore_timing','missed_chore_policy'):
                db.execute('DELETE FROM '+table+' WHERE quest_id=?',(qid,))
            if previous['claim']:db.execute('INSERT INTO claims VALUES(?,?)',(qid,previous['claim'][0]))
            if previous['move']:db.execute('INSERT INTO occurrence_moves VALUES(?,?)',(qid,previous['move'][0]))
            if previous['timing']:db.execute('INSERT INTO chore_timing VALUES(?,?)',(qid,previous['timing'][0]))
            if policy:db.execute('INSERT INTO missed_chore_policy VALUES(?,?,?)',(qid,*policy))
            db.execute('UPDATE skip_undo_state SET undone_at=? WHERE skip_id=?',(timing.now().isoformat(),skip_id))
        return 'Skip undone. The occurrence and its previous claim are restored. No points changed.'

    Repeating=ui.repeating.install_views(SimpleNamespace(View=View,Confirm=lambda *a,**kw:Confirm(*a,**kw),Card=lambda *a,**kw:Card(*a,**kw),present=lambda *a,**kw:present(*a,**kw),person=person))

    class OccurrenceDates(View):
        def __init__(self,owner,qid,guild=None,back=None,week=0,page=0):
            super().__init__(owner)
            self.recovery_context={'screen':'occurrence_dates','qid':qid,'week':week,'page':page}
            back=back or (lambda:Card(owner,qid,guild=guild))
            q=chore(qid);start=(ui.week_start(week).date() if week is not None else timing.now().date())
            end=start+timedelta(days=8 if week is not None else 15)
            dates=list(ui.dated.upcoming(qid,start,end))
            if week is not None:dates=[(d,slot) for d,slot in dates if ui.week_start(week)<=ui.dated.when(d,slot)<ui.week_start(week+1)]
            page=min(max(0,page),max(0,(len(dates)-1)//10));chunk=dates[page*10:(page+1)*10]
            self.embed=discord.Embed(title='Choose occurrence · '+clean(q[1] if q else 'Unavailable',100),description='Choose an exact date and slot. Claims and skips affect only that occurrence. Eastern time.',color=0x6B9B77)
            self.embed.set_footer(text=f'Page {page+1} of {max(1,(len(dates)+9)//10)}')
            for index,(day,slot) in enumerate(chunk):
                row=ui.dated.record(qid,day,slot)
                suffix=' · Skipped' if row and row[1]=='skip' else ''
                label=day_badge(WEEKDAYS[day.weekday()])+' '+day.strftime('%b %d')+' · '+('All day' if slot=='day' else slot.upper())+suffix
                self.button(label,lambda i,day=day,slot=slot:present(i,FutureOccurrence(owner,qid,day,slot,i.guild,lambda:OccurrenceDates(owner,qid,i.guild,back,week,page))),row=index//5)
            self.button('Previous',lambda i:present(i,OccurrenceDates(owner,qid,i.guild,back,week,page-1)),row=2,disabled=page==0)
            self.button('Next',lambda i:present(i,OccurrenceDates(owner,qid,i.guild,back,week,page+1)),row=2,disabled=(page+1)*10>=len(dates))
            self.button('More dates',lambda i:present(i,OccurrenceDates(owner,qid,i.guild,back,(week or 0)+1)),row=3)
            self.button('Current occurrence',lambda i:present(i,Card(owner,qid,back,i.guild)),row=3)
            if not dates:self.embed.description+=' No future dates in this week. Try More dates, or Choose day for a flexible chore.'
            self.nav(back)

    class FutureSlots(View):
        def __init__(self,owner,qid,day,guild=None,back=None):
            super().__init__(owner)
            self.recovery_context={'screen':'future_slots','qid':qid,'day':day.isoformat()}
            self.embed=discord.Embed(title=clean(chore(qid)[1],100),description=day.strftime('%a %b %d, %Y')+' · Choose AM or PM · Eastern time',color=0x6B9B77)
            for slot in ui.dated.slots(qid):
                self.button('All day' if slot=='day' else slot.upper(),lambda i,slot=slot:present(i,FutureOccurrence(owner,qid,day,slot,i.guild,back)),row=0)
            self.nav(back)

    class FutureOccurrence(View):
        def __init__(self,owner,qid,day,slot,guild=None,back=None):
            super().__init__(owner)
            back=back or (lambda:OccurrenceDates(owner,qid,guild))
            self.recovery_context={'screen':'future_occurrence','qid':qid,'day':day.isoformat(),'slot':slot,'parent':recovery.bookmark(back())}
            q=chore(qid);at=ui.dated.when(day,slot);record=ui.dated.record(qid,day,slot)
            uid=ui.dated.owner(qid,at) or ui.dated.base_owner(qid,at)
            skipped=ui.dated.skipped(qid,at)
            self.name_ids=[uid] if uid else []
            self.rebuild=lambda:FutureOccurrence(owner,qid,day,slot,guild,back)
            stamp=day_badge(WEEKDAYS[day.weekday()])+' '+day.strftime('%b %d, %Y')+' · '+('All day' if slot=='day' else slot.upper())
            self.embed=discord.Embed(title=clean(q[1] if q else 'Unavailable',100),description=stamp+' · Eastern time\n'+('Skipped just this time' if skipped else clean(person(uid,guild),100))+f' · {q[3] if q else 0} points',color=0x6B9B77)
            self.embed.add_field(name='Just this occurrence',value='Later repeats and weekly/repeating signups stay saved. Future work cannot be marked Done early.',inline=False)
            if q and q[8]:self.embed.add_field(name='Instructions',value=clean(q[8],1000),inline=False)
            expected=ui.dated.snapshot(qid,day,slot)
            async def action(i,kind):
                if not await self.interaction_check(i):return
                await i.response.defer()
                async with lock:notice=ui.dated.change(i.user.id,qid,day,slot,kind,expected)
                await present(i,FutureOccurrence(owner,qid,day,slot,i.guild,back),notice)
            if ui.dated.valid(qid,day,slot) and at>timing.now():
                self.button('Claim just this time',lambda i:action(i,'claim'),row=0,primary=True,disabled=skipped or (uid is not None and uid!=str(owner)) or not ui.attendance.at(owner,at))
                self.button('Skip just this time',lambda i:action(i,'skip'),row=0,disabled=skipped)
            if record and record[1]=='claim' and record[2]==str(owner) and timing.now()<at+timedelta(hours=12 if slot in ('am','pm') else 24):
                self.button('Drop this dated claim',lambda i:action(i,'drop'),row=1)
            self.button('Open current chore',lambda i:present(i,Card(owner,qid,back,i.guild)),row=1)
            self.dated_undo_id=ui.dated.undo_id(owner,qid,day,slot)
            async def undo(i):
                if not await self.interaction_check(i):return
                await i.response.defer()
                async with lock:notice=ui.dated.undo(i.user.id,self.dated_undo_id)
                await present(i,FutureOccurrence(owner,qid,day,slot,i.guild,back),notice)
            self.dated_undo_callback=undo
            self.nav(back)

    class Card(View):
        def __init__(self, owner, qid, back=None, guild=None, offset=0, notice=None):
            super().__init__(owner)
            ns['reset_due_quests']()
            q = chore(qid)
            back = back or (lambda: Chores(owner,guild,who='mine'))
            self.guild=guild
            self.qid, self.expected = qid, ui.snapshot(qid)
            self.return_to=lambda:Card(owner,qid,back,guild,offset)
            self.recovery_context={'screen':'card','qid':qid,'offset':offset,'parent':recovery.bookmark(back())}
            self.embed = discord.Embed(title=clean(q[1], 200) if q else 'Chore unavailable', description=notice or '', color=0x6B9B77)
            if not q or ui.is_archived(qid):
                self.embed.description = 'This chore is archived or unavailable. Manage chores → Archived chores can restore it.'
                self.nav(back)
                return
            uid, scope = ownership(qid, offset)
            self.name_ids=[uid]
            self.rebuild=lambda:Card(owner,qid,back,guild,offset,notice)
            duration = {'assignment':'Every week · ongoing','week0':'This week · until Sunday 6 p.m.','week1':'Next week · Sunday 6 p.m. to Sunday 6 p.m.','occurrence':'Just this time','repeating':'Repeating weekday/shift · only when home','dated':'This date and slot only'}.get(scope, 'Available')
            self.embed.add_field(name='Responsibility', value=f'{clean(person(uid,guild),100)} · {duration}', inline=False)
            self.embed.add_field(name='When', value=f'Repeats: {timing.repeat_text(q[2])}\n{timing.label(q[2],qid)}\n{due_text(q)}', inline=False)
            self.embed.add_field(name='Points and room', value=f'{q[3]} points · {clean(q[9] or "Unspecified",100)}', inline=False)
            self.embed.add_field(name='Estimate and checklist',value=(ui.planning.summary(qid).removeprefix(' · ') or 'No estimate or checklist yet'),inline=False)
            help_status=ui.planning.help_record(qid)
            if help_status and not q[5]:self.embed.add_field(name='⚠ '+help_status[4],value=clean(help_status[5],500),inline=False)
            self.button('Stuck / need help',lambda i:present(i,ui.planning.HelpStatus(owner,qid,i.guild)),row=2)
            if ui.planning.steps(qid):self.button('Checklist',lambda i:present(i,ui.planning.Checklist(owner,qid,i.guild,card)),row=2)
            if ui.repeating.shifts(qid):
                self.button('Sign-up schedule',lambda i:present(i,Repeating(i.user.id,qid,i.guild)),row=2)
                saved=ui.repeating.slots(qid)
                self.name_ids.extend(uid for _,_,uid in saved)
                if saved:self.embed.add_field(name='Repeating days · only when home',value='\n'.join(f'{WEEKDAYS[d][:3].title()} · {shift.upper()} · {clean(person(uid,guild),70)}' for d,shift,uid in saved)[:1000],inline=False)
            if q[8]: self.embed.add_field(name='Instructions', value=clean(q[8], 1000), inline=False)
            card = lambda: Card(owner, qid, back, guild, offset)
            async def mutate(i, action):
                if action=='done' and not ui.planning.complete(qid):
                    return await present(i,ui.planning.Checklist(owner,qid,i.guild,card))
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
                self.button('Claim',lambda i:claim_now(i,self,qid,self.expected,back),row=0,primary=True,disabled=not ui.available(owner))
            if not q[5] and ready(qid) and offset==0 and q[2]!='one-time':
                async def skip(i):
                    if not await self.interaction_check(i):return
                    await i.response.defer()
                    async with lock:text=skip_occurrence(i.user.id,qid,self.expected)
                    await present(i,card(),text)
                self.button('Skip this occurrence',skip,row=2)
            week_snapshot = tuple(ui.weekly_owner(qid, n) for n in (0, 1))
            if q[2] in WEEKLY_FREQUENCIES and not q[4] and not ui.repeating.slots(qid):
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
                if not ui.repeating.slots(qid):self.button('Every week · ongoing',ongoing,row=0)
            options = [('Duplicate chore','duplicate'), ('Estimate / checklist','plan'), ('Give feedback','feedback'), ('Edit chore','edit'), ('Change schedule','schedule'), ('Reassign','reassign'), ('Completion history','history')]
            if q[2]=='twice-daily':options.append(('Separate AM and PM sign-ups','split'))
            if not q[5]: options.append(('Move this occurrence','move'))
            if db.execute('SELECT 1 FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone(): options.append(('Cancel occurrence move','unmove'))
            if uid == str(owner) and offset == 0: options.extend([('Drop responsibility','drop'),('Propose trade','trade')])
            if q[2] in ('weekly', *WEEKDAYS): options.append(('Change regular day','day'))
            if ui.dated.slots(qid):options.insert(0,('Choose occurrence','dated'))
            picker = discord.ui.Select(placeholder='More actions…', row=1, options=[discord.SelectOption(label=l, value=v) for l,v in options])
            async def more(i):
                value = picker.values[0]
                if value == 'dated':return await present(i,OccurrenceDates(owner,qid,i.guild,back=card))
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
                elif value == 'schedule':view=ui.AddChoreMenu(owner,qid,ui.snapshot(qid))
                elif value == 'edit':
                    ids = [r[0] for r in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(r[0])]
                    view = ui.EditChoreView(owner, ids.index(qid)//20, qid)
                elif value == 'reassign': view = ui.ReassignView(owner, qid=qid, scope='occurrence' if scope in ('repeating','dated') else scope, expected=ui.reassign_snapshot(qid),return_context=recovery.bookmark(back()))
                elif value == 'drop':
                    if scope=='dated':return await present(i,FutureOccurrence(owner,qid,timing.now().date(),ui.dated.key(qid)[1],guild=i.guild,back=card))
                    if scope=='repeating':return await present(i,Repeating(owner,qid,i.guild))
                    view = ui.DropChoreView(owner, qid, ui.snapshot(qid))
                elif value == 'trade': view = ui.TradeOfferView(owner, qid)
                else: view = ui.ChooseDayView(owner, qid, ui.snapshot(qid))
                await present(i, adapt(view, owner, card))
            picker.callback=more
            self.action_picker=picker
            for index,(label,value) in enumerate(options):
                async def action(i,value=value):
                    if not await self.interaction_check(i):return
                    picker._values=[value]
                    await more(i)
                row=next(row for row in (1,3,4) if sum(c.row==row for c in self.children)<(3 if row==4 else 5))
                self.button(label,action,row=row)
            self.nav(back)

    class CardActions(View):
        def __init__(self,owner,card,title):
            super().__init__(owner)
            self.recovery_context=dict(card.recovery_context)
            self.embed=discord.Embed(title=title+' · '+chore(card.qid)[1],description={
                'Who does it':'Choose who takes this chore and for how long. Each action keeps its stated dates or responsibility scope.',
                'Change this chore':'Change the chore for future repeats. Copying and separating shifts are advanced changes.',
                'More options':'Change who does this chore or when you do it. These choices keep their stated dates and scope. Chore editing is available separately.'}[title],color=0x6B9B77)
            groups=page_spec('Card','Chore details').action_groups
            group=next(g for g in groups if g.title==title)
            actions=[item for item in card.children if isinstance(item,discord.ui.Button) and item.label not in ('Back','Dashboard','Refresh','Refresh / Resume')]
            selected=[item for item in actions if not groups[0].accepts(item) and ((title=='More options' and not groups[2].accepts(item)) or (title!='More options' and group.accepts(item)))]
            if selected:
                picker=discord.ui.Select(placeholder='Choose what to change…' if title=='Change this chore' else 'Choose an occasional action…',options=[discord.SelectOption(label=item.label,value=str(n),description='Unavailable right now' if item.disabled else None) for n,item in enumerate(selected)])
                async def choose(i):
                    if not await self.interaction_check(i):return
                    try:
                        index=int(picker.values[0])
                        if not 0<=index<len(selected):raise ValueError('Invalid action')
                        action=selected[index]
                    except (IndexError,ValueError):return await i.response.send_message('Choose an action from this list.',ephemeral=True)
                    if action.disabled:return await i.response.send_message('That action is unavailable right now. Refresh this screen.',ephemeral=True)
                    await getattr(action,'_sprig_recovery_callback',action.callback)(i)
                picker.callback=choose
                picker._sprig_menu_actions=tuple(selected)
                self.add_item(picker)
            if title=='More options':
                self.button('Manage this chore',lambda i:present(i,CardActions(owner,card,'Change this chore')),row=4)
            self.nav(card.return_to)

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
            size=page_size(owner)
            self.list_page_size=size
            self.recovery_context={'screen':'history','qid':qid,'page':page,'parent':recovery.bookmark(back())}
            records = db.execute('SELECT id,user_id,chore_name,points,completed_at,undone_at FROM completion_log WHERE quest_id=? ORDER BY id DESC', (qid,)).fetchall()
            page = min(max(page,0),max((len(records)-1)//size,0))
            chunk = records[page*size:(page+1)*size]
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
            if (page+1)*size < len(records): self.button('Next',lambda i:present(i,History(owner,qid,back,page+1)),row=3)
            self.nav(back)

    class ManageSearch(discord.ui.Modal):
        def __init__(self,owner,query):
            super().__init__(title='Find a chore to manage')
            self.owner=owner
            self.term=discord.ui.TextInput(label='Name, instructions, or room',required=False,default=query,max_length=100)
            self.add_item(self.term)
        async def on_submit(self,i):
            if not await View(self.owner).interaction_check(i):return
            await present(i,Manage(self.owner,i.guild,query=self.term.value))

    class Manage(View):
        def __init__(self, owner, guild=None, page=0, query=''):
            super().__init__(owner)
            query=str(query).strip()[:100];size=page_size(owner)
            records=[chore(qid) for qid, in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not ui.is_archived(qid)]
            if query:records=[q for q in records if query.casefold() in ' '.join(str(q[n] or '') for n in (1,8,9)).casefold()]
            page=min(max(int(page),0),max((len(records)-1)//size,0))
            self.page,self.query,self.list_page_size=page,query,size
            self.recovery_context={'screen':'manage','page':page,'query':query,'list_size':size}
            self.embed=discord.Embed(title='Manage chores',description='Edit any active chore, including completed chores. History and earned points stay saved.'+('\nSearch: '+clean(query,100) if query else ''),color=0x6B9B77)
            self.manage_details=[]
            for q in records[page*size:(page+1)*size]:
                self.embed.add_field(name=clean(q[1],100),value=timing.label(q[2],q[0])+f' · {q[3]} points · '+clean(q[9] or 'Unspecified room',65),inline=False)
                self.manage_details.append((q[0],ui.snapshot(q[0])))
            if not records:self.embed.add_field(name='No matching chores' if query else 'No active chores',value='Clear search or add a chore. Archived chores can be restored.')
            self.embed.set_footer(text=f'Page {page+1} of {max((len(records)-1)//size+1,1)} · {len(records)} chore(s)')
            self.paging_labels=('Previous','Next')
            back=lambda:Manage(owner,guild,page,query)
            self.top_actions=[
                self.button('Add chore',lambda i:present(i,adapt(ui.AddChoreMenu(owner),owner,back)),row=0),
                self.button('Archive chore',lambda i:present(i,adapt(ui.RemoveChoreView(owner),owner,back)),row=0),
                self.button('Archived chores',lambda i:present(i,adapt(ui.RemoveChoreView(owner,removed=True),owner,back)),row=0)]
            self.button('Search',lambda i:i.response.send_modal(ManageSearch(owner,query)),row=1)
            if query:self.button('Clear search',lambda i:present(i,Manage(owner,i.guild)),row=1)
            if page:self.button('Previous',lambda i:present(i,Manage(owner,i.guild,page-1,query)),row=3)
            if (page+1)*size<len(records):self.button('Next',lambda i:present(i,Manage(owner,i.guild,page+1,query)),row=3)
            self.nav()
        async def edit(self,i,qid,expected):
            if not await self.interaction_check(i):return
            if ui.snapshot(qid)!=expected or ui.is_archived(qid):
                return await present(i,Manage(self.owner,i.guild,self.page,self.query),'This chore changed. Review the refreshed list.')
            q=chore(qid);modal=ui.EditChoreModal(self.owner,qid,q[2],expected)
            async def save(event):
                if not await self.interaction_check(event):return
                async with lock:
                    notice=ui.update_chore(qid,modal.name.value,modal.repeat_frequency(),modal.points.value,modal.notes.value,expected,modal.room.value)
                await present(event,Manage(self.owner,event.guild,self.page,self.query),notice)
            modal.on_submit=save
            await i.response.send_modal(modal)

    class Announcements(View):
        def __init__(self,owner,guild=None):
            super().__init__(owner)
            self.recovery_context={'screen':'announcements'}
            expected=ui.announcement_mode()
            self.embed=discord.Embed(title='Update announcements',description='Only ginaria controls these household announcements.',color=0x6B9B77)
            if owner!=OWNER:
                self.embed.description='Only ginaria can manage update announcements.'
                self.nav();return
            self.embed.description='Automatic update announcements: **'+('On' if expected[0] else 'Off')+'**. Off means a quiet start. Announce this update lets you post deliberately even while automatic announcements are off. One notice per release; uncertain sends are never repeated. No pings.'
            async def toggle(i):
                if not await self.interaction_check(i):return
                async with lock:message=ui.set_announcement_mode(i.user.id,not expected[0],expected)
                await present(i,Announcements(owner,i.guild),message)
            self.button('Turn automatic '+('off' if expected[0] else 'on'),toggle,row=0)
            async def announce(i):
                if not await self.interaction_check(i):return
                saved=db.execute('SELECT guild_id,channel_id,message_id FROM chore_board WHERE singleton=1').fetchone()
                if not saved or saved[2]=='pending':return await present(i,Announcements(owner,i.guild),'Set up the household chores channel first.')
                async def save(event):
                    if not await self.interaction_check(event):return
                    if db.execute('SELECT guild_id,channel_id,message_id FROM chore_board WHERE singleton=1').fetchone()!=saved:
                        return await present(event,Announcements(owner,event.guild),'The destination changed. Review it again; no notice was sent.')
                    await event.response.defer()
                    status=await ui.announce_update(manual_actor=event.user.id,expected_location=saved)
                    messages={'sent':'Update announced.','already_attempted':'This release was already announced or attempted; no duplicate was sent.',
                        'failed_uncertain':'Delivery is uncertain. Check the chores channel; it will not be repeated.',
                        'no_release':'Could not identify the installed release. No notice was sent.',
                        'changed':'Settings or destination changed. No notice was sent.',
                        'lookup_failed':'Could not open the chores channel. No notice was sent.',
                        'wrong_channel':'The channel did not match the household. No notice was sent.'}
                    await present(event,Announcements(owner,event.guild),messages.get(status,'No notice was sent.'))
                from chore_board import update_notice
                await present(i,Confirm(owner,'Announce this update?',f'Post as ChoreSprite in <#{saved[1]}>:\n\n'+update_notice()+'\n\nThe date and time are filled in when posted. No pings. An already attempted release will not post again.',save,lambda:Announcements(owner,i.guild)))
            self.button('Announce this update',announce,row=0,primary=True)
            self.nav()

        async def interaction_check(self,i):
            if self.owner!=OWNER or i.user.id!=OWNER:
                await i.response.send_message('Only ginaria can manage update announcements.',ephemeral=True)
                return False
            return await super().interaction_check(i)

    class Notifications(View):
        def __init__(self, owner):
            super().__init__(owner)
            row = db.execute('SELECT trade_dm FROM notification_preferences WHERE user_id=?',(str(owner),)).fetchone()
            enabled = bool(row and row[0])
            self.embed = discord.Embed(title='Trade alerts',description='**New trade proposal DMs: **'+('on' if enabled else 'off')+'. These are event alerts, not scheduled chore reminders. Turning them on allows private DMs for new trade proposals. Requests remain in Trades even when alerts are off. For due-chore messages and daily times, use Dashboard → Chore reminders. Owner feedback DMs are separate.',color=0x6B9B77)
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
            self.recovery_context={'screen':'inbox','page':page,'resolved':resolved}
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

    def household_people(viewer,guild=None,register=True):
        ids={str(viewer)}
        saved=db.execute('SELECT guild_id,channel_id,message_id FROM chore_board WHERE singleton=1').fetchone()
        getter=getattr(guild,'get_channel',None)
        channel=getter(int(saved[1])) if getter and saved and str(getattr(guild,'id',None))==saved[0] else None
        members=[]
        if channel is not None:
            for member in getattr(channel,'members',()):
                if getattr(member,'bot',True):continue
                permissions=channel.permissions_for(member)
                if permissions.view_channel and permissions.read_message_history:
                    members.append(str(member.id))
        if members:
            # Accounts are keyed by Discord ID; never replace existing scores or preferences.
            if register:
                with db:db.executemany('INSERT OR IGNORE INTO users(id) VALUES(?)',[(uid,) for uid in members])
            ids.update(members)
        for query in ('SELECT id FROM users','SELECT user_id FROM household_profiles','SELECT user_id FROM person_colors','SELECT user_id FROM household_identities','SELECT user_id FROM alternating_members',
                      'SELECT user_id FROM availability_defaults','SELECT user_id FROM availability_exceptions',
                      'SELECT user_id FROM claims','SELECT user_id FROM week_signups',
                      'SELECT user_id FROM repeating_signups','SELECT assigned_to FROM quests WHERE assigned_to IS NOT NULL'):
            ids.update(str(row[0]) for row in db.execute(query))
        return sorted((uid for uid in ids if uid.isdecimal()),key=int)

    class Trips(View):
        def __init__(self, owner, guild=None, people=None, page=0, roster_page=0):
            super().__init__(owner)
            people = people or []
            self.people = people
            self.recovery_context={'screen':'trips','people':list(people),'page':page,'roster_page':roster_page}
            self.name_ids=list(people)
            self.rebuild=lambda:Trips(owner,guild,people,page,roster_page)
            back = lambda: Trips(owner,guild,people,page,roster_page)
            self.people_details=[]
            self.embed = discord.Embed(title='Who’s home? · trips and traded days',description='Choose anyone. Mark home/away for particular dates, or change their Usual schedule. Date overrides win; afterward the usual schedule resumes. Eastern time.',color=0x6B9B77)
            if not people:
                now=timing.now();known=household_people(owner,guild)
                size=page_size(owner);page=min(max(page,0),max((len(known)-1)//size,0))
                self.recovery_context['page']=page
                home=sum(ui.attendance.at(uid,now) for uid in known)
                self.embed.description=f'{now:%a %b %d, %I:%M %p} Eastern · **{home} Home · {len(known)-home} Away**\nFrom saved schedules and date exceptions, not Discord online status. Choose Change or select people below to adjust their schedule.'
                self.name_ids=known
                known.sort(key=lambda uid:(clean(person(uid,guild),100).casefold(),int(uid)))
                self.list_page_size=size
                names=[clean(person(uid,guild),100) for uid in known]
                for uid in known[page*size:(page+1)*size]:
                    state='🟢 Home' if ui.attendance.at(uid,now) else '🔴 Away'
                    override=db.execute('SELECT state FROM availability_exceptions WHERE user_id=? AND active=1 AND start_date<=? AND end_date>=? ORDER BY id DESC LIMIT 1',(uid,now.date().isoformat(),now.date().isoformat())).fetchone()
                    reason=('Date override: '+override[0]) if override else ui.attendance.describe(uid)
                    self.embed.add_field(name=clean(person(uid,guild),100)+(f' · ID {uid}' if names.count(clean(person(uid,guild),100))>1 else ''),value=state+' · '+reason,inline=False)
                    self.people_details.append(uid)
                self.embed.set_footer(text=f'Page {page+1} of {max((len(known)-1)//size+1,1)} · {len(known)} known household account(s) · Missing someone? Use the person picker below.')
                self.paging_labels=('Previous','Next')
                if page:self.button('Previous',lambda i:present(i,Trips(owner,i.guild,page=page-1)),row=3)
                if (page+1)*size<len(known):self.button('Next',lambda i:present(i,Trips(owner,i.guild,page=page+1)),row=3)
            picker = discord.ui.UserSelect(placeholder='Choose one or more people',min_values=1,max_values=10,row=0)
            async def choose(i):
                members = picker.values
                if any(m.bot or getattr(getattr(m,'guild',None),'id',None) != i.guild_id for m in members):
                    return await i.response.send_message('Choose household people, not bots.',ephemeral=True)
                await present(i,Trips(owner,i.guild,[str(m.id) for m in members],roster_page=page if not people else roster_page))
            picker.callback = choose
            self.add_item(picker)
            if people:
                self.embed.add_field(name='Selected',value=', '.join(clean(person(uid,guild),100) for uid in people),inline=False)
                self.embed.add_field(name='Usual schedule',value='\n'.join(clean(person(uid,guild),60)+' · '+ui.attendance.describe(uid) for uid in people),inline=False)
                self.button('Usual schedule',lambda i:present(i,UsualSchedule(owner,people,i.guild,roster_page=roster_page)),row=1)
                today_expected=ui.attendance.today_snapshot(people,timing.now())
                for label,state in [('Home today','home'),('Away today','away')]:
                    async def quick_today(i,state=state):
                        if not await self.interaction_check(i):return
                        async with lock:notice=ui.attendance.mark_today(i.user.id,people,state,today_expected,timing.now())
                        await present(i,Trips(owner,i.guild,people,page,roster_page),notice)
                    self.button(label,quick_today,row=1)

                for label,state in [('Mark home','home'),('Mark away','away')]:
                    async def add(i,state=state): await i.response.send_modal(TripModal(owner,people,state,back))
                    self.button(label,add,row=1)
                shortcuts = discord.ui.Select(placeholder='Quick dates…',row=2,options=[discord.SelectOption(label=l,value=v) for l,v in [('Home today','home:today'),('Away today','today'),('Home tomorrow','home:tomorrow'),('Away tomorrow','tomorrow'),('Home this weekend','home:weekend'),('Away this weekend','weekend')]])
                async def quick(i):
                    day,value = timing.now().date(),shortcuts.values[0]
                    state,value=value.split(':',1) if ':' in value else ('away',value)
                    first = day+timedelta(days=1 if value == 'tomorrow' else 0 if value=='weekend' and day.weekday()==6 else (5-day.weekday())%7 if value == 'weekend' else 0)
                    last = first+timedelta(days=1 if value == 'weekend' and first.weekday()==5 else 0)
                    await i.response.send_modal(TripModal(owner,people,state,back,first.isoformat(),last.isoformat()))
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
                self.button('Weekly attendance',lambda i:present(i,adapt(ui.AttendanceView(owner,member_id=int(people[0]),member_name=person(people[0],guild)),owner,back)),row=4)
                if page: self.button('Previous',lambda i:present(i,Trips(owner,i.guild,people,page-1,roster_page)),row=4)
                if (page+1)*10 < len(records): self.button('Next',lambda i:present(i,Trips(owner,i.guild,people,page+1,roster_page)),row=4)
            self.nav((lambda:Trips(owner,guild,page=roster_page)) if people else None)

    class UsualSchedule(View):
        def __init__(self,owner,people,guild=None,mode=None,days=None,expected=None,roster_page=0):
            super().__init__(owner)
            self.people=list(people)
            expected=ui.attendance.defaults_snapshot(people) if expected is None else expected
            if days is None:
                profiles=[ui.attendance.profile(uid) for uid in people]
                import json
                days=json.loads(profiles[0][1]) if profiles and all(row[:2]==profiles[0][:2] for row in profiles) else []
            days=list(days)
            self.recovery_context={'screen':'usual_schedule','people':list(people),'mode':mode,'days':days,'roster_page':roster_page}
            self.name_ids=list(people)
            self.rebuild=lambda:UsualSchedule(owner,people,guild,mode,days,expected,roster_page)
            back=lambda:UsualSchedule(owner,people,guild,mode,days,expected,roster_page)
            self.embed=discord.Embed(title='Usual schedule',description='Set the default for the selected people. Date overrides still win. This does not move chores or give them to someone else.',color=0x6B9B77)
            self.embed.add_field(name='Current defaults',value='\n'.join(clean(person(uid,guild),70)+' · '+ui.attendance.describe(uid) for uid in people) or 'Choose people in Who’s home?',inline=False)
            modes=[('Use household default','household'),('Home every day','home'),('Away every day','away'),('Home on selected weekdays','weekly'),('Alternating: cycle A','same'),('Alternating: cycle B','opposite')]
            picker=discord.ui.Select(placeholder='Choose their usual schedule',row=0,options=[discord.SelectOption(label=label,value=value,default=value==mode) for label,value in modes])
            async def choose(i):await present(i,UsualSchedule(owner,people,i.guild,picker.values[0],days,expected,roster_page))
            picker.callback=choose;self.add_item(picker)
            if mode=='weekly':
                for day in range(7):
                    async def toggle(i,day=day):
                        if not await self.interaction_check(i):return
                        await present(i,UsualSchedule(owner,people,i.guild,mode,sorted(set(days)^{day}),expected,roster_page))
                    self.button(('✓ ' if day in days else '')+WEEKDAYS[day][:3].title(),toggle,row=1 if day<4 else 2,primary=day in days)
            if mode is not None:
                preview=ui.attendance.describe(people[0],mode,days) if people else 'Choose people first.'
                self.embed.add_field(name='New default for all selected people',value=preview,inline=False)
                async def save(i):
                    if not await self.interaction_check(i):return
                    async with lock:notice=ui.attendance.set_defaults(i.user.id,people,mode,days,expected,timing.now())
                    await present(i,Trips(owner,i.guild,people,roster_page=roster_page),notice)
                self.button('Save usual schedule',save,row=3,primary=True,disabled=mode=='weekly' and not days)
            self.nav(lambda:Trips(owner,guild,people,roster_page=roster_page))

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

    TOPICS = {'Start here': 'Open **Chores** and choose **Mine**, **Available**, **Everyone**, or **Needs attention**.\n\nChoose a chore from the list dropdown to read instructions, **Claim** it, or mark it **Done**. The work card keeps everyday controls visible; **Actions…** holds signups and occasional tools.\n\n**Other dates** keeps your selected view, with day arrows and **Week calendar** for the week/month overview. **Manage chores** edits the catalog. The **gear** opens your personal Settings.\n\nAfter Done, use **Back to chores** when ready; the small **Undo** reverses your latest eligible action.',
     'Pick up a chore': 'Open **Available** on the daily sheet. Choose a chore from the dropdown, read its instructions, then press **✋ Claim**. This takes just this occurrence. The card stays open with **✓ Done** ready when you finish.\n\nUse **Actions… → Sign up** for a longer signup or repeating days. Each option names its scope. Weekly signups end Sunday at 6 p.m. Eastern; finishing today does not release the rest of the week.',
     'Finish a chore': '1. Open **Chores → Mine → choose a chore**.\n'
                       '2. Read the chore’s instructions. If it has a **Checklist**, check off its steps '
                       'first.\n'
                       '3. Press **Done** when the work is finished.\n'
                       '\n'
                       'The points go to the Discord account that completes it. A repeating chore can become '
                       'due again; marking it Done completes only its current occurrence.\n'
                       '\n'
                       'After Done, the short confirmation stays until you choose **Back to chores**. **Undo** restores the work and removes its points. If something is stopping you, use **Need help** instead.',
     'Drop, reassign, or trade': 'Open the chore card, then **Actions…**.\n'
                                 '\n'
                                 '**Drop responsibility** gives up your responsibility without completing the '
                                 'work. **Reassign** gives it to another person. Check whether the '
                                 'confirmation covers one occurrence, a whole week, or an ongoing assignment.\n'
                                 '\n'
                                 '**Propose trade** offers an exchange with someone else. The other person '
                                 'must accept in **Plan & coordinate → Trades** before ownership changes. '
                                 'Declining or canceling leaves both chores as they were.\n'
                                 '\n'
                                 'Previously earned points and history stay saved.',
     'Choose or change a day': 'Open the chore card, then the action buttons.\n'
                               '\n'
                               'Choose **Change regular day** to set the weekday for a weekly chore in future '
                               'weeks too.\n'
                               '\n'
                               'Choose **Move this occurrence** to move only the current unfinished '
                               'occurrence. **Cancel occurrence move** removes that one-time change.\n'
                               '\n'
                               'Choosing a date in Calendar only shows its schedule. It does not move the '
                               'chore or sign you up.',
     'Schedules and missed chores': '**Keep overdue** leaves unfinished work due until someone completes it. '
                                    '**Skip if missed** lets an expired occurrence pass without awarding '
                                    'points; the next scheduled occurrence still happens. Choose this under '
                                    '**Edit chore → Missed chores**.\n'
                                    '\n'
                                    'All times are **Eastern**. Daily chores reset at midnight; twice-daily '
                                    'chores have morning and afternoon slots. Household weeks change Sunday at '
                                    '6 p.m.; monthly periods begin on the first.\n'
                                    '\n'
                                    'Separate **Daily AM** and **Daily PM** chores can have different owners. '
                                    'An unsplit twice-daily chore offers **Separate AM and PM sign-ups** in '
                                    'More options → Manage this chore.\n'
                                    '\n',
     'Use the calendar': 'Open **Plan & coordinate → Calendar** to see today. Use **<< Prev day**, **Today**, '
                         'or **Next day >>** to change the date. **< Prev / Next >** shows more chores '
                         'on the same date.\n'
                         '\n'
                         'Press **Details** beside a chore to read more. Past and future dates show a preview '
                         'before you open the current chore.\n'
                         '\n'
                         'Use **Week** or **Month** for an overview. **No fixed day** shows flexible weekly or '
                         'monthly chores that have not been given a weekday.\n'
                         '\n'
                         'The calendar is a schedule preview, not a complete record of finished work.',
     'Set reminders': '1. Open **My settings → Chore reminders**.\n'
                      '2. Use **Change times** to enter up to ten times, such as **09:00, 17:00**. Times are '
                      'Eastern and use the 24-hour clock.\n'
                      '3. Press **Turn on** to allow private reminder DMs. Use **Turn off** whenever you '
                      'want.\n'
                      '\n'
                      'These settings belong to your account, not to an individual chore. Reminders include '
                      'your due, unfinished responsibilities. Sprig stays quiet when you are away or have '
                      'nothing due.\n'
                      '\n'
                      'Trade DMs have a separate switch under **My settings → Trade alerts**.',
     'Report a problem': 'Open the chore card and press **Stuck / need help**. Choose **Stuck**, **Need '
                         'supplies**, or **Need help**, then explain what is stopping you.\n'
                         '\n'
                         'The note is shared with the household and appears under **Needs attention**. '
                         'Anyone can report a problem on an unfinished chore, even before it is due or claimed. Responsibility and points stay unchanged.\n'
                         '\n'
                         'When the obstacle is gone, mark the help status resolved. You still need to finish '
                         'the work and press **Done** separately. Older notes stay in status history.',
     'Suggest a chore change': 'Open the chore card, then **Give feedback**.\n'
                               '\n'
                               'Explain what should change: the instructions, timing, or number of points. You '
                               'can suggest an effort score for the household to discuss.\n'
                               '\n'
                               'Ginaria receives a private notification and can read it under **Owner tools → '
                               'Review inbox**. Suggestions do not change the chore automatically. If you '
                               'agree on a change, use **Edit chore** to apply it.\n'
                               '\n'
                               'Changing a chore’s point value affects future completions; previously earned '
                               'points stay as they are.',
     'Add, edit, or copy chores': 'Open **Manage chores** for the active chore list. Press **Edit** beside a chore for its prefilled form; saving keeps your search and page. **Search** finds names, instructions, or rooms. **Add chore**, **Archive chore**, and **Archived chores** are above the list. New '
                                  'chores default to **5 points**.\n'
                                  '\n'
                                  'To change an existing chore, open its card and choose **'
                                  'Edit chore**. The same menu has **Estimate / checklist** for steps and a '
                                  'time estimate, and **Duplicate chore** to make a fresh, unassigned copy '
                                  'with a new name.\n'
                                  '\n'
                                  'Archiving hides a chore while keeping its records. Use **Manage chores → '
                                  'Archived chores** to restore it.\n'
                                  '\n'
                                  'Everyone can manage chores; owner-only points and review controls are '
                                  'separate.',
     'Trips and traded days': 'Open **Plan & coordinate → Who’s home?**. Select the people affected, choose '
                              'home or away, and enter the first and last dates. Preview the dates before '
                              'confirming.\n'
                              '\n'
                              'These are full days in Eastern time. You can edit or cancel a saved exception. '
                              'The normal rotation resumes afterward.\n'
                              '\n'
                              'Existing chore responsibilities stay saved. Review coverage warnings and use '
                              'Reassign or Trade when someone else needs to cover the work; a trip does not '
                              'automatically transfer chores.',
     'Points and standings': 'Open **My settings → Points & standings** to see your total, streak, and '
                             'household rankings. Points belong to the account that completes the chore. They '
                             'do not currently redeem rewards.\n'
                             '\n'
                             '**Owner only:** Ginaria can use **Reset points** for one person or everyone, '
                             'choose whether to reset streaks, and confirm the change. History stays saved.\n'
                             '\n'
                             '**Reset history / Undo** can reverse a reset while the affected scores have no '
                             'newer activity. If something has changed, Sprig stops the undo so it cannot '
                             'overwrite newer work.',
     'Undo a mistake': 'Use the small **↶ Undo** at the bottom to reverse your most recent eligible Done or Skip. The adjacent description names the action. Completion Undo restores responsibility, points and streak state; Skip Undo restores its occurrence without points. Neither rewinds later changes. If unavailable or refused, refresh and inspect the current state.\n\nOlder records are in **Chore details → More options → Completion history**. The owner can inspect another person’s completion with the same safety checks. Back leaves a confirmation unsaved; it does not undo a saved action.',
     'Recover a screen': 'If buttons stop responding, press **Refresh**. It restores your page, filters, and '
                         'date after controls expire or Sprig restarts.\n'
                         '\n'
                         'If you cannot use that screen, open **/chores** again. **My settings → Continue '
                         'where I left off** returns to your saved place when one is available.\n'
                         '\n'
                         'Refreshing never repeats an expired action or confirmation. Review the current state '
                         'before trying a change again.\n'
                         '\n'
                         'Your controls are private, but changes to chores are shared with the household.'}
    HELP_ALIASES = {'Taking responsibility': 'Pick up a chore',
     'Dates and colors': 'Schedules and missed chores',
     'Schedules and missed work': 'Schedules and missed chores',
     'Feedback and points': 'Suggest a chore change',
     'History and mistakes': 'Undo a mistake',
     'Managing chores': 'Add, edit, or copy chores',
     'Planning and reminders': 'Set reminders',
     'Help statuses and copies': 'Report a problem',
     'Points and resets': 'Points and standings',
     'Notifications and recovery': 'Recover a screen'}

    TOPICS['Trips and traded days']='Open **Plan & coordinate → Who’s home?** to see scheduled Home/Away statuses now. Choose **Change** beside a person or select anyone below. **Mark home / Mark away** sets a single date or a trip; Quick dates includes home or away today, tomorrow, and the weekend. Preview the dates before saving.\n\nChoose **Usual schedule** to change a person’s normal arrangement: home daily, away daily, selected weekdays, or alternating weeks. Review & save shows who changes. Use household default restores Kas/Zel’s alternating weeks and everyone else’s home-every-day default.\n\nA dated override always wins. When it ends, the person’s usual schedule resumes. Kas/Zel’s alternating handoff stays Sunday at 6 p.m. Changing attendance keeps chores assigned; review coverage or use Reassign when needed.'

    TOPICS['Workload & pace']='Earned averages use recorded completions through yesterday, excluding undone work. Resets of the points balance do not erase this work. Days before the first recorded completion are unavailable, not invented zeros; today is shown separately.\n\nThe plan covers the next 7, 28, or 90 full days. It uses current assignments and dated week signups; unknown owners stay Unclaimed. Daily/fixed-day chores count scheduled occurrences. Flexible weekly/monthly points are prorated across their period, without choosing a weekday. Moved work counts once before its normal schedule resumes. Undated one-time work is separate. This estimates responsibility, assuming recurring work gets finished on time; it is not guaranteed future earnings.\n\nDaily rates use calendar days; weekly means 7 days and monthly means 30 days. Per home-day uses the saved rotation and exceptions, with Sunday split at 6 p.m. Old attendance edits can change that historical comparison. Away occurrences are excluded from their plan. Saved responsibilities resume when home; missed away occurrences do not accumulate. Points measure the household’s chosen effort values, not hours worked.'

    TOPICS['Repeating days']='Open a daily chore by its name button, then Sign-up schedule. Saved slots are preselected. Toggle the exact weekday/AM/PM buttons you want, then Save repeating days once.\n\nRepeats apply only when home, using usual attendance and exceptions. Your away slots pause; the signup returns when you are home. Opposite home weeks may share a slot. If attendance changes create an overlap, it stays unclaimed until covered or corrected. Unselect slots and Save to release them. Clear selection and Save releases all your recurring slots; other people stay unchanged. Skip, occurrence Reassign, and accepted Trade preserve the repeating schedule. Whole-week/ongoing assignments cannot override repeating days. Points go to whoever completes each occurrence.'

    TOPICS['Future occurrences']='A chore name always opens Chore details. In This week, Next week, or Upcoming, use Choose date beside the name, or Choose occurrence on the card, to select an exact date and AM/PM slot. Or open Calendar → a day → a chore.\n\n**Claim just this time** reserves only that occurrence, when you are home. **Skip just this time** takes effect immediately, awards no points, and keeps later repeats and saved signups.\n\n**Undo skip for this occurrence** is at the bottom until that occurrence ends, if its record remains unchanged. Release a dated claim with **Drop this dated claim**. Flexible weekly/monthly chores need a regular day before they have dated occurrences. Future work cannot be completed early.'
    TOPICS['Change list length']='Open **Settings → List length** and choose **1–10 items per page**. \n\nNew accounts default to **8** on the daily sheet; your existing preference is preserved. Legacy dense button lists may show fewer rows to stay inside Discord limits. This changes display only, never chores or points.'

    TOPICS['Schedules and missed chores'] += DAY_LEGEND+'\nWeekly and monthly symbols mean no fixed weekday until one is chosen.'

    TOPICS['Trade alerts']='Trade alerts sends a private DM when someone proposes a chore trade to you. It has an on/off switch, not a daily schedule. Requests remain in Trades with alerts off.\n\nFor scheduled due-chore DMs, open Dashboard → Chore reminders. Feedback DMs to the owner are separate.'

    PAGE_TOPICS = {
        'Dashboard':'Start here', 'Browse':'Pick up a chore',
        'Attention':'Report a problem', 'Card':'Pick up a chore',
        'ClaimChoices':'Pick up a chore', 'Repeating':'Repeating days',
        'OccurrenceDates':'Future occurrences', 'FutureSlots':'Future occurrences',
        'FutureOccurrence':'Future occurrences', 'Filters':'Pick up a chore',
        'Groups':'Pick up a chore', 'ButtonChoices':'Start here',
        'Points':'Points and standings', 'ResetPoints':'Points and standings',
        'ResetHistory':'Points and standings', 'History':'Undo a mistake',
        'Confirm':'Undo a mistake', 'Manage':'Add, edit, or copy chores',
        'Announcements':'Start here', 'Notifications':'Trade alerts',
        'Inbox':'Suggest a chore change', 'ReviewInbox':'Suggest a chore change',
        'Trips':'Trips and traded days', 'UsualSchedule':'Trips and traded days',
        'ExceptionCard':'Trips and traded days', 'HouseholdSetup':'Trips and traded days',
        'AttendanceView':'Trips and traded days', 'Calendar':'Use the calendar',
        'Day':'Use the calendar', 'Checklist':'Finish a chore',
        'Reminders':'Set reminders', 'HelpStatus':'Report a problem',
        'HelpHistory':'Report a problem', 'NeedsHelp':'Report a problem',
        'Report':'Workload & pace', 'PersonColor':'Your color', 'ListLength':'Change list length',
        'ReassignView':'Drop, reassign, or trade', 'DropChoreView':'Drop, reassign, or trade',
        'TradeOfferView':'Drop, reassign, or trade', 'TradeInboxView':'Drop, reassign, or trade',
        'ChooseDayView':'Choose or change a day', 'MissedChoreView':'Schedules and missed chores',
        'FeedbackView':'Suggest a chore change', 'EditChoreView':'Add, edit, or copy chores',
        'AddChoreMenu':'Add, edit, or copy chores', 'RemoveChoreView':'Add, edit, or copy chores',
        'WeekdayMenu':'Schedules and missed chores', 'RepeatMenu':'Schedules and missed chores',
        'PersonalView':'Pick up a chore', 'ResponsibilityView':'Pick up a chore',
        'WeeklyView':'Pick up a chore', 'Guide':'Start here', 'PageHelp':'Start here',
    }

    def screen_name(source):
        title=getattr(getattr(source,'embed',None),'title',None)
        if not title and type(source).__name__ in ('View','ReturnView'):return 'Chore actions'
        prefixes={'Card':'Chore details','FutureSlots':'Choose a shift','FutureOccurrence':'Dated occurrence','Day':'Calendar day','Confirm':'Confirm change','ButtonChoices':'Choose an option'}
        prefix=prefixes.get(type(source).__name__)
        if title:return (prefix+' · ' if prefix else '')+str(title)
        import re
        return re.sub(r'(?<!^)(?=[A-Z])',' ',type(source).__name__).replace(' View','').strip() or 'Chores'

    def page_help_button(source):
        button=discord.ui.Button(label='?',style=discord.ButtonStyle.secondary)
        button._sprig_navigation=True
        async def show(i):
            if not await source.interaction_check(i):return
            if isinstance(source,PageHelp):return await present(i,Guide(source.owner))
            await present(i,PageHelp(source.owner,source))
        button.callback=show
        return button

    class PageHelp(View):
        def __init__(self,owner,source=None,*,name=None,topic=None,parent=None,guild=None,instructions=None):
            super().__init__(owner)
            name=name or screen_name(source)
            kind=type(source).__name__ if source is not None else ''
            topic=topic or PAGE_TOPICS.get(kind,'Start here')
            if kind=='Browse' and source.state['area']=='mine':topic='Finish a chore'
            if topic not in TOPICS:topic='Start here'
            context=parent if parent is not None else recovery.bookmark(source)
            self.recovery_context={'screen':'page_help','name':name,'topic':topic,'parent':context}
            saved_instructions=instructions
            instructions=TOPICS[topic]
            if source is not None and kind not in PAGE_TOPICS:
                description=getattr(getattr(source,'embed',None),'description',None) or ''
                actions=[getattr(item,'label','') for item in source.children if isinstance(item,discord.ui.Button) and item.label not in ('Back','Dashboard')]
                instructions=(description+'\n\n' if description else '')+'Use '+(', '.join('**'+label+'**' for label in actions) if actions else 'the choices on this screen')+' to continue. Back returns without confirming an action; Dashboard opens the main menu.'
            if kind=='Card':instructions='Read this chore’s instructions. **Claim** takes this occurrence; after claiming, **Done** completes it. **Skip** skips only this occurrence without points. **Need help** records a problem; required checklist steps must be finished before Done.\n\nUse **Actions…** for signups, reassigning, trades, editing, dates and history. Each choice includes its scope or description. **Back to chores** returns to the sheet and preserves its view. One small **↶ Undo** names your latest reversible Done or Skip at the bottom.'
            elif kind=='Chores':instructions=TOPICS['Start here']+'\n\n**Needs attention** combines Overdue, Needs someone and Blocked work today. On other dates it shows projected unclaimed work; current help and overdue labels are not carried into future occurrences.'
            elif kind=='Attention':instructions='This list combines **Overdue**, **Needs someone**, and **Blocked** work. A chore appears once even when several labels apply. Due today does not automatically mean overdue.\n\nPress **Details** beside a chore to inspect or act. Back returns to this list page; Refresh reads the latest state.'
            elif kind=='Confirm':instructions='Read the proposed change above before confirming. Back leaves it unsaved. Opening Help never confirms or repeats the action.'
            elif kind=='ButtonChoices':instructions='Press a choice to select it. If several choices are allowed, toggle them and press Apply. Back returns without applying these choices.'
            elif kind=='Announcements':instructions='Owner only: turn automatic update announcements on or off, or preview Announce this update before sending it. Restarting does not need to announce anything.'
            elif kind in ('Guide','PageHelp'):instructions='Choose a help topic to read short instructions. The ? button on a chore screen opens its own help. Back returns to the screen that opened this help.'
            instructions=saved_instructions or instructions
            self.recovery_context['instructions']=instructions
            self.embed=discord.Embed(title='Help · '+name,description=instructions,color=0x6B9B77)
            self.button('All help topics',lambda i:present(i,Guide(owner)),row=1)
            self.nav((lambda:source) if source is not None else lambda:recovery.restore(owner,context,guild))

    class Guide(View):
        def __init__(self,owner,topic='Start here'):
            super().__init__(owner)
            topic=HELP_ALIASES.get(topic,topic)
            if topic not in TOPICS:topic='Start here'
            self.recovery_context={'screen':'guide','topic':topic}
            self.embed = discord.Embed(title='Help · '+topic,description=TOPICS[topic],color=0x6B9B77)
            picker = discord.ui.Select(placeholder='What would you like to do?',options=[discord.SelectOption(label=k,value=k,default=k==topic) for k in TOPICS])
            async def choose(i): await present(i,Guide(owner,picker.values[0]))
            picker.callback = choose
            self.add_item(picker)
            self.nav()

    TOPICS['Your color']='Open **Settings → Your color** and choose a marker.\n\nChoosing saves immediately. **No marker** removes it. Everyone sees it on refreshed workspace screens; responsibility and points stay unchanged.'

    result = SimpleNamespace(People=People,PersonProfile=PersonProfile,save_profile=save_profile,ProfileModal=ProfileModal,HouseholdColors=HouseholdColors,ChoreMore=ChoreMore,PersonColor=PersonColor,color_key=color_key,sheet_size=sheet_size,Chores=Chores,PersonalSettings=PersonalSettings,browse_page_size=browse_page_size,PageHelp=PageHelp,screen_name=screen_name,PAGE_TOPICS=PAGE_TOPICS,ButtonChoices=ButtonChoices,ClaimChoices=ClaimChoices,Repeating=Repeating,OccurrenceDates=OccurrenceDates,FutureOccurrence=FutureOccurrence,FutureSlots=FutureSlots,skip_occurrence=skip_occurrence,undo_skip=undo_skip,undoable_skip=undoable_skip,UsualSchedule=UsualSchedule,page_size=page_size,ListLength=ListLength,Announcements=Announcements,Confirm=Confirm,clean=clean,person=person,undo_points_reset=undo_points_reset,ResetHistory=ResetHistory,ResetPoints=ResetPoints,split_daily_shifts=split_daily_shifts,Points=Points,LayoutPanel=LayoutPanel,render=render,payload=payload,Dashboard=Dashboard,Attention=Attention,attention_rows=attention_rows,Browse=Browse,Card=Card,Inbox=Inbox,Trips=Trips,Guide=Guide,Manage=Manage,History=History,Notifications=Notifications,MoveModal=MoveModal,TripModal=TripModal,View=View,adapt=adapt,present=present,save_trip=save_trip,parse_date=parse_date,ownership=ownership,notify_trade=notify_trade,memory=memory)

    from chore_recovery import install as install_recovery
    recovery = install_recovery(ns, ui, result)
    result.recovery = recovery
    return result
