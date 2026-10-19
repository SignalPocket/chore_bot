"""Button interface for Sprig; existing commands remain the source of mutations."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import discord
from discord.ext import commands

PAGE_SIZE = 20


def install(namespace):
    api = SimpleNamespace(**namespace)
    bot, db = api.bot, api.db
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
            WHERE q.frequency IN ('daily', 'weekly') AND q.assigned_to IS NULL
            ORDER BY q.name COLLATE NOCASE, q.id""").fetchall()
        return [r for r in result if weekly_owner(r[0], offset) in (None, str(user_id))
                and (offset != 0 or not r[5] or r[5] == str(user_id))]

    def signup(user_id, quest_id, key):
        offsets = {week_key(0): 0, week_key(1): 1}
        offset = offsets.get(key)
        if offset is None:
            return "The week changed. Reopen Weekly sign-ups."
        if not available(user_id, offset):
            return "You're away that week. Choose a week when you're home."
        row = db.execute("SELECT frequency, assigned_to FROM quests WHERE id = ?", (quest_id,)).fetchone()
        if not row or row[0] not in ('daily', 'weekly') or row[1]:
            return "This chore is no longer available for a weekly sign-up."
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
        if not available(user_id):
            return []
        if mode == "mine":
            return [r for r in result if str(r[4] or weekly_owner(r[0]) or r[5]) == str(user_id)]
        return [r for r in result if not r[4] and not r[5] and not weekly_owner(r[0])]

    def snapshot(quest_id):
        row = db.execute("""SELECT q.completed, q.last_completed, q.assigned_to, c.user_id
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id WHERE q.id = ?""", (quest_id,)).fetchone()
        return (row, week_key(), weekly_owner(quest_id))

    def allowed(interaction):
        saved = location()
        return saved and str(interaction.guild_id) == saved[0] and str(interaction.channel_id) == saved[1]

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
                self.embed.add_field(name=r[1][:256], value=f"{r[2].capitalize()} · {r[3]} points{responsibility}\n{(r[7] or '')[:700]}", inline=False)
            elif not chunk:
                self.embed.add_field(name="All clear", value="No open chores right now." if mode == "open" else "Nothing assigned or claimed. Tap Open chores to sign up.")
            else:
                self.embed.add_field(name="Available here", value="\n".join(f"• {discord.utils.escape_markdown(r[1])[:44]}" for r in chunk)[:1024], inline=False)
            self.embed.set_footer(text=f"Page {self.page + 1} of {max((len(self.entries) - 1) // PAGE_SIZE + 1, 1)} · Private view · Reopen from the main board after 10 minutes or a bot restart.")
            if chunk:
                select = discord.ui.Select(placeholder="Choose a chore…", options=[discord.SelectOption(label=r[1][:100], value=str(r[0]), description=f"{r[2]} · {r[3]} points · #{r[0]}"[:100], default=bool(self.selected and r[0] == self.selected[0])) for r in chunk])
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
            self.embed = discord.Embed(title="🌱 Weekly sign-ups", description=f"{start:%b %d} at 6 p.m. → {end:%b %d} at 6 p.m.\n{status}\n{notice or 'Reserve a recurring chore for this week or next week.'}")
            if not db.execute("SELECT 1 FROM alternating_members LIMIT 1").fetchone():
                self.embed.add_field(name="Household setup needed", value="An administrator still needs to select Kas and Z in Household setup so their away weeks can be enforced.", inline=False)
            if self.selected:
                r = self.selected
                state = "You're signed up" if weekly_owner(r[0], offset) == str(owner) else "Open for the week"
                self.embed.add_field(name=r[1][:256], value=f"{r[2]} · {state}\n{(r[7] or '')[:700]}", inline=False)
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

    class Launcher(SafeView):
        def __init__(self):
            super().__init__(timeout=None)

        async def interaction_check(self, interaction):
            if not allowed(interaction):
                await interaction.response.send_message("Use the current household chore board.", ephemeral=True)
                return False
            return True

        async def open_list(self, interaction, mode):
            view = PersonalView(interaction.user.id, mode)
            await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

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
            message = await ctx.send("🌱 **Household chores**\nTap **Open chores** to sign up. Tap **My chores** to mark your work **Done**.\nYour list is private; changes are saved for everyone.", view=Launcher())
            db.execute("UPDATE chore_board SET message_id = ? WHERE singleton = 1", (str(message.id),))
            db.commit()

    previous_setup = bot.setup_hook

    async def setup_hook():
        await previous_setup()
        bot.add_view(Launcher())

    bot.setup_hook = setup_hook
    return SimpleNamespace(Launcher=Launcher, PersonalView=PersonalView, WeeklyView=WeeklyView, HouseholdSetup=HouseholdSetup, snapshot=snapshot, rows=rows, week_key=week_key, available=available, weekly_owner=weekly_owner, signup=signup)
