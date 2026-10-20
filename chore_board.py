"""Button interface for Sprig; existing commands remain the source of mutations."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import discord
from discord.ext import commands
from chore_timing import ChoreTiming, WEEKDAYS, WEEKLY_FREQUENCIES, DAY_COLORS, DAY_LEGEND, day_badge

PAGE_SIZE = 20


def install(namespace):
    api = SimpleNamespace(**namespace)
    bot, db = api.bot, api.db
    timing = ChoreTiming(namespace, db)
    db.execute("""CREATE TABLE IF NOT EXISTS chore_board (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, message_id TEXT NOT NULL
    )""")
    db.commit()
    lock = asyncio.Lock()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS week_signups (
            quest_id INTEGER NOT NULL, week_start TEXT NOT NULL, user_id TEXT NOT NULL,
            PRIMARY KEY (quest_id, week_start));
        CREATE TABLE IF NOT EXISTS alternating_members (
            user_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS archived_chores (
            quest_id INTEGER PRIMARY KEY, removed_by TEXT NOT NULL, removed_at TEXT NOT NULL);
    """)
    db.commit()

    def week_start(offset=0):
        now = namespace['now_local']().astimezone(api.QUEST_TIMEZONE)
        start = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=18, minute=0, second=0, microsecond=0)
        if now < start:
            start -= timedelta(days=7)
        return start + timedelta(weeks=offset)

    def week_key(offset=0):
        return week_start(offset).date().isoformat()

    def available(user_id, offset=0):
        alternating = db.execute("SELECT 1 FROM alternating_members WHERE user_id = ?", (str(user_id),)).fetchone()
        if not alternating:
            return True
        # Sunday October 18, 2026 begins the away week supplied by Katherine.
        anchor = datetime(2026, 10, 18).date()
        return ((week_start(offset).date() - anchor).days // 7) % 2 == 1

    def weekly_owner(quest_id, offset=0):
        row = db.execute("SELECT user_id FROM week_signups WHERE quest_id = ? AND week_start = ?", (quest_id, week_key(offset))).fetchone()
        return row[0] if row else None

    original_reset = api.reset_due_quests

    def reset_with_availability():
        result = original_reset()
        # A claim made during a home week must not strand a chore in an away week.
        away = [r[0] for r in db.execute("SELECT user_id FROM alternating_members").fetchall() if not available(r[0])]
        with db:
            db.executemany("DELETE FROM claims WHERE user_id = ?", [(uid,) for uid in away])
            # A new weekly owner takes precedence over a previous occurrence claim.
            db.execute("""DELETE FROM claims WHERE EXISTS (
                SELECT 1 FROM week_signups w WHERE w.quest_id = claims.quest_id
                AND w.week_start = ? AND w.user_id != claims.user_id)""", (week_key(),))
        return result

    api.reset_due_quests = reset_with_availability
    namespace['reset_due_quests'] = reset_with_availability

    def weekly_rows(user_id, offset):
        api.reset_due_quests()
        result = db.execute("""SELECT q.id, q.name, q.frequency, q.points,
            q.assigned_to, c.user_id, q.last_completed, q.notes
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id
            WHERE q.assigned_to IS NULL
            ORDER BY q.name COLLATE NOCASE, q.id""").fetchall()
        return [r for r in result if r[2] in WEEKLY_FREQUENCIES and (timing.in_week(r[2],week_start(offset)) or (offset == 0 and timing.ready(r[0]))) and not is_archived(r[0]) and weekly_owner(r[0], offset) in (None, str(user_id))
                and (offset != 0 or not r[5] or r[5] == str(user_id))]

    def signup(user_id, quest_id, key):
        offsets = {week_key(0): 0, week_key(1): 1}
        offset = offsets.get(key)
        if offset is None:
            return "The week changed. Reopen Weekly sign-ups."
        if not available(user_id, offset):
            return "You're away that week. Choose a week when you're home."
        row = db.execute("SELECT frequency, assigned_to FROM quests WHERE id = ?", (quest_id,)).fetchone()
        if not row or is_archived(quest_id) or row[0] not in WEEKLY_FREQUENCIES or row[1]:
            return "This chore is no longer available for a weekly sign-up."
        if not timing.in_week(row[0],week_start(offset)) and not (offset == 0 and timing.ready(quest_id)):
            return 'This chore is not scheduled for that week.'
        claim = db.execute("SELECT user_id FROM claims WHERE quest_id = ?", (quest_id,)).fetchone()
        if offset == 0 and claim and claim[0] != str(user_id):
            return "Someone already claimed this occurrence. Choose another chore."
        with db:
            db.execute("INSERT OR IGNORE INTO week_signups VALUES (?, ?, ?)", (quest_id, key, str(user_id)))
            if offset == 0 and weekly_owner(quest_id, offset) == str(user_id):
                db.execute("DELETE FROM claims WHERE quest_id = ? AND user_id = ?", (quest_id, str(user_id)))
        if weekly_owner(quest_id, offset) != str(user_id):
            return "Someone already signed up for this chore that week."
        return "You're signed up for the week. Daily chores stay yours after each Done until Sunday at 6 p.m."

    def location():
        return db.execute("SELECT guild_id, channel_id, message_id FROM chore_board WHERE singleton = 1").fetchone()

    def rows(user_id, mode):
        api.reset_due_quests()
        result = db.execute("""SELECT q.id, q.name, q.frequency, q.points,
            q.assigned_to, c.user_id, q.last_completed, q.notes
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id
            WHERE q.completed = 0 ORDER BY q.name COLLATE NOCASE, q.id""").fetchall()
        result = [r for r in result if not is_archived(r[0]) and timing.ready(r[0])]
        if not available(user_id):
            return []
        if mode == "mine":
            return [r for r in result if str(r[4] or weekly_owner(r[0]) or r[5]) == str(user_id)]
        return [r for r in result if not r[4] and not r[5] and not weekly_owner(r[0])]

    def snapshot(quest_id):
        row = db.execute("""SELECT q.completed, q.last_completed, q.assigned_to, c.user_id
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id WHERE q.id = ?""", (quest_id,)).fetchone()
        details=db.execute('SELECT name,frequency,points,notes,category,difficulty FROM quests WHERE id=?',(quest_id,)).fetchone()
        return (row, week_key(), weekly_owner(quest_id), is_archived(quest_id), details, timing.state(quest_id))

    def allowed(interaction):
        saved = location()
        if not saved or saved[2]=='pending' or str(interaction.guild_id)!=saved[0]:
            return False
        if str(interaction.channel_id)==saved[1]:
            return True
        # Fresh private panels can be opened elsewhere in the household server,
        # but never bypass permission to the canonical chores channel.
        getter=getattr(interaction.guild,'get_channel',None)
        channel=getter(int(saved[1])) if getter else None
        if channel is None:
            return False
        permissions=channel.permissions_for(interaction.user)
        return permissions.view_channel and permissions.read_message_history

    class SafeView(discord.ui.View):
        async def on_error(self, interaction, error, item):
            # Do not repeat an action after a response failure: it may have saved.
            message = "I couldn't finish updating this view. Open My chores again to check what saved before trying again."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            import logging
            logging.getLogger(__name__).exception("Chore board interaction failed", exc_info=error)

    class Context:
        def __init__(self, interaction):
            self.author, self.guild = interaction.user, interaction.guild
            self.messages = []

        async def send(self, content, **kwargs):
            # Buffer command feedback: no network await during its DB mutation.
            self.messages.append(content)

    class PersonalView(SafeView):
        def __init__(self, owner, mode="open", page=0, selected=None, notice=""):
            super().__init__(timeout=600)
            self.owner, self.mode = owner, mode
            self.entries = rows(owner, mode)
            self.page = min(max(page, 0), max((len(self.entries) - 1) // PAGE_SIZE, 0))
            chunk = self.entries[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]
            self.selected = next((r for r in chunk if r[0] == selected), None)
            self.expected = snapshot(selected) if self.selected else None
            title = "Open chores" if mode == "open" else "My chores"
            away_message = "You're away this week. Use Weekly sign-ups on the main board to reserve your next home week's chores."
            self.embed = discord.Embed(title=f"🌱 {title}", description=notice or ("Choose a chore below. No commands needed." if available(owner) else away_message))
            if self.selected:
                r = self.selected
                responsibility = " · Yours through Sunday at 6 p.m." if weekly_owner(r[0]) == str(owner) else ""
                self.embed.add_field(name=r[1][:256], value=f"{timing.label(r[2])} · {r[3]} points{responsibility}\n{(r[7] or '')[:650]}", inline=False)
            elif not chunk:
                self.embed.add_field(name="All clear", value="No open chores right now." if mode == "open" else "Nothing assigned or claimed. Tap Open chores to sign up.")
            else:
                self.embed.add_field(name="Available here", value="\n".join(f"• {discord.utils.escape_markdown(r[1])[:44]}" for r in chunk)[:1024], inline=False)
            self.embed.set_footer(text=f"Page {self.page + 1} of {max((len(self.entries) - 1) // PAGE_SIZE + 1, 1)} · Private view · Reopen from the main board after 10 minutes or a bot restart.")
            if chunk:
                select = discord.ui.Select(placeholder="Choose a chore…", options=[discord.SelectOption(label=r[1][:100], value=str(r[0]), description=f"{timing.label(r[2])} · {r[3]} points · #{r[0]}"[:100], default=bool(self.selected and r[0] == self.selected[0])) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            self.add_button("Open chores", lambda i: self.show(i, mode="open", page=0))
            self.add_button("My chores", lambda i: self.show(i, mode="mine", page=0))
            if self.selected:
                if mode == "open":
                    self.add_button("Claim", lambda i: self.act(i, "claim"), discord.ButtonStyle.success)
                else:
                    self.add_button("Done", lambda i: self.act(i, "done"), discord.ButtonStyle.success)
                    if not self.selected[4] and not weekly_owner(self.selected[0]):
                        self.add_button("Release", lambda i: self.act(i, "unclaim"))
            if self.page:
                self.add_button("Previous", lambda i: self.show(i, page=self.page - 1), row=2)
            if (self.page + 1) * PAGE_SIZE < len(self.entries):
                self.add_button("Next", lambda i: self.show(i, page=self.page + 1), row=2)
            self.add_button("Refresh", lambda i: self.show(i), row=2)

        def add_button(self, label, callback, style=discord.ButtonStyle.secondary, row=1):
            button = discord.ui.Button(label=label, style=style, row=row)
            button.callback = callback
            self.add_item(button)

        async def interaction_check(self, interaction):
            if interaction.user.id != self.owner or not allowed(interaction):
                await interaction.response.send_message("Open your own chore list from the main board.", ephemeral=True)
                return False
            return True

        async def show(self, interaction, mode=None, page=None, selected=None, notice=""):
            view = PersonalView(self.owner, mode or self.mode, self.page if page is None else page, selected, notice)
            await interaction.response.edit_message(embed=view.embed, view=view)

        async def act(self, interaction, action):
            await interaction.response.defer()
            async with lock:
                api.reset_due_quests()
                if not available(self.owner):
                    notice = "You're away this week. Open Weekly sign-ups to plan your next home week."
                elif snapshot(self.selected[0]) != self.expected:
                    notice = "This chore changed since you opened it. The list has been refreshed."
                else:
                    context = Context(interaction)
                    await bot.get_command(action).callback(context, self.selected[0])
                    notice = "\n".join(context.messages)
                view = PersonalView(self.owner, "mine" if action == "claim" else self.mode, notice=notice)
            await interaction.edit_original_response(embed=view.embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    def responsibility_rows(offset=0):
        api.reset_due_quests()
        start,end=week_start(offset),week_start(offset+1)
        result=[]
        for qid,name,frequency,assigned,claim,completed,reset in db.execute("SELECT q.id,q.name,q.frequency,q.assigned_to,c.user_id,q.completed,q.reset_after FROM quests q LEFT JOIN claims c ON c.quest_id=q.id"):
            if is_archived(qid):
                continue
            if frequency in WEEKLY_FREQUENCIES:
                if not timing.in_week(frequency,start) and not (offset==0 and not completed and timing.ready(qid)):
                    continue
            elif completed:
                # Monthly chores reappear in the week containing their reset.
                if not reset or datetime.fromisoformat(reset)>=end or (offset and datetime.fromisoformat(reset)<start):
                    continue
            owner=assigned or weekly_owner(qid,offset) or (claim if offset==0 else None)
            kind='Assigned' if assigned else ('Weekly sign-up' if weekly_owner(qid,offset) else ('Single claim' if claim and offset==0 else 'Nobody signed up'))
            status=('Done for this occurrence' if completed else ('Due now' if timing.ready(qid) else 'Upcoming')) if offset==0 else 'Scheduled / outstanding next week'
            result.append((str(owner) if owner else None,qid,name,frequency,kind,status))
        return result

    async def responsibility_view(owner,guild,offset=0,page=0):
        names={}
        context=SimpleNamespace(guild=guild)
        for uid in {r[0] for r in responsibility_rows(offset) if r[0]}:
            names[uid]=await namespace['get_member_name'](context,uid)
        return ResponsibilityView(owner,guild,offset,page,names)

    class ResponsibilityView(SafeView):
        def __init__(self,owner,guild,offset=0,page=0,names=None):
            super().__init__(timeout=600)
            self.owner,self.guild,self.offset=owner,guild,offset
            def display(uid):
                member=guild.get_member(int(uid)) if uid else None
                return discord.utils.escape_markdown((names or {}).get(uid) or (member.display_name if member else (f'Account {uid}' if uid else 'Nobody signed up')))[:100]
            entries=sorted(responsibility_rows(offset),key=lambda r:(r[0] is None,display(r[0]).casefold(),r[2].casefold(),r[1]))
            self.entries=entries
            self.page=min(max(page,0),max((len(entries)-1)//12,0))
            start,end=week_start(offset),week_start(offset+1)
            missing=sum(r[0] is None for r in entries)
            self.embed=discord.Embed(title="Who’s doing what?",description=f"**{'This week' if offset==0 else 'Next week'} · {start:%b %d} → {end:%b %d}**\n{len(entries)-missing} assigned · **{missing} need someone**\nWeeks change Sunday, 6 p.m. Eastern. Includes still-open monthly/one-time chores.\n{DAY_LEGEND}",color=0x6B9B77)
            def schedule(frequency):
                if frequency in WEEKDAYS:
                    return day_badge(frequency)
                if frequency.startswith('days:'):
                    return ' / '.join(day_badge(day) for day in frequency[5:].split(','))
                if ':' in frequency:
                    phase,day=frequency.split(':')
                    return f'Every other {day_badge(day)} ({phase})'
                return {'twice-daily':'AM + PM','daily':'Daily','weekly':'Weekly','monthly':'Monthly','one-time':'One time'}.get(frequency,frequency)
            heading=None
            lines=[]
            def flush():
                if lines:
                    self.embed.add_field(name=heading,value='\n'.join(lines),inline=False)
            for uid,qid,name,frequency,kind,status in entries[self.page*12:(self.page+1)*12]:
                title=(display(uid)+(' · away' if not available(uid,offset) else '')) if uid else 'Needs someone'
                tags=[schedule(frequency)]
                if kind=='Single claim':
                    tags.append('one occurrence')
                elif kind=='Assigned':
                    tags.append('ongoing')
                if status=='Done for this occurrence':
                    tags.append('done this slot' if frequency=='twice-daily' else 'done')
                line=f"• **{discord.utils.escape_markdown(name)[:150]}** — {' · '.join(tags)}"
                if title!=heading or len('\n'.join(lines+[line]))>950:
                    flush()
                    heading=title
                    lines=[]
                lines.append(line)
            flush()
            if not entries:
                self.embed.add_field(name='All clear',value='No chores scheduled or outstanding for this week.',inline=False)
            self.embed.set_footer(text=f'Page {self.page+1} of {max((len(entries)-1)//12+1,1)} · Single claims apply only to this week · Refresh for changes')
            self.button('This week',lambda i:self.show(i,offset=0,page=0))
            self.button('Next week',lambda i:self.show(i,offset=1,page=0))
            self.button('Refresh',lambda i:self.show(i))
            if self.page:
                self.button('Previous',lambda i:self.show(i,page=self.page-1))
            if (self.page+1)*12<len(entries):
                self.button('Next page',lambda i:self.show(i,page=self.page+1))

        def button(self,label,callback):
            item=discord.ui.Button(label=label)
            item.callback=callback
            self.add_item(item)

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own Who’s doing what? view from the household panel.',ephemeral=True)
                return False
            return True

        async def show(self,interaction,offset=None,page=None):
            await interaction.response.defer()
            view=await responsibility_view(self.owner,interaction.guild,self.offset if offset is None else offset,self.page if page is None else page)
            await interaction.edit_original_response(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())

    class WeeklyView(SafeView):
        def __init__(self, owner, offset=0, page=0, selected=None, notice=""):
            super().__init__(timeout=600)
            self.owner, self.key = owner, week_key(offset)
            self.offset = offset
            entries = weekly_rows(owner, offset)
            self.page = min(max(page, 0), max((len(entries) - 1) // PAGE_SIZE, 0))
            chunk = entries[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]
            self.selected = next((r for r in chunk if r[0] == selected), None)
            start = week_start(offset)
            end = start + timedelta(weeks=1)
            status = "Home this week" if available(owner, offset) else "Away this week — choose your next home week"
            self.embed = discord.Embed(title="🌱 Weekly sign-ups", description=f"{start:%b %d} at 6 p.m. → {end:%b %d} at 6 p.m.\n{status}\n{notice or 'Reserve a recurring chore for this week or next week.'}\n{DAY_LEGEND}")
            if not db.execute("SELECT 1 FROM alternating_members LIMIT 1").fetchone():
                self.embed.add_field(name="Household setup needed", value="An administrator still needs to select Kas and Z in Household setup so their away weeks can be enforced.", inline=False)
            if self.selected:
                r = self.selected
                state = "You're signed up" if weekly_owner(r[0], offset) == str(owner) else "Open for the week"
                self.embed.add_field(name=r[1][:256], value=f"{timing.label(r[2])} · {state}\n{(r[7] or '')[:700]}", inline=False)
            elif not chunk:
                self.embed.add_field(name="No chores available", value="Preassigned and one-time chores aren't part of weekly sign-ups.")
            if chunk:
                select = discord.ui.Select(placeholder="Choose a chore for the week…", options=[discord.SelectOption(label=r[1][:100], value=str(r[0]), description=("Your weekly responsibility" if weekly_owner(r[0], offset) == str(owner) else "Open for the week"), default=bool(self.selected and r[0] == self.selected[0])) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            self.button("This week", lambda i: self.show(i, offset=0, page=0))
            self.button("Next week", lambda i: self.show(i, offset=1, page=0))
            if self.selected:
                mine = weekly_owner(self.selected[0], offset) == str(owner)
                if mine or available(owner, offset):
                    self.button("Release week" if mine else "Sign up for week", lambda i: self.act(i, mine), discord.ButtonStyle.secondary if mine else discord.ButtonStyle.success)
            if self.page:
                self.button("Previous", lambda i: self.show(i, page=self.page - 1), row=2)
            if (self.page + 1) * PAGE_SIZE < len(entries):
                self.button("Next", lambda i: self.show(i, page=self.page + 1), row=2)
            self.button("Refresh", lambda i: self.show(i), row=2)
            self.embed.set_footer(text=f"Page {self.page + 1} · Sunday 6 p.m. handoff · Daily completion does not release your week · Reopen from the main board after 10 minutes or restart.")

        def button(self, label, callback, style=discord.ButtonStyle.secondary, row=1):
            button = discord.ui.Button(label=label, style=style, row=row)
            button.callback = callback
            self.add_item(button)

        async def interaction_check(self, interaction):
            if interaction.user.id != self.owner or not allowed(interaction):
                await interaction.response.send_message("Open your own Weekly sign-ups from the main board.", ephemeral=True)
                return False
            return True

        async def show(self, interaction, offset=None, page=None, selected=None):
            view = WeeklyView(self.owner, self.offset if offset is None else offset, self.page if page is None else page, selected)
            await interaction.response.edit_message(embed=view.embed, view=view)

        async def act(self, interaction, release=False):
            await interaction.response.defer()
            async with lock:
                # Do not silently apply a click to a different week after Sunday.
                if week_key(self.offset) != self.key:
                    notice = "The week changed. Review the new dates before signing up."
                elif release:
                    with db:
                        db.execute("DELETE FROM week_signups WHERE quest_id = ? AND week_start = ? AND user_id = ?", (self.selected[0], self.key, str(self.owner)))
                    notice = "Weekly sign-up released. Completed work and points are unchanged."
                else:
                    notice = signup(self.owner, self.selected[0], self.key)
                view = WeeklyView(self.owner, self.offset, notice=notice)
            await interaction.edit_original_response(embed=view.embed, view=view)

    def reassign_snapshot(qid):
        return snapshot(qid),week_key(1),weekly_owner(qid,1)

    def reassign(qid,target,scope,expected):
        api.reset_due_quests()
        if reassign_snapshot(qid)!=expected or is_archived(qid):
            return 'This chore or week changed. Reopen Reassign and review it again.'
        row=db.execute('SELECT frequency,assigned_to,completed FROM quests WHERE id=?',(qid,)).fetchone()
        if not row or scope not in ('occurrence','week0','week1','assignment'):
            return 'Choose a valid chore and assignment scope.'
        offset=1 if scope=='week1' else 0
        if not available(target,offset):
            return 'That person is away that week. Choose someone who is home.'
        if scope.startswith('week'):
            if row[1]:
                return 'This chore has an ongoing assignment. Choose Ongoing assignment instead.'
            if row[0] not in WEEKLY_FREQUENCIES or (not timing.in_week(row[0],week_start(offset)) and not (offset==0 and not row[2] and timing.ready(qid))):
                return 'This chore is not available for a sign-up that week.'
            with db:
                db.execute('INSERT OR REPLACE INTO week_signups VALUES(?,?,?)',(qid,week_key(offset),str(target)))
                if offset==0:
                    db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            return 'Weekly responsibility reassigned. Completed work and earned points are unchanged.'
        if scope=='assignment':
            if db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,week_key())).fetchone():
                return 'This chore has weekly sign-ups. Reassign those weeks instead, or release them before setting an ongoing assignment.'
            with db:
                db.execute('UPDATE quests SET assigned_to=? WHERE id=?',(str(target),qid))
                db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            return 'Ongoing assignment saved. The chore name, completion history, and earned points are unchanged.'
        if row[1] or weekly_owner(qid):
            return 'This chore has an ongoing assignment or weekly owner. Choose that scope instead.'
        if row[2] or not timing.ready(qid):
            return 'There is no open occurrence to reassign. Choose a weekly or ongoing assignment instead.'
        with db:
            db.execute('INSERT OR REPLACE INTO claims VALUES(?,?)',(qid,str(target)))
        return 'This occurrence reassigned. Completed work and earned points are unchanged.'

    class ReassignView(SafeView):
        def __init__(self,owner,page=0,qid=None,scope=None,target=None,expected=None):
            super().__init__(timeout=600)
            self.owner,self.qid,self.scope,self.target=owner,qid,scope,target
            entries=[r for r in db.execute('SELECT id,name FROM quests ORDER BY name COLLATE NOCASE,id') if not is_archived(r[0])]
            self.page=min(max(page,0),max((len(entries)-1)//PAGE_SIZE,0))
            self.expected=expected
            self.embed=discord.Embed(title='Reassign a chore',description='Choose a chore, how long the responsibility lasts, and a person. Then review and confirm. Everyone in the household can do this. Chore names, history, and earned points stay saved.')
            chunk=entries[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
            if chunk:
                picker=discord.ui.Select(placeholder='Choose a chore',row=0,options=[discord.SelectOption(label=name[:100],value=str(key),default=key==qid) for key,name in chunk])
                async def choose_chore(interaction):
                    chosen=int(picker.values[0])
                    await self.show(interaction,qid=chosen,scope=None,target=None,expected=reassign_snapshot(chosen))
                picker.callback=choose_chore
                self.add_item(picker)
            if qid is not None:
                row=db.execute('SELECT name,assigned_to FROM quests WHERE id=?',(qid,)).fetchone()
                if row:
                    self.embed.add_field(name='Chore',value=discord.utils.escape_markdown(row[0]),inline=False)
                scopes=[('This occurrence only','occurrence'),('Whole week · this week','week0'),('Whole week · next week','week1'),('Ongoing assignment','assignment')]
                choose_scope=discord.ui.Select(placeholder='For how long?',row=1,options=[discord.SelectOption(label=label,value=value,default=value==scope) for label,value in scopes])
                async def set_scope(interaction):
                    await self.show(interaction,scope=choose_scope.values[0],target=None)
                choose_scope.callback=set_scope
                self.add_item(choose_scope)
                if scope:
                    label=dict((value,label) for label,value in scopes)[scope]
                    if scope.startswith('week'):
                        offset=int(scope[-1])
                        label+=f' ({week_start(offset):%b %d} → {week_start(offset+1):%b %d}, Sunday 6 p.m. Eastern)'
                    self.embed.add_field(name='Scope',value=label,inline=False)
                    users=discord.ui.UserSelect(placeholder='Who should take it?',min_values=1,max_values=1,row=2)
                    async def set_target(interaction):
                        member=users.values[0]
                        if member.bot or getattr(getattr(member,'guild',None),'id',None)!=interaction.guild_id:
                            await interaction.response.send_message('Choose a person in this household server, not a bot.',ephemeral=True)
                            return
                        await self.show(interaction,target=member)
                    users.callback=set_target
                    self.add_item(users)
                    if target:
                        self.embed.add_field(name='Give to',value=discord.utils.escape_markdown(target.display_name),inline=False)
                        self.button('Confirm reassignment',self.confirm,row=3,style=discord.ButtonStyle.primary)
            if self.page:
                self.button('Previous',lambda i:self.show(i,page=self.page-1,qid=None,scope=None,target=None,expected=None))
            if (self.page+1)*PAGE_SIZE<len(entries):
                self.button('Next page',lambda i:self.show(i,page=self.page+1,qid=None,scope=None,target=None,expected=None))
            self.button('Cancel',self.cancel,row=3)

        def button(self,label,callback,row=4,style=discord.ButtonStyle.secondary):
            item=discord.ui.Button(label=label,row=row,style=style)
            item.callback=callback
            self.add_item(item)

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own Reassign view from the household panel.',ephemeral=True)
                return False
            return True

        async def show(self,interaction,**changes):
            values=dict(page=self.page,qid=self.qid,scope=self.scope,target=self.target,expected=self.expected)
            values.update(changes)
            view=ReassignView(self.owner,**values)
            await interaction.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())

        async def cancel(self,interaction):
            await interaction.response.edit_message(content='Reassignment canceled. Nothing changed.',embed=None,view=None)

        async def confirm(self,interaction):
            if not self.target or self.target.bot or getattr(getattr(self.target,'guild',None),'id',None)!=interaction.guild_id:
                await interaction.response.send_message('Choose a household member first.',ephemeral=True)
                return
            await interaction.response.defer()
            async with lock:
                notice=reassign(self.qid,self.target.id,self.scope,self.expected)
            await interaction.edit_original_response(content=notice,embed=None,view=None,allowed_mentions=discord.AllowedMentions.none())

    class HouseholdSetup(SafeView):
        def __init__(self, owner):
            super().__init__(timeout=600)
            self.owner = owner
            self.members = None
            select = discord.ui.UserSelect(placeholder="Select Kas and Z's two Discord accounts", min_values=2, max_values=2)
            async def choose(interaction):
                if any(m.bot for m in select.values):
                    await interaction.response.send_message("Select two people, not bot accounts.", ephemeral=True)
                    return
                self.members = [str(m.id) for m in select.values]
                names = ', '.join(discord.utils.escape_markdown(m.display_name) for m in select.values)
                await interaction.response.edit_message(content=f"Alternating-week people: **{names}**.\nAway Oct 18–25, 2026; home Oct 25–Nov 1. Switch Sunday 6 p.m. Eastern.\nTap Save to confirm these accounts.", view=self, allowed_mentions=discord.AllowedMentions.none())
            select.callback = choose
            self.add_item(select)
            button = discord.ui.Button(label="Save household", style=discord.ButtonStyle.success)
            button.callback = self.save
            self.add_item(button)

        async def interaction_check(self, interaction):
            if interaction.user.id != self.owner or not allowed(interaction) or not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("Only the administrator who opened setup can save it.", ephemeral=True)
                return False
            return True

        async def save(self, interaction):
            if not self.members:
                await interaction.response.send_message("Select Kas and Z's two accounts first.", ephemeral=True)
                return
            # No sign-ups may become unusable as a side effect of configuring identity.
            current = {r[0] for r in db.execute("SELECT user_id FROM alternating_members")}
            if current != set(self.members) and db.execute("SELECT 1 FROM week_signups WHERE week_start >= ? LIMIT 1", (week_key(),)).fetchone():
                await interaction.response.send_message("Release current and future weekly sign-ups before changing the alternating-week accounts.", ephemeral=True)
                return
            with db:
                db.execute("DELETE FROM alternating_members")
                db.executemany("INSERT INTO alternating_members VALUES (?)", [(m,) for m in self.members])
            # Remove only pending occurrence claims held by away members, not chore history.
            with db:
                for member in self.members:
                    if not available(member):
                        db.execute("DELETE FROM claims WHERE user_id = ?", (member,))
            await interaction.response.edit_message(content="Saved. Kas and Z can sign up and complete chores during home weeks; they can reserve next week's work while away.", view=None)

    def can_add(interaction, owner=None):
        return (allowed(interaction) and
                (owner is None or interaction.user.id == owner) and not getattr(interaction.user, 'bot', False))

    def is_archived(quest_id):
        return db.execute('SELECT 1 FROM archived_chores WHERE quest_id = ?', (quest_id,)).fetchone() is not None

    class RemoveChoreView(SafeView):
        def __init__(self, owner, removed=False, page=0, selected=None, notice=''):
            super().__init__(timeout=600)
            self.owner, self.removed = owner, removed
            entries = [(qid, name) for qid, name in db.execute('SELECT id, name FROM quests ORDER BY name COLLATE NOCASE, id') if is_archived(qid) == removed]
            self.page = min(max(page, 0), max((len(entries)-1)//PAGE_SIZE, 0))
            chunk = entries[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
            self.selected = next((r for r in chunk if r[0] == selected), None)
            self.expected = snapshot(selected) if self.selected else None
            self.embed = discord.Embed(title='Removed chores' if removed else 'Remove chore', description=notice or 'Choose a chore. Removal hides it from the board and weekly sign-ups; history and points stay saved. You can restore it here.')
            if self.selected:
                self.embed.add_field(name=self.selected[1][:256], value='Tap Restore to put it back.' if removed else 'Remove this chore from everyone’s board? Existing history is retained; current ownership and completion state are kept for restoration.', inline=False)
            if chunk:
                select = discord.ui.Select(placeholder='Choose a chore…', options=[discord.SelectOption(label=name[:100],value=str(qid)) for qid,name in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            if self.selected:
                self.button('Restore' if removed else 'Confirm removal', self.act, discord.ButtonStyle.success if removed else discord.ButtonStyle.danger)
            self.button('Active chores' if removed else 'Removed chores', lambda i: self.show(i, removed=not removed, page=0))
            if self.page:
                self.button('Previous', lambda i: self.show(i, page=self.page-1))
            if (self.page+1)*PAGE_SIZE < len(entries):
                self.button('Next', lambda i: self.show(i, page=self.page+1))
            self.embed.set_footer(text=f'Page {self.page+1} · Nobody’s points or completion history are deleted')

        def button(self,label,callback,style=discord.ButtonStyle.secondary):
            item=discord.ui.Button(label=label,style=style,row=1)
            item.callback=callback
            self.add_item(item)

        async def interaction_check(self, interaction):
            if not can_add(interaction, self.owner):
                await interaction.response.send_message('Open your own chore management view from the household panel.',ephemeral=True)
                return False
            return True

        async def show(self, interaction, removed=None, page=None, selected=None):
            view=RemoveChoreView(self.owner,self.removed if removed is None else removed,self.page if page is None else page,selected)
            await interaction.response.edit_message(embed=view.embed,view=view)

        async def act(self, interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Use your own household panel view.',ephemeral=True)
                return
            if snapshot(self.selected[0]) != self.expected:
                notice='This chore changed. Choose it again before confirming.'
            else:
                with db:
                    if self.removed:
                        db.execute('DELETE FROM archived_chores WHERE quest_id = ?', (self.selected[0],))
                    else:
                        db.execute('INSERT OR IGNORE INTO archived_chores VALUES (?, ?, ?)', (self.selected[0],str(self.owner),namespace['now_local']().isoformat()))
                notice='Restored.' if self.removed else 'Removed from the board. Find it under Removed chores if you want to restore it.'
            view=RemoveChoreView(self.owner,self.removed,notice=notice)
            await interaction.response.edit_message(embed=view.embed,view=view)

    def create_chore(name, frequency, points, notes):
        name = ' '.join(name.split())
        if not name:
            return "Give the chore a name."
        if frequency not in api.VALID_FREQUENCIES:
            return "Choose a valid repeat schedule."
        try:
            points = int(points.strip() or '5')
        except ValueError:
            return "Points must be a whole number (zero is fine)."
        if points < 0 or points > 1000000:
            return "Points must be between 0 and 1,000,000."
        # Include completed chores so a delayed/retried submission cannot duplicate one.
        for quest_id, existing_name in db.execute('SELECT id, name FROM quests').fetchall():
            if ' '.join(existing_name.split()).casefold() == name.casefold():
                return f"A chore with that name already exists (#{quest_id}). Nothing added. Choose a more specific name if this is a different chore."
        with db:
            db.execute("""INSERT INTO quests (name, frequency, points, notes, category, difficulty)
                VALUES (?, ?, ?, ?, 'general', 'normal')""", (name, frequency, points, notes.strip() or None))
            timing.initialize(db.execute('SELECT last_insert_rowid()').fetchone()[0],frequency)
        return f"Added **{discord.utils.escape_markdown(name)}**. It is open for sign-up; refresh Open chores to see it."

    class AddChoreModal(discord.ui.Modal):
        def __init__(self, owner, frequency):
            super().__init__(title="Add scheduled chore" if ":" in frequency else f"Add {frequency} chore", timeout=600)
            self.owner, self.frequency = owner, frequency
            self.name = discord.ui.TextInput(label="Chore name", placeholder=timing.label(frequency)[:100], max_length=100)
            self.notes = discord.ui.TextInput(label="Instructions / timing (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000, placeholder="What counts as done? Choose weekdays in the schedule picker; notes don't send reminders.")
            self.points = discord.ui.TextInput(label="Points (optional; blank means 5)", required=False, default="5", max_length=7)
            for item in (self.name, self.notes, self.points):
                self.add_item(item)

        async def on_submit(self, interaction):
            if not can_add(interaction, self.owner):
                await interaction.response.send_message("Use the form you opened from the household panel.", ephemeral=True)
                return
            message = create_chore(self.name.value, self.frequency, self.points.value, self.notes.value)
            await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

        async def on_error(self, interaction, error):
            if not interaction.response.is_done():
                await interaction.response.send_message("Couldn't confirm the result. Check Open chores before submitting again.", ephemeral=True)

    class AddChoreMenu(SafeView):
        def __init__(self, owner, edit_id=None, expected=None):
            super().__init__(timeout=600)
            self.owner = owner
            select = discord.ui.Select(placeholder="How often does this chore repeat?", options=[
                discord.SelectOption(label="Daily", value="daily", description="Returns at midnight; can be reserved for a week"),
                discord.SelectOption(label="Weekly", value="weekly", description="Returns Sunday at 6 p.m.; can be reserved for a week"),
                discord.SelectOption(label="Monthly", value="monthly", description="Returns on the first day of the month"),
                discord.SelectOption(label="One time", value="one-time", description="Does not return automatically after completion"),
                discord.SelectOption(label="Twice daily", value="twice-daily", description="One completion before noon; another after noon"),
                discord.SelectOption(label="On a specific weekday", value="weekday", description="Choose Monday through Sunday; overdue chores stay due"),
                discord.SelectOption(label="Twice a week", value="two-days", description="Choose two weekdays"),
                discord.SelectOption(label="Every other week", value="alternating", description="Choose a weekday and Kas/Z home or away weeks"),
            ])
            async def choose(interaction):
                if select.values[0] in ('two-days','alternating'):
                    await interaction.response.send_message('Choose the repeat days below.',view=RepeatMenu(owner,select.values[0],edit_id,expected),ephemeral=True)
                    return
                if select.values[0] == 'weekday':
                    await interaction.response.send_message('Choose the weekday.',view=WeekdayMenu(owner,edit_id,expected),ephemeral=True)
                else:
                    modal=AddChoreModal(owner,select.values[0]) if edit_id is None else EditChoreModal(owner,edit_id,select.values[0],expected)
                    await interaction.response.send_modal(modal)
            select.callback = choose
            self.add_item(select)

        async def interaction_check(self, interaction):
            if not can_add(interaction, self.owner):
                await interaction.response.send_message("Open your own form from the household panel.", ephemeral=True)
                return False
            return True

    class WeekdayMenu(SafeView):
        def __init__(self,owner,edit_id=None,expected=None):
            super().__init__(timeout=600)
            self.owner=owner
            select=discord.ui.Select(placeholder='Which weekday?',options=[discord.SelectOption(label=day.capitalize(),value=day,emoji=DAY_COLORS[day]) for day in WEEKDAYS])
            async def choose(interaction):
                modal=AddChoreModal(owner,select.values[0]) if edit_id is None else EditChoreModal(owner,edit_id,select.values[0],expected)
                await interaction.response.send_modal(modal)
            select.callback=choose
            self.add_item(select)

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Use the schedule picker you opened from the household panel.',ephemeral=True)
                return False
            return True

    class RepeatMenu(SafeView):
        def __init__(self,owner,kind,edit_id=None,expected=None,phase=None):
            super().__init__(timeout=600)
            self.owner=owner
            if kind == 'alternating' and phase is None:
                picker=discord.ui.Select(placeholder='Which alternating weeks?',options=[discord.SelectOption(label='Kas and Z away weeks',value='away'),discord.SelectOption(label='Kas and Z home weeks',value='home')])
                async def choose_phase(interaction):
                    await interaction.response.edit_message(content='Choose the weekday. This repeats every other week; overdue chores stay due.',view=RepeatMenu(owner,kind,edit_id,expected,picker.values[0]))
                picker.callback=choose_phase
            else:
                count=2 if kind == 'two-days' else 1
                picker=discord.ui.Select(placeholder='Choose two weekdays' if count==2 else 'Choose a weekday',min_values=count,max_values=count,options=[discord.SelectOption(label=day.capitalize(),value=day,emoji=DAY_COLORS[day]) for day in WEEKDAYS])
                async def choose_days(interaction):
                    days=sorted(picker.values,key=WEEKDAYS.index)
                    frequency='days:'+','.join(days) if count==2 else phase+':'+days[0]
                    modal=AddChoreModal(owner,frequency) if edit_id is None else EditChoreModal(owner,edit_id,frequency,expected)
                    await interaction.response.send_modal(modal)
                picker.callback=choose_days
            self.add_item(picker)

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own schedule picker from the household panel.',ephemeral=True)
                return False
            return True

    def update_chore(quest_id,name,frequency,points,notes,expected):
        api.reset_due_quests()
        if snapshot(quest_id)!=expected or is_archived(quest_id):
            return 'This chore changed. Reopen Edit chore before saving.'
        name=' '.join(name.split())
        if not name or len(name)>100 or frequency not in api.VALID_FREQUENCIES:
            return 'Enter a name (up to 100 characters) and a valid schedule.'
        try:
            points=int(points.strip() or '5')
        except ValueError:
            return 'Points must be a whole number.'
        if not 0<=points<=1000000:
            return 'Points must be between 0 and 1,000,000.'
        for other_id,other_name in db.execute('SELECT id,name FROM quests'):
            if other_id!=quest_id and ' '.join(other_name.split()).casefold()==name.casefold():
                return 'Another chore already has that name. Nothing changed.'
        old=db.execute('SELECT frequency,completed,last_completed FROM quests WHERE id=?',(quest_id,)).fetchone()
        if old[0]!=frequency and frequency not in WEEKLY_FREQUENCIES and db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(quest_id,week_key())).fetchone():
            return 'Release this chore’s current/future weekly sign-ups before changing it to monthly or one time.'
        with db:
            db.execute('UPDATE quests SET name=?,frequency=?,points=?,notes=? WHERE id=?',(name,frequency,points,notes.strip() or None,quest_id))
            if old[0]!=frequency:
                timing.initialize(quest_id,frequency)
                if old[1]:
                    when=datetime.fromisoformat(old[2]) if old[2] else namespace['now_local']()
                    if when.tzinfo is None:
                        when=when.replace(tzinfo=api.QUEST_TIMEZONE)
                    reset=timing.completion_reset(quest_id,when,frequency)
                    db.execute('UPDATE quests SET reset_after=? WHERE id=?',(reset,quest_id))
        return 'Saved. Existing assignments, claims, completions, and earned points are retained. New point values apply to future completions.'

    class EditChoreModal(AddChoreModal):
        def __init__(self,owner,quest_id,frequency,expected):
            super().__init__(owner,frequency)
            self.title='Edit chore'
            self.quest_id,self.expected=quest_id,expected
            row=db.execute('SELECT name,notes,points FROM quests WHERE id=?',(quest_id,)).fetchone()
            self.name.default=row[0]
            self.notes.default=row[1] or ''
            self.points.default=str(row[2])

        async def on_submit(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Use your own household edit form.',ephemeral=True)
                return
            result=update_chore(self.quest_id,self.name.value,self.frequency,self.points.value,self.notes.value,self.expected)
            await interaction.response.send_message(result,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    class EditChoreView(SafeView):
        def __init__(self,owner,page=0,selected=None):
            super().__init__(timeout=600)
            self.owner=owner
            api.reset_due_quests()
            entries=[r for r in db.execute('SELECT id,name,frequency FROM quests ORDER BY name COLLATE NOCASE,id') if not is_archived(r[0])]
            self.page=min(max(page,0),max((len(entries)-1)//PAGE_SIZE,0))
            chunk=entries[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
            chosen=next((r for r in chunk if r[0]==selected),None)
            self.embed=discord.Embed(title='Edit chore',description='Choose a chore to edit its name, instructions, points, or schedule. Existing earned points and history stay saved.')
            if chunk:
                select=discord.ui.Select(placeholder='Choose a chore…',options=[discord.SelectOption(label=r[1][:100],value=str(r[0])) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction,selected=int(select.values[0]))
                select.callback=choose
                self.add_item(select)
            if chosen:
                expected=snapshot(chosen[0])
                self.embed.add_field(name=chosen[1][:256],value=timing.label(chosen[2]),inline=False)
                async def details(interaction):
                    await interaction.response.send_modal(EditChoreModal(owner,chosen[0],chosen[2],expected))
                async def schedule(interaction):
                    await interaction.response.send_message('Choose the replacement schedule, then review and submit the prefilled form.',view=AddChoreMenu(owner,chosen[0],expected),ephemeral=True)
                self.button('Edit details',details)
                self.button('Change schedule',schedule)
            if self.page:
                self.button('Previous',lambda i:self.show(i,page=self.page-1))
            if (self.page+1)*PAGE_SIZE<len(entries):
                self.button('Next',lambda i:self.show(i,page=self.page+1))

        def button(self,label,callback):
            button=discord.ui.Button(label=label,row=1)
            button.callback=callback
            self.add_item(button)

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Edit chore view.',ephemeral=True)
                return False
            return True

        async def show(self,interaction,page=None,selected=None):
            view=EditChoreView(self.owner,self.page if page is None else page,selected)
            await interaction.response.edit_message(embed=view.embed,view=view)

    HELP_HINT = 'Need help? Tap **Help** below for the button guide, or type **!help** for command help.'
    BOARD_TEXT = ('🌱 **Sprig · household chores**\n'
                  'A little care for our shared space.\n\n'
                  '**Your day** · Open **My chores** to finish a task, or **Open chores** to pick one up.\n'
                  '**Plan together** · Reserve your week or see who’s doing what.\n\n'
                  'Button replies are private. Your changes stay saved for the household.\n' + HELP_HINT)

    def help_embed():
        embed = discord.Embed(title='How to use Sprig', description='Use the buttons to manage chores. This guide is private; everyone with access to the household panel can open it.')
        for title, text in [
            ('Sign up for a chore', 'Open chores → choose a chore → Claim. It then appears in My chores.'),
            ('Mark work done', 'My chores → choose the chore → Done. Use Release to give up a one-off claim when that option is shown.'),
            ('Give a chore to someone else', 'Reassign → choose chore → choose This occurrence, Whole week (this or next), or Ongoing assignment → select a household member → Confirm reassignment. Anyone can do this. Names, history, and earned points stay saved. Weekly owners must be changed using the whole-week scope.'),
            ('See everyone’s chores', 'Who’s doing what? shows This week / Next week, each person’s assignments and weekly sign-ups, and Nobody signed up. Single claims do not carry into next week. Refresh to see new changes.'),
            ('Take a whole week', 'Weekly sign-ups → This week or Next week → choose a chore → Sign up for week. Daily chores stay yours after Done and return when due. Use Release week to give up the reservation.'),
            ('Kas and Z’s weeks', 'Weeks switch Sunday at 6 p.m. Eastern. Once their accounts are saved in Household setup, Kas and Z can sign up only for their home weeks. Ask a household administrator if the accounts or week look wrong.'),
            ('Add, edit, or remove', 'Everyone can use Add chore, Edit chore, and Remove chore. Removal asks for confirmation and hides the chore; Removed chores → Restore brings it back. Earned points and history stay saved.'),
            ('When chores return', 'Daily: midnight. Twice daily: midnight and noon. Weekly: Sunday at 6 p.m. Monthly: first day of the month. Twice-weekly chores return on the two chosen weekdays. Every-other-week chores follow the selected Kas/Z home or away weeks. Scheduled chores stay due until done. One-time chores do not repeat. Times are Eastern; notes do not send reminders.'),
            ('Open fresh controls or get more help', 'Use /chores for a fully private panel once enabled, or !chores for fresh buttons with a public starter message. Button replies are private. Reopen after 10 minutes or a restart. Type !help for the older command guide. Household setup is for administrators.')
        ]:
            embed.add_field(name=title, value=text, inline=False)
        return embed

    class Launcher(SafeView):
        def __init__(self,timeout=None):
            super().__init__(timeout=timeout)
            # Keep both the persistent dashboard and fresh panels in the same order.
            layout=[('My chores',0),('Open chores',0),('Weekly sign-ups',0),
                    ('Who’s doing what?',1),('Reassign',1),('Help',1),
                    ('Add chore',2),('Edit chore',2),('Remove chore',2),('Household setup',2)]
            buttons={item.label:item for item in self.children}
            self.clear_items()
            for label,row in layout:
                item=buttons[label]
                item.row=row
                item.style=discord.ButtonStyle.primary if label=='My chores' else discord.ButtonStyle.secondary
                self.add_item(item)

        async def interaction_check(self, interaction):
            if not allowed(interaction):
                await interaction.response.send_message("Use the current household chore board.", ephemeral=True)
                return False
            return True

        async def open_list(self, interaction, mode):
            view = PersonalView(interaction.user.id, mode)
            await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

        @discord.ui.button(label="Who’s doing what?", custom_id="sprig:responsibilities:v1", row=1)
        async def responsibility_button(self,interaction,button):
            await interaction.response.defer(ephemeral=True,thinking=True)
            view=await responsibility_view(interaction.user.id,interaction.guild)
            await interaction.followup.send(embed=view.embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

        @discord.ui.button(label="Reassign",custom_id="sprig:reassign:v1",row=1)
        async def reassign_button(self,interaction,button):
            view=ReassignView(interaction.user.id)
            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)

        @discord.ui.button(label="Help", custom_id="sprig:help:v1", row=1)
        async def help_button(self, interaction, button):
            await interaction.response.send_message(embed=help_embed(), ephemeral=True)

        @discord.ui.button(label="Open chores", style=discord.ButtonStyle.primary, custom_id="sprig:open:v1")
        async def open_button(self, interaction, button):
            await self.open_list(interaction, "open")

        @discord.ui.button(label="My chores", style=discord.ButtonStyle.success, custom_id="sprig:mine:v1")
        async def mine_button(self, interaction, button):
            await self.open_list(interaction, "mine")

        @discord.ui.button(label="Weekly sign-ups", style=discord.ButtonStyle.primary, custom_id="sprig:weeks:v1")
        async def weeks_button(self, interaction, button):
            view = WeeklyView(interaction.user.id)
            await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

        @discord.ui.button(label="Household setup", custom_id="sprig:household:v1")
        async def setup_button(self, interaction, button):
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("Household setup is for server administrators.", ephemeral=True)
                return
            await interaction.response.send_message("Select Kas and Z's Discord accounts, then Save. Weeks switch Sunday at 6 p.m. Eastern; Oct 18, 2026 starts an away week.", view=HouseholdSetup(interaction.user.id), ephemeral=True)

        @discord.ui.button(label="Add chore", style=discord.ButtonStyle.success, custom_id="sprig:add:v1")
        async def add_button(self, interaction, button):
            if not can_add(interaction):
                await interaction.response.send_message("Use the household panel in its configured channel.", ephemeral=True)
                return
            await interaction.response.send_message("Choose a repeat schedule, then fill in the form. Weekday chores appear on their due day and stay due until done. Twice daily has a morning slot and an afternoon/evening slot (noon and midnight resets). New chores are shared/open; name personal chores specifically. Notes don't send reminders.", view=AddChoreMenu(interaction.user.id), ephemeral=True)

        @discord.ui.button(label="Remove chore", style=discord.ButtonStyle.secondary, custom_id="sprig:remove:v1", row=1)
        async def remove_button(self, interaction, button):
            view=RemoveChoreView(interaction.user.id)
            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)

        @discord.ui.button(label='Edit chore',custom_id='sprig:edit:v1',row=1)
        async def edit_button(self,interaction,button):
            view=EditChoreView(interaction.user.id)
            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)

    @bot.hybrid_command(name='chores',description='Open your chore buttons here, privately when using /chores')
    @commands.guild_only()
    async def chores(ctx):
        """A fresh local entry point; slash responses and all button actions are private."""
        private=bool(ctx.interaction)
        check=SimpleNamespace(guild_id=ctx.guild.id if ctx.guild else None,channel_id=ctx.channel.id,guild=ctx.guild,user=ctx.author)
        if not allowed(check):
            await ctx.send("Use the household server with access to the chores channel. Check panel setup if it hasn't been completed.",ephemeral=private)
            return
        text=BOARD_TEXT + '\nReopen **/chores** after 10 minutes or a restart.'
        if not private:
            text+='\nThis starter message is public. Use **/chores** for a fully private panel without a channel message.'
        await ctx.send(text,view=Launcher(timeout=600),ephemeral=private,allowed_mentions=discord.AllowedMentions.none())

    @bot.command(name='enableprivatechores')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def enableprivatechores(ctx):
        """One-time explicit registration of /chores in the household guild."""
        saved=location()
        if not saved or saved[2]=='pending' or str(ctx.guild.id)!=saved[0]:
            await ctx.send('Finish household panel setup in this server first.')
            return
        guild=discord.Object(id=int(saved[0]))
        existing=await bot.tree.fetch_commands(guild=guild)
        local_names={command.name for command in bot.tree.get_commands(guild=guild)} | {'chores'}
        if any(command.name not in local_names for command in existing):
            await ctx.send("Other server commands aren't represented in this bot's command tree. Nothing synced, so they won't be overwritten.")
            return
        bot.tree.add_command(bot.tree.get_command('chores'),guild=guild,override=True)
        await bot.tree.sync(guild=guild)
        await ctx.send('Enabled **/chores** in this household server. It opens a fully private panel. No chores or board messages were changed.')

    @bot.command(name="board")
    @commands.guild_only()
    async def board(ctx):
        """Find the existing household panel from any channel in its server."""
        saved=location()
        if not saved or saved[2]=='pending':
            await ctx.send("There isn't a confirmed chore panel yet. Ask the household to check setup before posting another one.")
            return
        if ctx.guild is None or str(ctx.guild.id)!=saved[0]:
            await ctx.send("There isn't a chore board configured for this server.")
            return
        channel=ctx.guild.get_channel(int(saved[1]))
        if channel is None:
            await ctx.send("I can't find the saved chores channel. Ask the household to check it; I haven't created another panel.")
            return
        permissions=channel.permissions_for(ctx.author)
        if not permissions.view_channel or not permissions.read_message_history:
            await ctx.send("You need access to the chores channel and its message history to open the board.")
            return
        await ctx.send(f"🌱 **Household chore board:** https://discord.com/channels/{saved[0]}/{saved[1]}/{saved[2]}",allowed_mentions=discord.AllowedMentions.none())

    @bot.command(name="refreshchoreboard")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def refreshchoreboard(ctx):
        """Update the existing panel's buttons after an approved upgrade; never repost."""
        saved = location()
        if not saved or saved[2] == 'pending':
            await ctx.send("No confirmed panel to refresh. Inspect the saved setup first.")
            return
        if str(ctx.guild.id) != saved[0] or str(ctx.channel.id) != saved[1]:
            await ctx.send("Run this in the existing household chores channel.")
            return
        message = await ctx.channel.fetch_message(int(saved[2]))
        if message.author.id != bot.user.id:
            await ctx.send("The saved message is not Sprig's panel. Nothing changed.")
            return
        await message.edit(content=BOARD_TEXT, view=Launcher())
        await ctx.send("Updated the existing panel's buttons. Your chores and sign-ups are unchanged.")

    @bot.command(name="choreboard")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def choreboard(ctx):
        """One-time household admin setup. Everyone else uses the buttons."""
        async with lock:
            saved = location()
            if saved:
                if saved[2] == "pending":
                    await ctx.send("Board setup was interrupted. Check this channel for the board before an administrator repairs the saved setup; I won't post a duplicate.")
                else:
                    await ctx.send(f"The chore board is already set up: https://discord.com/channels/{saved[0]}/{saved[1]}/{saved[2]}")
                return
            # Reserve setup before delivery. A timeout may still have posted it.
            db.execute("INSERT INTO chore_board VALUES (1, ?, ?, 'pending')", (str(ctx.guild.id), str(ctx.channel.id)))
            db.commit()
            message = await ctx.send(BOARD_TEXT, view=Launcher())
            db.execute("UPDATE chore_board SET message_id = ? WHERE singleton = 1", (str(message.id),))
            db.commit()

    previous_setup = bot.setup_hook

    async def setup_hook():
        await previous_setup()
        bot.add_view(Launcher())
        saved=location()
        if saved and saved[2]!='pending':
            # Register the local handler after restarts; do not sync remotely
            # until an administrator explicitly enables the slash command.
            bot.tree.add_command(bot.tree.get_command('chores'),guild=discord.Object(id=int(saved[0])),override=True)

    bot.setup_hook = setup_hook
    return SimpleNamespace(ReassignView=ReassignView, reassign=reassign, reassign_snapshot=reassign_snapshot, responsibility_view=responsibility_view, responsibility_rows=responsibility_rows, ResponsibilityView=ResponsibilityView, Launcher=Launcher, PersonalView=PersonalView, WeeklyView=WeeklyView, HouseholdSetup=HouseholdSetup, AddChoreModal=AddChoreModal, AddChoreMenu=AddChoreMenu, RemoveChoreView=RemoveChoreView, EditChoreView=EditChoreView, EditChoreModal=EditChoreModal, RepeatMenu=RepeatMenu, WeekdayMenu=WeekdayMenu, update_chore=update_chore, ready=timing.ready, completion_reset=timing.completion_reset, timing=timing, is_archived=is_archived, create_chore=create_chore, snapshot=snapshot, rows=rows, week_key=week_key, available=available, weekly_owner=weekly_owner, signup=signup)
