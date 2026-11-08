"""Button interface for Sprig; existing commands remain the source of mutations."""
import asyncio
import json
from uuid import uuid4
from time import monotonic
from datetime import datetime, timedelta
from types import SimpleNamespace

import discord
from discord.ext import commands
from household_availability import HouseholdAvailability
from chore_timing import ChoreTiming, WEEKDAYS, WEEKLY_FREQUENCIES, DAY_COLORS, DAY_LEGEND, day_badge

PAGE_SIZE = 20
ACTION_ACK_SECONDS = 1.0
REVIEW_OWNER_ID = 301104023405199361


APP_VERSION = '2.3.2'
# Keep this to one short sentence describing changes since the previous release.
RELEASE_SUMMARY = 'Confirming reassignment returns directly to your original chore list and page.'
UPDATE_NOTICE = f'Sprig has been updated to version {APP_VERSION}. Open /chores for fresh controls.'


def update_notice(at=None):
    """Timestamp the announcement in Eastern time, including its DST abbreviation."""
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo('America/New_York')
    at = datetime.now(eastern) if at is None else at
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('Announcement time must include a timezone')
    local = at.astimezone(eastern)
    stamp = (f'{local:%B} {local.day}, {local.year} at '
             f'{local.hour % 12 or 12}:{local:%M} {local:%p %Z}')
    return f'{UPDATE_NOTICE}\nWhat’s new: {RELEASE_SUMMARY}\nAnnounced {stamp} (Eastern time).'



def current_release(base_dir):
    """Read the deployed commit without a shell or any network access."""
    import subprocess
    try:
        result = subprocess.run(['git', '-C', str(base_dir), 'rev-parse', '--verify', 'HEAD'],
            capture_output=True, text=True, check=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha if len(sha) == 40 and all(c in '0123456789abcdef' for c in sha) else None


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
    db.execute("CREATE TABLE IF NOT EXISTS chore_revisions(quest_id INTEGER PRIMARY KEY,revision INTEGER NOT NULL)")
    db.commit()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS week_signups (
            quest_id INTEGER NOT NULL, week_start TEXT NOT NULL, user_id TEXT NOT NULL,
            PRIMARY KEY (quest_id, week_start));
        CREATE TABLE IF NOT EXISTS alternating_members (
            user_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS archived_chores (
            quest_id INTEGER PRIMARY KEY, removed_by TEXT NOT NULL, removed_at TEXT NOT NULL);
    """)
    db.execute("""CREATE TABLE IF NOT EXISTS chore_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposer TEXT NOT NULL, recipient TEXT NOT NULL,
        offered INTEGER NOT NULL, requested INTEGER NOT NULL, offered_scope TEXT NOT NULL,
        requested_scope TEXT NOT NULL, offered_snapshot TEXT NOT NULL, requested_snapshot TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending')""")
    db.commit()

    db.execute("""CREATE TABLE IF NOT EXISTS chore_feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT, submission_key TEXT UNIQUE NOT NULL,
        quest_id INTEGER NOT NULL, author_id TEXT NOT NULL, author_name TEXT NOT NULL,
        comment TEXT NOT NULL, timing TEXT NOT NULL, suggested_points INTEGER,
        created_at TEXT NOT NULL, context TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0)""")
    db.commit()
    db.execute("CREATE TABLE IF NOT EXISTS feedback_notifications (feedback_id INTEGER PRIMARY KEY, status TEXT NOT NULL)")
    db.commit()
    attendance=HouseholdAvailability(db,api.QUEST_TIMEZONE)

    def week_start(offset=0):
        now = namespace['now_local']().astimezone(api.QUEST_TIMEZONE)
        start = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=18, minute=0, second=0, microsecond=0)
        if now < start:
            start -= timedelta(days=7)
        return start + timedelta(weeks=offset)

    def week_key(offset=0):
        return week_start(offset).date().isoformat()

    def available(user_id, offset=0):
        return attendance.at(user_id,namespace['now_local']() if offset==0 else week_start(offset))

    def week_status(user_id,offset=0):
        return attendance.status(user_id,week_start(offset))

    def coverage_warning(qid,user_id,offset=0):
        frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()
        if not frequency:
            return ''
        frequency=frequency[0]
        days=attendance.week(user_id,week_start(offset))
        if frequency in ('daily','twice-daily','daily-am','daily-pm'):
            away=[when for when,home in days if not home]
        elif frequency in WEEKDAYS or ':' in frequency:
            away=[when for when,home in days[1:] if timing.matches(when.date(),frequency) and not home]
        else:
            away=[when for when,home in days if not home] if week_status(user_id,offset)!='home' else []
        if not away:
            return ''
        return 'Check coverage: away '+', '.join(f'{day_badge(WEEKDAYS[when.weekday()])} {when:%b %d}' for when in away)

    def can_take_week(user_id,qid,offset):
        days=attendance.week(user_id,week_start(offset))
        if offset==0:
            today=namespace['now_local']().astimezone(api.QUEST_TIMEZONE).date()
            days=[(when,home) for when,home in days if when.date()>=today]
        if not any(home for _,home in days):
            return False
        frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()
        if frequency and (frequency[0] in WEEKDAYS or ':' in frequency[0]):
            scheduled=[(when,home) for when,home in days if when!=week_start(offset) and timing.matches(when.date(),frequency[0])]
            return all(home for _,home in scheduled) if scheduled else (offset==0 and available(user_id))
        return True

    def weekly_owner(quest_id, offset=0):
        row = db.execute("SELECT user_id FROM week_signups WHERE quest_id = ? AND week_start = ?", (quest_id, week_key(offset))).fetchone()
        return row[0] if row else None

    original_reset = api.reset_due_quests

    def reset_with_availability():
        timing.skip_missed()
        result = original_reset()
        # Preserve responsibilities when attendance changes; show coverage warnings.
        with db:
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
        if hasattr(namespace.get('chore_ui'),'repeating') and namespace['chore_ui'].repeating.slots(quest_id):
            return 'This chore has repeating weekday signups. Manage those days instead of taking the whole week.'
        offsets = {week_key(0): 0, week_key(1): 1}
        offset = offsets.get(key)
        if offset is None:
            return "The week changed. Reopen Weekly sign-ups."
        if week_status(user_id,offset)=='away':
            return "You're away that week. Choose a week when you're home."
        row = db.execute("SELECT frequency, assigned_to FROM quests WHERE id = ?", (quest_id,)).fetchone()
        if not row or is_archived(quest_id) or row[0] not in WEEKLY_FREQUENCIES or row[1]:
            return "This chore is no longer available for a weekly sign-up."
        if not timing.in_week(row[0],week_start(offset)) and not (offset == 0 and timing.ready(quest_id)):
            return 'This chore is not scheduled for that week.'
        if not can_take_week(user_id,quest_id,offset):
            return 'You are away on a scheduled chore day. Choose another chore or update attendance.'
        claim = db.execute("SELECT user_id FROM claims WHERE quest_id = ?", (quest_id,)).fetchone()
        if offset == 0 and claim and claim[0] != str(user_id):
            return "Someone already claimed this occurrence. Choose another chore."
        with db:
            db.execute("INSERT OR IGNORE INTO week_signups VALUES (?, ?, ?)", (quest_id, key, str(user_id)))
            if offset == 0 and weekly_owner(quest_id, offset) == str(user_id):
                db.execute("DELETE FROM claims WHERE quest_id = ? AND user_id = ?", (quest_id, str(user_id)))
        if weekly_owner(quest_id, offset) != str(user_id):
            return "Someone already signed up for this chore that week."
        return "You're signed up for the week. Daily chores stay yours after each Done until Sunday at 6 p.m. " + coverage_warning(quest_id,user_id,offset)

    def location():
        return db.execute("SELECT guild_id, channel_id, message_id FROM chore_board WHERE singleton = 1").fetchone()

    db.execute("""CREATE TABLE IF NOT EXISTS update_announcements (
        release_id TEXT PRIMARY KEY, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL,
        status TEXT NOT NULL, message_id TEXT)""")
    db.commit()

    db.execute("""CREATE TABLE IF NOT EXISTS announcement_settings (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), automatic INTEGER NOT NULL,
        revision INTEGER NOT NULL)""")
    db.commit()

    def announcement_mode():
        row = db.execute('SELECT automatic,revision FROM announcement_settings WHERE singleton=1').fetchone()
        return (bool(row[0]),row[1]) if row else (False,0)

    def set_announcement_mode(actor,enabled,expected):
        if str(actor)!=str(REVIEW_OWNER_ID):return 'Only ginaria can change update announcements.'
        if announcement_mode()!=expected:return 'This setting changed. Review the current choice.'
        with db:
            db.execute('INSERT INTO announcement_settings VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET automatic=excluded.automatic,revision=excluded.revision',
                (int(bool(enabled)),expected[1]+1))
        return 'Automatic update announcements are '+('on.' if enabled else 'off. You can still choose Announce this update.')

    async def announce_update(manual_actor=None,expected_location=None):
        if manual_actor is not None and str(manual_actor)!=str(REVIEW_OWNER_ID):
            return 'owner_only'
        expected_mode=announcement_mode()
        if manual_actor is None and not expected_mode[0]:return 'disabled'
        import logging
        logger = logging.getLogger('discord.sprig')
        saved = location()
        if expected_location is not None and saved!=expected_location:return 'changed'
        if not saved or saved[2] == 'pending':
            return 'not_configured'
        release = await asyncio.to_thread(current_release, api.BASE_DIR)
        if not release:
            return 'no_release'
        if db.execute('SELECT 1 FROM update_announcements WHERE release_id=?', (release,)).fetchone():
            return 'already_attempted'
        try:
            channel = bot.get_channel(int(saved[1])) or await bot.fetch_channel(int(saved[1]))
        except Exception:
            logger.exception('Update notice channel lookup failed; no message was attempted')
            return 'lookup_failed'
        if location() != saved or (manual_actor is None and announcement_mode()!=expected_mode):
            return 'changed'
        if (str(getattr(channel, 'id', '')) != saved[1]
                or str(getattr(getattr(channel, 'guild', None), 'id', '')) != saved[0]):
            return 'wrong_channel'
        # Persist before sending. Discord might accept a message even if the
        # reply is lost; never replay an uncertain announcement on reconnect.
        with db:
            claimed = db.execute('INSERT OR IGNORE INTO update_announcements VALUES(?,?,?,?,NULL)',
                (release, saved[0], saved[1], 'sending')).rowcount
        if not claimed:
            return 'already_attempted'
        try:
            message = await channel.send(update_notice(), allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            with db:
                db.execute("UPDATE update_announcements SET status='failed_uncertain' WHERE release_id=?", (release,))
            logger.exception('Update notice delivery uncertain; not retrying automatically')
            return 'failed_uncertain'
        with db:
            db.execute("UPDATE update_announcements SET status='sent',message_id=? WHERE release_id=?",
                (str(message.id), release))
        return 'sent'

    def rows(user_id, mode):
        api.reset_due_quests()
        result = db.execute("""SELECT q.id, q.name, q.frequency, q.points,
            q.assigned_to, c.user_id, q.last_completed, q.notes
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id
            WHERE q.completed = 0 ORDER BY q.name COLLATE NOCASE, q.id""").fetchall()
        result = [r for r in result if not is_archived(r[0]) and timing.ready(r[0])]
        if not available(user_id):
            return []
        def responsible(qid):return namespace['chore_ui'].workspace.ownership(qid)[0]
        if mode == "mine":
            return [r for r in result if responsible(r[0]) == str(user_id)]
        return [r for r in result if not responsible(r[0])]

    def snapshot(quest_id):
        row = db.execute("""SELECT q.completed, q.last_completed, q.assigned_to, c.user_id
            FROM quests q LEFT JOIN claims c ON c.quest_id = q.id WHERE q.id = ?""", (quest_id,)).fetchone()
        details=db.execute('SELECT name,frequency,points,notes,category,difficulty FROM quests WHERE id=?',(quest_id,)).fetchone()
        return (row, week_key(), weekly_owner(quest_id), is_archived(quest_id), details, timing.state(quest_id), timing.policy_state(quest_id), db.execute("SELECT day FROM occurrence_moves WHERE quest_id=?",(quest_id,)).fetchone(), db.execute("SELECT revision FROM chore_revisions WHERE quest_id=?",(quest_id,)).fetchone())

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
        def add_dashboard(self,row=4):
            button=discord.ui.Button(label='Dashboard',row=row,style=discord.ButtonStyle.primary)
            async def home(interaction):
                await workspace.present(interaction,workspace.Chores(interaction.user.id,interaction.guild))
            button.callback=home
            self.add_item(button)

        async def on_error(self, interaction, error, item):
            # Do not repeat an action after a response failure: it may have saved.
            message = "I couldn't finish updating this view. Open /chores again to check what saved before trying again."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            import logging
            logging.getLogger(__name__).exception("Chore board interaction failed", exc_info=error)

    class ReturnView(SafeView):
        def __init__(self,owner):
            super().__init__(timeout=600)
            self.owner=owner
            mine=discord.ui.Button(label='Chores',style=discord.ButtonStyle.primary)
            async def open_mine(interaction):
                await workspace.present(interaction,workspace.Chores(owner,interaction.guild,who='mine'))
            mine.callback=open_mine
            self.add_item(mine)
            self.add_dashboard(row=0)

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own dashboard with /chores.',ephemeral=True)
                return False
            return True

    class Context:
        def __init__(self, interaction):
            self.author, self.guild = interaction.user, interaction.guild
            self.messages = []

        async def send(self, content, **kwargs):
            # Buffer command feedback: no network await during its DB mutation.
            self.messages.append(content)

    def chore_option(qid,name,extra='',selected=False):
        frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()[0]
        description=timing.compact_label(frequency)+((' · '+extra) if extra else '')
        return discord.SelectOption(label=name[:100],value=str(qid),description=description[:100],emoji=timing.emoji(frequency),default=selected)

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
            away_message = "You're away today. Use Weekly sign-ups on the main board to reserve your next home week's chores."
            self.embed = discord.Embed(title=f"🌱 {title}", description=(notice or ("Choose a chore below. No commands needed." if available(owner) else away_message))+"\n"+DAY_LEGEND)
            if self.selected:
                r = self.selected
                responsibility = " · Yours through Sunday at 6 p.m." if weekly_owner(r[0]) == str(owner) else ""
                self.embed.add_field(name=r[1][:256], value=f"{timing.label(r[2],r[0])} · {r[3]} points{responsibility}\n{(r[7] or '')[:650]}", inline=False)
            elif not chunk:
                self.embed.add_field(name='Away today' if not available(owner) else 'All clear',value='Your responsibilities remain saved. Check Who’s home? or the weekly overview for coverage.' if not available(owner) else ("No open chores right now." if mode == "open" else "No chores due right now. Check weekly sign-ups or the overview for upcoming work."))
            else:
                for part in range(0,len(chunk),6):
                    self.embed.add_field(name='Available here' if part==0 else 'More chores',value='\n'.join(f"• **{discord.utils.escape_markdown(r[1])[:65]}** — {timing.compact_label(r[2])}" for r in chunk[part:part+6]),inline=False)
            self.embed.set_footer(text=f"Page {self.page + 1} of {max((len(self.entries) - 1) // PAGE_SIZE + 1, 1)} · Private view · Reopen /chores after 10 minutes or a restart.")
            if chunk:
                select = discord.ui.Select(placeholder="Choose a chore…", options=[chore_option(r[0],r[1],f"{r[3]} points",selected=bool(self.selected and r[0]==self.selected[0])) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            if mode=='mine':
                self.add_button('Open chores',lambda i:self.show(i,mode='open',page=0),row=3)
            else:
                self.add_button('My chores',lambda i:self.show(i,mode='mine',page=0),row=3)
            if self.selected is not None or self.page:
                self.add_button('Back to list',lambda i:self.show(i,page=0),row=3)
            if self.selected:
                if mode == "open":
                    self.add_button("Claim", lambda i: self.act(i, "claim"), discord.ButtonStyle.success)
                else:
                    self.add_button("Done", lambda i: self.act(i, "done"), discord.ButtonStyle.success)
                    async def drop(interaction):
                        view=DropChoreView(self.owner,self.selected[0],self.expected)
                        await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                    async def give(interaction):
                        view=ReassignView(self.owner,qid=self.selected[0],scope=owned_scope(self.selected[0])[1],expected=reassign_snapshot(self.selected[0]))
                        await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                    async def trade(interaction):
                        if snapshot(self.selected[0])!=self.expected:
                            await interaction.response.send_message('This chore changed. Reopen My chores first.',ephemeral=True)
                            return
                        view=TradeOfferView(self.owner,self.selected[0])
                        await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                    self.add_button('Drop',drop)
                    self.add_button('Reassign',give)
                    self.add_button('Trade',trade,row=1)
                    if self.selected[2] in ('weekly',*WEEKDAYS):
                        async def choose_day(interaction):
                            view=ChooseDayView(self.owner,self.selected[0],self.expected)
                            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                        self.add_button('Change regular day',choose_day,row=2)

            if self.selected:
                async def review(interaction):
                    view=FeedbackView(self.owner,self.selected[0])
                    await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                self.add_button('Chore review',review,row=2)
            if self.page:
                self.add_button("Previous", lambda i: self.show(i, page=self.page - 1), row=4)
            if (self.page + 1) * PAGE_SIZE < len(self.entries):
                self.add_button("Next", lambda i: self.show(i, page=self.page + 1), row=4)
            self.add_button("Refresh", lambda i: self.show(i), row=4)
            if mode=='mine':
                count=db.execute("SELECT count(*) FROM chore_trades WHERE status='pending' AND (proposer=? OR recipient=?)",(str(owner),str(owner))).fetchone()[0]
                async def requests(interaction):
                    view=TradeInboxView(self.owner)
                    await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                self.add_button(f'Trade requests ({count})',requests,row=2)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77


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
            started=monotonic()
            view = PersonalView(self.owner, mode or self.mode, self.page if page is None else page, selected, notice)
            import logging
            logger=logging.getLogger('discord.sprig')
            logger.info('Chore list rendered in %.3fs; sending Discord response',monotonic()-started)
            await interaction.response.edit_message(embed=view.embed, view=view)
            logger.info('Chore list navigation completed in %.3fs',monotonic()-started)

        async def act(self, interaction, action):
            started=monotonic()
            async def change():
                async with lock:
                    api.reset_due_quests()
                    if not available(self.owner):
                        notice = "You're away today. Open Weekly sign-ups to plan your next home week."
                    elif snapshot(self.selected[0]) != self.expected:
                        notice = "This chore changed since you opened it. The list has been refreshed."
                    else:
                        context = Context(interaction)
                        await bot.get_command(action).callback(context, self.selected[0])
                        notice = "\n".join(context.messages)
                        if action=='claim' and db.execute('SELECT user_id FROM claims WHERE quest_id=?',(self.selected[0],)).fetchone()==(str(self.owner),):
                            notice='Added to My chores: **'+discord.utils.escape_markdown(self.selected[1])+'**.'
                        elif action=='done' and db.execute('SELECT completed FROM quests WHERE id=?',(self.selected[0],)).fetchone()==(1,):
                            notice='Done: **'+discord.utils.escape_markdown(self.selected[1])+'** · +'+str(self.selected[3])+' points.'
                    view = PersonalView(self.owner, "mine" if action == "claim" else self.mode, notice=notice)
                return view
            # Fast local mutations need one Discord response, not defer + edit.
            task=asyncio.create_task(change())
            finished,_=await asyncio.wait({task},timeout=ACTION_ACK_SECONDS)
            deferred=not finished
            if deferred:
                await interaction.response.defer()
            view=await task
            payload=dict(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            if deferred:
                await interaction.edit_original_response(**payload)
            else:
                await interaction.response.edit_message(**payload)
            import logging
            logging.getLogger('discord.sprig').info('Chore action %s completed in %.3fs (deferred=%s)',action,monotonic()-started,deferred)

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
            dated=namespace['chore_ui'].dated
            if db.execute("SELECT 1 FROM dated_occurrences WHERE quest_id=? AND day>=? AND day<=? AND state!='released'",(qid,start.date().isoformat(),end.date().isoformat())).fetchone():
                for n in range((end.date()-start.date()).days+1):
                    day=start.date()+timedelta(days=n)
                    for slot in dated.slots(qid):
                        when=dated.when(day,slot)
                        if not start<=when<end or not dated.valid(qid,day,slot) or dated.skipped(qid,when):continue
                        active=dated.owner(qid,when) or dated.base_owner(qid,when)
                        result.append((active,qid,name+' · '+day.strftime('%a %b %d')+' · '+('All day' if slot=='day' else slot.upper()),frequency,'Dated occurrence','Scheduled'))
                continue
            repeating=namespace['chore_ui'].repeating
            if repeating.slots(qid) and not assigned and not weekly_owner(qid,offset):
                for when in repeating.occurrences(qid,start,end):
                    saved=repeating.reserved(qid,when)
                    if not saved:continue
                    active=repeating.owner(qid,when)
                    shift='Whole day' if repeating.shifts(qid)==('day',) else 'AM' if when.hour<12 else 'PM'
                    result.append((active,qid,name+' · '+when.strftime('%a')+' '+shift,frequency,'Repeating · only when home',
                        'Scheduled' if active else 'Away · needs coverage'))
                continue
            owner=assigned or weekly_owner(qid,offset) or (claim if offset==0 else None)
            kind='Assigned' if assigned else ('Weekly sign-up' if weekly_owner(qid,offset) else ('Single claim' if claim and offset==0 else 'Nobody signed up'))
            status=('Done for this occurrence' if completed else ('Due now' if timing.ready(qid) else 'Upcoming')) if offset==0 else 'Scheduled / outstanding next week'
            result.append((str(owner) if owner else None,qid,name,frequency,kind,status))
        return result

    member_names={}
    name_lookups=asyncio.Semaphore(3)

    async def responsibility_view(owner,guild,offset=0,page=0,mode="person"):
        context=SimpleNamespace(guild=guild)
        async def resolve(uid):
            key=(getattr(guild,'id',None),uid)
            member=guild.get_member(int(uid))
            if member:
                return uid,member.display_name
            cached=member_names.get(key)
            if cached and monotonic()-cached[0]<300:
                return uid,cached[1]
            async with name_lookups:
                name=await namespace['get_member_name'](context,uid)
            if name and not name.startswith('Unknown user ('):
                member_names[key]=(monotonic(),name)
            return uid,name
        names=dict(await asyncio.gather(*(resolve(uid) for uid in {r[0] for r in responsibility_rows(offset) if r[0]})))
        return ResponsibilityView(owner,guild,offset,page,names,mode)

    class ResponsibilityView(SafeView):
        def __init__(self,owner,guild,offset=0,page=0,names=None,mode="person"):
            super().__init__(timeout=600)
            self.owner,self.guild,self.offset=owner,guild,offset
            self.mode=mode if mode in ("person","chore","day") else "person"
            mode=self.mode
            def display(uid):
                member=guild.get_member(int(uid)) if uid else None
                return discord.utils.escape_markdown((names or {}).get(uid) or (member.display_name if member else (f'Account {uid}' if uid else 'Nobody signed up')))[:100]
            entries=sorted(responsibility_rows(offset),key=lambda r:(r[0] is None,display(r[0]).casefold(),r[2].casefold(),r[1]))
            self.entries=entries
            start,end=week_start(offset),week_start(offset+1)
            rendered=[]
            if mode=='day':
                for entry in entries:
                    frequency=entry[3]
                    if frequency in ('daily','twice-daily','daily-am','daily-pm'):
                        rendered.append((-2,'Every day',entry))
                    elif not timing.in_week(frequency,start):
                        rendered.append((-1,'Overdue from an earlier week',entry))
                    elif frequency in WEEKDAYS or frequency.startswith('days:') or ':' in frequency:
                        days=frequency[5:].split(',') if frequency.startswith('days:') else [frequency.split(':')[-1]]
                        for day in days:
                            day_index=WEEKDAYS.index(day)
                            date=start+timedelta(days=day_index+1)
                            rendered.append((day_index,f'{day_badge(day)} · {date:%b %d}',entry))
                    else:
                        title={'weekly':'🤍 Any day this week','monthly':'🟫 Monthly · still open','one-time':'No fixed day'}.get(frequency,'Flexible schedule')
                        rendered.append((7,title,entry))
                rendered.sort(key=lambda item:(item[0],item[1],item[2][2].casefold(),item[2][1]))
            elif mode=='chore':
                rendered=[(0,'Chores · A–Z',entry) for entry in sorted(entries,key=lambda r:(r[2].casefold(),r[1]))]
            else:
                rendered=[(0,(display(entry[0])+(' · '+week_status(entry[0],offset) if week_status(entry[0],offset)!='home' else '')) if entry[0] else 'Needs someone',entry) for entry in entries]
            self.rendered=rendered
            self.page=min(max(page,0),max((len(rendered)-1)//12,0))
            missing=sum(r[0] is None for r in entries)
            self.embed=discord.Embed(title={"person":"Who’s doing what?","chore":"What’s being done by whom?","day":"The week by day"}[mode],description=f"**{'This week' if offset==0 else 'Next week'} · {start:%b %d} → {end:%b %d}**\n{len(entries)-missing} assigned · **{missing} need someone**\nWeeks change Sunday, 6 p.m. Eastern. Includes still-open monthly/one-time chores.\n{DAY_LEGEND}",color=0x6B9B77)
            def schedule(frequency):
                if frequency in WEEKDAYS:
                    return day_badge(frequency)
                if frequency.startswith('days:'):
                    return ' / '.join(day_badge(day) for day in frequency[5:].split(','))
                if ':' in frequency:
                    phase,day=frequency.split(':')
                    return f'Every other {day_badge(day)} ({phase})'
                return {'twice-daily':'AM + PM','daily':'Daily','weekly':'🤍 Weekly','monthly':'🟫 Monthly','one-time':'One time'}.get(frequency,frequency)
            heading=None
            lines=[]
            def flush():
                if lines:
                    self.embed.add_field(name=heading,value='\n'.join(lines),inline=False)
            for _,title,entry in rendered[self.page*12:(self.page+1)*12]:
                uid,qid,name,frequency,kind,status=entry
                tags=([display(uid) if uid else 'Needs someone'] if mode!='person' else [])+[schedule(frequency)]
                if kind=='Single claim':
                    tags.append('one occurrence')
                elif kind=='Assigned':
                    tags.append('ongoing')
                if status=='Done for this occurrence':
                    tags.append('done this slot' if frequency=='twice-daily' else 'done')
                warning=coverage_warning(qid,uid,offset) if uid else ''
                line=f"• **{discord.utils.escape_markdown(name)[:150]}** — {' · '.join(tags)}"+('\n⚠ '+(warning if len(warning)<=110 else warning[:100]+'… · see Who’s home?') if warning else '')
                if title!=heading or len('\n'.join(lines+[line]))>950:
                    flush()
                    heading=title
                    lines=[]
                lines.append(line)
            flush()
            if not rendered:
                self.embed.add_field(name='All clear',value='No chores scheduled or outstanding for this week.',inline=False)
            self.embed.set_footer(text=f'Page {self.page+1} of {max((len(rendered)-1)//12+1,1)} · Single claims apply only to this week · Refresh for changes')
            self.button('This week',lambda i:self.show(i,offset=0,page=0))
            self.button('Next week',lambda i:self.show(i,offset=1,page=0))
            self.button('Refresh',lambda i:self.show(i))
            for label,value in [('By person','person'),('By chore','chore'),('By day','day')]:
                async def switch(interaction,value=value):
                    await self.show(interaction,page=0,mode=value)
                self.button(label,switch,row=1,style=discord.ButtonStyle.primary if value==mode else discord.ButtonStyle.secondary)

            if self.page:
                self.button('Previous',lambda i:self.show(i,page=self.page-1),row=2)
            if (self.page+1)*12<len(rendered):
                self.button('Next page',lambda i:self.show(i,page=self.page+1),row=2)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        def button(self,label,callback,row=0,style=discord.ButtonStyle.secondary):
            item=discord.ui.Button(label=label,row=row,style=style)
            item.callback=callback
            self.add_item(item)

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own Who’s doing what? view from the household panel.',ephemeral=True)
                return False
            return True

        async def show(self,interaction,offset=None,page=None,mode=None):
            await interaction.response.defer()
            view=await responsibility_view(self.owner,interaction.guild,self.offset if offset is None else offset,self.page if page is None else page,self.mode if mode is None else mode)
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
            self.expected = reassign_snapshot(selected) if self.selected else None
            start = week_start(offset)
            end = start + timedelta(weeks=1)
            status = {"home":"Home this week","away":"Away this week — choose a home week","partial":"Partly home this week — check coverage before reserving daily chores"}[week_status(owner,offset)]
            self.embed = discord.Embed(title="🌱 Weekly sign-ups", description=f"{start:%b %d} at 6 p.m. → {end:%b %d} at 6 p.m.\n{status}\n{notice or 'Reserve a recurring chore for this week or next week.'}\n{DAY_LEGEND}")
            self.embed.add_field(name='Availability',value=('Home throughout this household week.' if week_status(owner,offset)=='home' else ('Away throughout this household week.' if week_status(owner,offset)=='away' else '\n'.join(f'{day_badge(WEEKDAYS[when.weekday()])} {when:%b %d}: '+('Home' if home else 'Away')+(' after 6 p.m.' if index==0 else (' before 6 p.m.' if index==7 else '')) for index,(when,home) in enumerate(attendance.week(owner,week_start(offset)))))),inline=False)
            if not db.execute("SELECT 1 FROM alternating_members LIMIT 1").fetchone():
                self.embed.add_field(name="Household setup needed", value="An administrator still needs to select Kas and Z in Household setup so their away weeks can be enforced.", inline=False)
            if self.selected:
                r = self.selected
                state = "You're signed up" if weekly_owner(r[0], offset) == str(owner) else "Open for the week"
                self.embed.add_field(name=r[1][:256], value=f"{timing.label(r[2],r[0])} · {state}\n{(r[7] or '')[:700]}", inline=False)
            elif not chunk:
                self.embed.add_field(name="No chores available", value="Preassigned and one-time chores aren't part of weekly sign-ups.")
            if chunk:
                select = discord.ui.Select(placeholder="Choose a chore for the week…", options=[chore_option(r[0],r[1],"Your weekly responsibility" if weekly_owner(r[0], offset) == str(owner) else "Open for the week",selected=bool(self.selected and r[0]==self.selected[0])) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            if self.selected:
                async def review(interaction):
                    view=FeedbackView(owner,self.selected[0])
                    await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                self.button('Chore review',review,row=2)
            self.button("This week", lambda i: self.show(i, offset=0, page=0))
            self.button("Next week", lambda i: self.show(i, offset=1, page=0))
            if self.selected:
                mine = weekly_owner(self.selected[0], offset) == str(owner)
                if mine or can_take_week(owner,r[0],offset):
                    self.button("Release week" if mine else "Sign up for week", lambda i: self.act(i, mine), discord.ButtonStyle.secondary if mine else discord.ButtonStyle.success)
            if self.page:
                self.button("Previous", lambda i: self.show(i, page=self.page - 1), row=2)
            if (self.page + 1) * PAGE_SIZE < len(entries):
                self.button("Next", lambda i: self.show(i, page=self.page + 1), row=2)
            self.button("Refresh", lambda i: self.show(i), row=2)
            self.embed.set_footer(text=f"Page {self.page + 1} · 🩷 Sun 6 p.m. handoff · Daily completion does not release your week · Reopen /chores after 10 minutes or a restart.")
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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
                api.reset_due_quests()
                # Do not silently apply a click to a different week after Sunday.
                if week_key(self.offset) != self.key:
                    notice = "The week changed. Review the new dates before signing up."
                elif not self.selected or reassign_snapshot(self.selected[0]) != self.expected:
                    notice = "This chore changed. Review the refreshed weekly list before changing responsibility."
                elif release:
                    with db:
                        db.execute("DELETE FROM week_signups WHERE quest_id = ? AND week_start = ? AND user_id = ?", (self.selected[0], self.key, str(self.owner)))
                    notice = "Weekly sign-up released. Completed work and points are unchanged."
                else:
                    notice = signup(self.owner, self.selected[0], self.key)
                view = WeeklyView(self.owner, self.offset, notice=notice)
            await interaction.edit_original_response(embed=view.embed, view=view)

    def reassign_snapshot(qid):
        base=(snapshot(qid),week_key(1),weekly_owner(qid,1),db.execute('SELECT id,active FROM availability_exceptions ORDER BY id').fetchall())
        defaults=db.execute('SELECT user_id,mode,weekdays,revision FROM availability_defaults ORDER BY user_id').fetchall()
        return base+(defaults,) if defaults else base

    def reassign(qid,target,scope,expected,actor=None):
        api.reset_due_quests()
        if reassign_snapshot(qid)!=expected or is_archived(qid):
            return 'This chore or week changed. Reopen Reassign and review it again.'
        row=db.execute('SELECT frequency,assigned_to,completed FROM quests WHERE id=?',(qid,)).fetchone()
        if not row or scope not in ('occurrence','week0','week1','assignment'):
            return 'Choose a valid chore and assignment scope.'
        if scope in ('week0','week1','assignment') and namespace['chore_ui'].repeating.slots(qid):
            return 'Release repeating days before assigning a whole week or ongoing responsibility.'
        offset=1 if scope=='week1' else 0
        if (scope.startswith('week') and not can_take_week(target,qid,offset)) or (scope=='occurrence' and not available(target)):
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
        if namespace['chore_ui'].dated.owner(qid):
            if row[2] or not timing.ready(qid):return 'There is no open dated occurrence to reassign.'
            with db:
                namespace['chore_ui'].dated.transfer_current(actor if actor is not None else 'system',qid,str(target))
                db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            return 'This dated occurrence reassigned. Later repeats and points stay saved.'
        if row[1] or weekly_owner(qid):
            return 'This chore has an ongoing assignment or weekly owner. Choose that scope instead.'
        if row[2] or not timing.ready(qid):
            return 'There is no open occurrence to reassign. Choose a weekly or ongoing assignment instead.'
        with db:
            db.execute('INSERT OR REPLACE INTO claims VALUES(?,?)',(qid,str(target)))
        return 'This occurrence reassigned. Completed work and earned points are unchanged.'

    class ReassignView(SafeView):
        def __init__(self,owner,page=0,qid=None,scope=None,target=None,expected=None,return_context=None):
            super().__init__(timeout=600)
            self.owner,self.qid,self.scope,self.target=owner,qid,scope,target
            self.return_context=return_context
            if return_context is not None:self.recovery_context={'screen':'reassign','parent':return_context}
            entries=[r for r in db.execute('SELECT id,name FROM quests ORDER BY name COLLATE NOCASE,id') if not is_archived(r[0])]
            self.page=min(max(page,0),max((len(entries)-1)//PAGE_SIZE,0))
            self.expected=expected
            self.embed=discord.Embed(title='Reassign a chore',description='Choose a chore, how long the responsibility lasts, and a person. Then review and confirm. Everyone in the household can do this. Chore names, history, and earned points stay saved.')
            chunk=entries[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
            if chunk:
                picker=discord.ui.Select(placeholder='Choose a chore',row=0,options=[chore_option(key,name,selected=key==qid) for key,name in chunk])
                async def choose_chore(interaction):
                    chosen=int(picker.values[0])
                    await self.show(interaction,qid=chosen,scope=None,target=None,expected=reassign_snapshot(chosen))
                picker.callback=choose_chore
                self.add_item(picker)
            if qid is not None:
                row=db.execute('SELECT name,assigned_to,frequency FROM quests WHERE id=?',(qid,)).fetchone()
                if row:
                    self.embed.add_field(name='Chore',value=discord.utils.escape_markdown(row[0])+'\n'+timing.label(row[2],qid),inline=False)
                scopes=[]
                current_scope=owned_scope(qid)[1]
                if not row[1] and not weekly_owner(qid) and not db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()[0] and timing.ready(qid):
                    scopes.append(('Just this time','occurrence'))
                if not row[1] and row[2] in WEEKLY_FREQUENCIES:
                    for value,offset in [('week0',0),('week1',1)]:
                        if timing.in_week(row[2],week_start(offset)) or (offset==0 and timing.ready(qid)):
                            scopes.append(('This week' if offset==0 else 'Next week',value))
                if not db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,week_key())).fetchone():
                    scopes.append(('Every week · ongoing','assignment'))
                if scope not in [value for label,value in scopes]: scope=None
                choose_scope=discord.ui.Select(placeholder='For how long?',row=1,options=[discord.SelectOption(label=label,value=value,default=value==scope) for label,value in scopes])
                async def set_scope(interaction):
                    await self.show(interaction,scope=choose_scope.values[0],target=None)
                choose_scope.callback=set_scope
                self.add_item(choose_scope)
                if scope:
                    label=dict((value,label) for label,value in scopes)[scope]
                    if scope.startswith('week'):
                        offset=int(scope[-1])
                        label+=f' ({week_start(offset):%b %d} → {week_start(offset+1):%b %d}, 🩷 Sun 6 p.m. Eastern)'
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
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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
            values=dict(page=self.page,qid=self.qid,scope=self.scope,target=self.target,expected=self.expected,return_context=self.return_context)
            values.update(changes)
            view=ReassignView(self.owner,**values)
            await interaction.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())

        async def cancel(self,interaction):
            if not await self.interaction_check(interaction):return
            if self.return_context is not None:
                return await workspace.present(interaction,workspace.recovery.restore(self.owner,self.return_context,interaction.guild),'Reassignment canceled. Nothing changed.')
            await interaction.response.edit_message(content='Reassignment canceled. Nothing changed.',embed=None,view=ReturnView(interaction.user.id))

        async def confirm(self,interaction):
            if not await self.interaction_check(interaction):return
            if not self.target or self.target.bot or getattr(getattr(self.target,'guild',None),'id',None)!=interaction.guild_id:
                await interaction.response.send_message('Choose a household member first.',ephemeral=True)
                return
            await interaction.response.defer()
            async with lock:
                notice=reassign(self.qid,self.target.id,self.scope,self.expected,actor=interaction.user.id)
            if self.return_context is not None:
                return await workspace.present(interaction,workspace.recovery.restore(self.owner,self.return_context,interaction.guild),notice)
            await interaction.edit_original_response(content=notice,embed=None,view=ReturnView(interaction.user.id),allowed_mentions=discord.AllowedMentions.none())

    def owned_scope(qid):
        row=db.execute('SELECT assigned_to FROM quests WHERE id=?',(qid,)).fetchone()
        if not row or is_archived(qid):
            return None,None
        if namespace['chore_ui'].dated.owner(qid):
            return namespace['chore_ui'].dated.owner(qid),'dated'
        if row[0]:
            return row[0],'assignment'
        recurring=namespace['chore_ui'].repeating.owner(qid)
        owner=weekly_owner(qid)
        if owner:
            return owner,'week0'
        row=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone()
        return (row[0],'occurrence') if row else ((recurring,'repeating') if recurring else (None,None))

    def drop_chore(owner,qid,expected):
        api.reset_due_quests()
        if snapshot(qid)!=expected:
            return 'This chore changed. Reopen My chores before dropping it.'
        current,scope=owned_scope(qid)
        if current!=str(owner):
            return 'This chore is no longer yours. Nothing changed.'
        if scope=='dated':
            with db:namespace['chore_ui'].dated.transfer_current(owner,qid,None)
            return 'Dated claim released. Later repeats and points stay saved.'
        if scope=='repeating':return 'Use Sign-up schedule → Release selected days to release repeating responsibility, or Skip this occurrence for just today.'
        with db:
            if scope=='assignment':
                db.execute('UPDATE quests SET assigned_to=NULL WHERE id=?',(qid,))
            elif scope=='week0':
                db.execute('DELETE FROM week_signups WHERE quest_id=? AND week_start=? AND user_id=?',(qid,week_key(),str(owner)))
            db.execute('DELETE FROM claims WHERE quest_id=? AND user_id=?',(qid,str(owner)))
        return 'Dropped. It is available for someone else; completed work, history, and earned points stay saved.'

    class DropChoreView(SafeView):
        def __init__(self,owner,qid,expected):
            super().__init__(timeout=600)
            self.owner=owner
            name=db.execute('SELECT name FROM quests WHERE id=?',(qid,)).fetchone()[0]
            scope=owned_scope(qid)[1]
            label={'week0':'your whole responsibility for this week (future weeks stay unchanged)','assignment':'the ongoing assignment, including future occurrences','occurrence':'this occurrence only'}.get(scope,'this responsibility')
            self.embed=discord.Embed(title='Drop chore?',description=f'**{discord.utils.escape_markdown(name)}**\nThis releases {label}. History and earned points remain.')
            for label,save in [('Confirm drop',True),('Cancel',False)]:
                button=discord.ui.Button(label=label)
                async def choose(interaction,save=save):
                    if not await self.interaction_check(interaction):return
                    async with lock:
                        result=drop_chore(owner,qid,expected) if save else 'Canceled. Nothing changed.'
                    if save and result.startswith('Dropped.'):
                        await workspace.present(interaction,workspace.Chores(owner,guild=interaction.guild),notice='Dropped · '+name)
                    else:
                        await interaction.response.edit_message(content=result,embed=None,view=ReturnView(interaction.user.id))
                button.callback=choose
                self.add_item(button)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own My chores to drop a responsibility.',ephemeral=True)
                return False
            return True

    def trade_snapshot(qid):
        return json.dumps(reassign_snapshot(qid),sort_keys=True)

    def propose_trade(owner,offered,requested,expected_offer,expected_request):
        api.reset_due_quests()
        giver,scope=owned_scope(offered)
        recipient,other_scope=owned_scope(requested)
        if giver!=str(owner) or not recipient or recipient==str(owner) or offered==requested:
            return 'Choose your chore and a chore owned by someone else.'
        if scope=='repeating' and not timing.ready(offered) or other_scope=='repeating' and not timing.ready(requested):
            return 'Wait until both occurrences are due to trade repeating responsibilities for just this time.'
        if trade_snapshot(offered)!=expected_offer or trade_snapshot(requested)!=expected_request:
            return 'A chore or week changed. Review the trade again.'
        if not available(owner) or not available(recipient):
            return 'Both people must be home this week to trade.'
        if db.execute("SELECT 1 FROM chore_trades WHERE proposer=? AND offered=? AND requested=? AND status='pending'",(str(owner),offered,requested)).fetchone():
            return 'That proposal is already waiting in Trade requests. Nothing duplicated.'
        with db:
            db.execute('INSERT INTO chore_trades(proposer,recipient,offered,requested,offered_scope,requested_scope,offered_snapshot,requested_snapshot) VALUES(?,?,?,?,?,?,?,?)',(str(owner),recipient,offered,requested,scope,other_scope,expected_offer,expected_request))
        return 'Trade proposed. Nothing changes until the other person accepts in Dashboard → Trades. Private notifications follow their preference.'

    def respond_trade(owner,trade_id,action):
        api.reset_due_quests()
        row=db.execute('SELECT proposer,recipient,offered,requested,offered_scope,requested_scope,offered_snapshot,requested_snapshot,status FROM chore_trades WHERE id=?',(trade_id,)).fetchone()
        if not row or row[8]!='pending':
            return 'This proposal is no longer pending.'
        giver,recipient,offered,requested,scope,other_scope,expected,other_expected,_=row
        if (action in ('accept','decline') and str(owner)!=recipient) or (action=='cancel' and str(owner)!=giver) or action not in ('accept','decline','cancel'):
            return 'Only the recipient can accept/decline; only the proposer can cancel.'
        if action!='accept':
            with db:
                db.execute('UPDATE chore_trades SET status=? WHERE id=?',('declined' if action=='decline' else 'canceled',trade_id))
            return 'Trade '+('declined' if action=='decline' else 'canceled')+'. Chores are unchanged.'
        if trade_snapshot(offered)!=expected or trade_snapshot(requested)!=other_expected or owned_scope(offered)!=(giver,scope) or owned_scope(requested)!=(recipient,other_scope) or not available(giver) or not available(recipient):
            with db:
                db.execute("UPDATE chore_trades SET status='expired' WHERE id=?",(trade_id,))
            return 'A chore, availability, or week changed. Trade expired; propose a fresh one.'
        for qid,kind in [(offered,scope),(requested,other_scope)]:
            completed=db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()[0]
            if kind in ('occurrence','repeating','dated') and (completed or not timing.ready(qid)):
                return 'An occurrence is no longer open. Nothing exchanged.'
            if kind=='assignment' and db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,week_key())).fetchone():
                return 'An ongoing assignment has weekly reservations. Resolve those before trading.'
        with db:
            for qid,new_owner,kind in [(offered,recipient,scope),(requested,giver,other_scope)]:
                if kind=='assignment':
                    db.execute('UPDATE quests SET assigned_to=? WHERE id=?',(new_owner,qid))
                    db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
                elif kind=='week0':
                    db.execute('UPDATE week_signups SET user_id=? WHERE quest_id=? AND week_start=?',(new_owner,qid,week_key()))
                    db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
                elif kind=='dated':
                    namespace['chore_ui'].dated.transfer_current(owner,qid,new_owner)
                    db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
                elif kind=='repeating':
                    db.execute('INSERT OR REPLACE INTO claims(quest_id,user_id) VALUES(?,?)',(qid,new_owner))
                else:
                    db.execute('UPDATE claims SET user_id=? WHERE quest_id=?',(new_owner,qid))
            db.execute("UPDATE chore_trades SET status='accepted' WHERE id=?",(trade_id,))
        return 'Trade accepted. Both responsibilities exchanged together; history and earned points are unchanged.'

    class TradeOfferView(SafeView):
        def __init__(self,owner,offered,page=0,requested=None,expected_offer=None):
            super().__init__(timeout=600)
            self.owner,self.offered=owner,offered
            expected_offer=expected_offer or trade_snapshot(offered)
            entries=[(qid,name) for qid,name in db.execute('SELECT id,name FROM quests ORDER BY name COLLATE NOCASE,id') if owned_scope(qid)[0] not in (None,str(owner))]
            page=min(max(page,0),max((len(entries)-1)//PAGE_SIZE,0))
            name=db.execute('SELECT name FROM quests WHERE id=?',(offered,)).fetchone()[0]
            descriptions={'occurrence':'this occurrence','week0':'this whole week','assignment':'ongoing assignment','repeating':'this occurrence only; repeating signup stays saved','dated':'this dated occurrence only'}
            self.embed=discord.Embed(title='Propose a trade',description=f'You offer **{discord.utils.escape_markdown(name)}** ({descriptions.get(owned_scope(offered)[1],"ownership changed")}). Choose another person’s chore. They must accept in Trade requests.')
            chunk=entries[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
            if chunk:
                picker=discord.ui.Select(placeholder='Which chore would you take?',options=[chore_option(qid,name,selected=qid==requested) for qid,name in chunk])
                async def choose(interaction):
                    view=TradeOfferView(owner,offered,page,int(picker.values[0]),expected_offer)
                    await interaction.response.edit_message(embed=view.embed,view=view)
                picker.callback=choose
                self.add_item(picker)
            else:
                self.embed.add_field(name='No available trades',value='Someone else needs to claim or sign up for a chore first.')
            if requested:
                recipient,scope=owned_scope(requested)
                other=db.execute('SELECT name,frequency FROM quests WHERE id=?',(requested,)).fetchone()
                self.embed.add_field(name='You receive',value=f'**{discord.utils.escape_markdown(other[0])}** · {descriptions.get(scope,"ownership changed")}\n{timing.label(other[1],requested)}\nFrom <@{recipient}>; the name/instructions stay unchanged.',inline=False)
                expected_request=trade_snapshot(requested)
                async def propose(interaction):
                    async with lock:
                        result=propose_trade(owner,offered,requested,expected_offer,expected_request)
                        trade_id=db.execute('SELECT MAX(id) FROM chore_trades WHERE proposer=?',(str(owner),)).fetchone()[0] if result.startswith('Trade proposed') else None
                    await interaction.response.edit_message(content=result,embed=None,view=ReturnView(interaction.user.id),allowed_mentions=discord.AllowedMentions.none())
                    if result.startswith('Trade proposed'):
                        await workspace.notify_trade(trade_id)
                self.button('Propose trade',propose)
            if page:
                async def previous(interaction):
                    view=TradeOfferView(owner,offered,page-1,expected_offer=expected_offer)
                    await interaction.response.edit_message(embed=view.embed,view=view)
                self.button('Previous',previous)
            if (page+1)*PAGE_SIZE<len(entries):
                async def following(interaction):
                    view=TradeOfferView(owner,offered,page+1,expected_offer=expected_offer)
                    await interaction.response.edit_message(embed=view.embed,view=view)
                self.button('Next',following)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        def button(self,label,callback):
            item=discord.ui.Button(label=label,row=1)
            item.callback=callback
            self.add_item(item)

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own trade proposal from My chores.',ephemeral=True)
                return False
            return True

    class TradeInboxView(TradeOfferView):
        def __init__(self,owner,page=0,selected=None):
            SafeView.__init__(self,timeout=600)
            self.owner=owner
            entries=db.execute("SELECT id,proposer,recipient,offered,requested FROM chore_trades WHERE status='pending' AND (proposer=? OR recipient=?) ORDER BY id DESC",(str(owner),str(owner))).fetchall()
            page=min(max(page,0),max((len(entries)-1)//PAGE_SIZE,0))
            chunk=entries[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
            self.embed=discord.Embed(title='Trade requests',description='Incoming: accept or decline. Outgoing: cancel. Until acceptance, both chores stay with their current owners.')
            chosen=next((r for r in chunk if r[0]==selected),None)
            def name(qid):
                row=db.execute('SELECT name FROM quests WHERE id=?',(qid,)).fetchone()
                return row[0] if row else 'Archived chore'
            if chunk:
                picker=discord.ui.Select(placeholder='Choose a proposal',options=[discord.SelectOption(label=(f'#{r[0]} '+('Incoming: ' if r[2]==str(owner) else 'Outgoing: ')+name(r[3]))[:100],value=str(r[0])) for r in chunk])
                async def choose(interaction):
                    view=TradeInboxView(owner,page,int(picker.values[0]))
                    await interaction.response.edit_message(embed=view.embed,view=view)
                picker.callback=choose
                self.add_item(picker)
            else:
                self.embed.add_field(name='No pending trades',value='Propose one from a selected chore in My chores.')
            if chosen:
                scopes=db.execute('SELECT offered_scope,requested_scope FROM chore_trades WHERE id=?',(selected,)).fetchone()
                scopes=tuple({'week0':'whole week · this week','assignment':'ongoing assignment','occurrence':'this occurrence'}.get(value,value) for value in scopes)
                self.embed.add_field(name='Exchange',value=f'<@{chosen[1]}> offers **{discord.utils.escape_markdown(name(chosen[3]))}** ({scopes[0]})\n<@{chosen[2]}> gives **{discord.utils.escape_markdown(name(chosen[4]))}** ({scopes[1]})',inline=False)
                for label,action in ([('Accept trade','accept'),('Decline','decline')] if chosen[2]==str(owner) else [('Cancel proposal','cancel')]):
                    async def respond(interaction,action=action):
                        async with lock:
                            result=respond_trade(owner,selected,action)
                        await interaction.response.edit_message(content=result,embed=None,view=ReturnView(interaction.user.id),allowed_mentions=discord.AllowedMentions.none())
                    self.button(label,respond)
            for label,new_page in [('Previous',page-1),('Next',page+1)]:
                if (label=='Previous' and page>0) or (label=='Next' and (page+1)*PAGE_SIZE<len(entries)):
                    async def navigate(interaction,new_page=new_page):
                        view=TradeInboxView(owner,new_page)
                        await interaction.response.edit_message(embed=view.embed,view=view)
                    self.button(label,navigate)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

    class AttendanceModal(discord.ui.Modal):
        def __init__(self,owner,member_id,member_name,state):
            super().__init__(title='Mark '+member_name[:20]+' '+state,timeout=600)
            self.owner,self.member_id,self.state=owner,member_id,state
            self.start=discord.ui.TextInput(label='First full day (YYYY-MM-DD)',placeholder='2026-10-24',max_length=10)
            self.end=discord.ui.TextInput(label='Last full day, included (YYYY-MM-DD)',placeholder='2026-10-26',max_length=10)
            self.note=discord.ui.TextInput(label='Reason (optional)',placeholder='Trip or traded days',required=False,max_length=300)
            for item in [self.start,self.end,self.note]:
                self.add_item(item)

        async def on_submit(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Who’s home? form.',ephemeral=True)
                return
            async with lock:
                result=attendance.add(self.member_id,self.start.value,self.end.value,self.state,self.note.value)
                warnings=[]
                if result.startswith('Saved'):
                    for offset in (0,1):
                        ids={qid for qid, in db.execute('SELECT quest_id FROM week_signups WHERE user_id=? AND week_start=?',(str(self.member_id),week_key(offset)))}
                        ids.update(qid for qid, in db.execute('SELECT id FROM quests WHERE assigned_to=?',(str(self.member_id),)))
                        ids.update(qid for qid, in db.execute('SELECT quest_id FROM claims WHERE user_id=?',(str(self.member_id),)))
                        for qid in ids:
                            if not is_archived(qid) and coverage_warning(qid,self.member_id,offset):
                                name=db.execute('SELECT name FROM quests WHERE id=?',(qid,)).fetchone()[0]
                                warnings.append(('This week: ' if offset==0 else 'Next week: ')+name)
            text=result
            if warnings:
                text+='\n⚠ Responsibilities to review (kept, not removed):\n'+'\n'.join(discord.utils.escape_markdown(value) for value in warnings[:10])
                if len(warnings)>10:
                    text+=f'\n…and {len(warnings)-10} more. Open the overview to review coverage.'
            await interaction.response.send_message(text,view=ReturnView(interaction.user.id),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    class AttendanceView(SafeView):
        def __init__(self,owner,member_id=None,member_name='',offset=0,page=0,selected=None):
            super().__init__(timeout=600)
            self.owner=owner
            self.embed=discord.Embed(title='Who’s home? · trips & traded days',description='Choose a person, then Mark home or Mark away. Dates are full calendar days in Eastern time, including the last date. Exceptions override the normal rotation, then expire automatically. Anyone in this household can edit them. Existing responsibilities are kept and flagged for review.')
            users=discord.ui.UserSelect(placeholder='Whose dates are changing?',min_values=1,max_values=1,row=0)
            async def person(interaction):
                member=users.values[0]
                if member.bot or getattr(getattr(member,'guild',None),'id',None)!=interaction.guild_id:
                    await interaction.response.send_message('Choose a person in this household server, not a bot.',ephemeral=True)
                    return
                await redraw(interaction,member_id=member.id,member_name=member.display_name,page=0,selected=None)
            users.callback=person
            self.add_item(users)
            async def redraw(interaction,**changes):
                values=dict(member_id=member_id,member_name=member_name,offset=offset,page=page,selected=selected)
                values.update(changes)
                view=AttendanceView(owner,**values)
                await interaction.response.edit_message(embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            def button(label,callback,row=1):
                item=discord.ui.Button(label=label,row=row)
                item.callback=callback
                self.add_item(item)
            if member_id is not None:
                start=week_start(offset)
                self.embed.add_field(name=discord.utils.escape_markdown(member_name)+(' · This week' if offset==0 else ' · Next week'),value='\n'.join(f'{day_badge(WEEKDAYS[when.weekday()])} {when:%b %d}: '+('Home' if home else 'Away')+(' after 6 p.m.' if index==0 else (' before 6 p.m.' if index==7 else '')) for index,(when,home) in enumerate(attendance.week(member_id,start))),inline=False)
                for label,state in [('Mark home','home'),('Mark away','away')]:
                    async def mark(interaction,state=state):
                        await interaction.response.send_modal(AttendanceModal(owner,member_id,member_name,state))
                    button(label,mark)
                records=db.execute('SELECT id,start_date,end_date,state,note FROM availability_exceptions WHERE user_id=? AND active=1 ORDER BY start_date,id',(str(member_id),)).fetchall()
                page=min(max(page,0),max((len(records)-1)//PAGE_SIZE,0))
                chunk=records[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
                if chunk:
                    self.embed.add_field(name='Saved exceptions',value='\n'.join(f'#{row[0]} · {row[1]} → {row[2]} · {row[3].capitalize()}' for row in chunk)[:1024],inline=False)
                    picker=discord.ui.Select(placeholder='Choose an exception to cancel',row=2,options=[discord.SelectOption(label=f'{row[1]} → {row[2]} · {row[3].capitalize()}',value=str(row[0])) for row in chunk])
                    async def choose(interaction):
                        await redraw(interaction,selected=int(picker.values[0]))
                    picker.callback=choose
                    self.add_item(picker)
                    chosen=next((row for row in chunk if row[0]==selected),None)
                    if chosen:
                        self.embed.add_field(name='Cancel this exception?',value=f'{chosen[1]} → {chosen[2]} · {chosen[3].capitalize()}\n{discord.utils.escape_markdown(chosen[4])}\nNormal rotation resumes for those dates. Other exceptions remain.',inline=False)
                        async def cancel(interaction):
                            async with lock:
                                current=db.execute('SELECT id,start_date,end_date,state,note FROM availability_exceptions WHERE id=? AND user_id=? AND active=1',(selected,str(member_id))).fetchone()
                                if current!=chosen:
                                    text='This exception changed. Reopen Who’s home? before canceling.'
                                else:
                                    with db:
                                        db.execute('UPDATE availability_exceptions SET active=0 WHERE id=?',(selected,))
                                    text='Exception canceled. Normal rotation applies again; responsibilities and history were kept. Review coverage in the overview.'
                            await interaction.response.edit_message(content=text,embed=None,view=ReturnView(interaction.user.id))
                        button('Confirm cancel exception',cancel,row=3)
                else:
                    self.embed.add_field(name='No saved exceptions',value='The normal rotation applies. Mark home or away to override a date range.')
                button('This week',lambda i:redraw(i,offset=0,selected=None),row=4)
                button('Next week',lambda i:redraw(i,offset=1,selected=None),row=4)
                if page:
                    button('Previous',lambda i:redraw(i,page=page-1,selected=None),row=4)
                if (page+1)*PAGE_SIZE<len(records):
                    button('Next page',lambda i:redraw(i,page=page+1,selected=None),row=4)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Who’s home? view.',ephemeral=True)
                return False
            return True

    class HouseholdSetup(SafeView):
        def __init__(self, owner):
            super().__init__(timeout=600)
            self.owner = owner
            self.members = None
            select = discord.ui.UserSelect(placeholder="Select Kas and Zel's two Discord accounts", min_values=2, max_values=2)
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
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self, interaction):
            if interaction.user.id != self.owner or not allowed(interaction) or not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("Only the administrator who opened setup can save it.", ephemeral=True)
                return False
            return True

        async def save(self, interaction):
            if not self.members:
                await interaction.response.send_message("Select Kas and Zel's two accounts first.", ephemeral=True)
                return
            # No sign-ups may become unusable as a side effect of configuring identity.
            current = {r[0] for r in db.execute("SELECT user_id FROM alternating_members")}
            if current != set(self.members) and db.execute("SELECT 1 FROM week_signups WHERE week_start >= ? LIMIT 1", (week_key(),)).fetchone():
                await interaction.response.send_message("Release current and future weekly sign-ups before changing the alternating-week accounts.", ephemeral=True)
                return
            with db:
                db.execute("DELETE FROM alternating_members")
                db.executemany("INSERT INTO alternating_members VALUES (?)", [(m,) for m in self.members])
            await interaction.response.edit_message(content="Saved. Kas and Zel follow the alternating rotation. Who’s home? can override dates for trips or traded days. Existing responsibilities were kept; review coverage warnings.", view=ReturnView(interaction.user.id))

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
            self.embed = discord.Embed(title='Archived chores' if removed else 'Archive chore', description=notice or 'Choose a chore. Archiving hides it from the board and weekly sign-ups; history and points stay saved. You can restore it here.')
            if self.selected:
                self.embed.add_field(name=self.selected[1][:256], value='Tap Restore to put it back.' if removed else 'Archive this chore from everyone’s board? Existing history is retained; current ownership and completion state are kept for restoration.', inline=False)
            if not self.selected:
                for start in range(0,len(chunk),5):
                    self.embed.add_field(name=('Archived chores' if removed else 'Active chores') if start==0 else 'Continued',value='\n'.join('• '+name[:160] for _,name in chunk[start:start+5]),inline=False)
                if not chunk:self.embed.add_field(name='No archived chores' if removed else 'No active chores',value='There are no chores in this list.')
            if chunk:
                select = discord.ui.Select(placeholder='Choose a chore to restore…' if removed else 'Choose a chore to archive…', options=[chore_option(qid,name,selected=bool(self.selected and qid==self.selected[0])) for qid,name in chunk])
                async def choose(interaction):
                    await self.show(interaction, selected=int(select.values[0]))
                select.callback = choose
                self.add_item(select)
            if self.selected:
                self.button('Restore' if removed else 'Confirm archive', self.act, discord.ButtonStyle.success if removed else discord.ButtonStyle.danger)
            self.button('Active chores' if removed else 'Archived chores', lambda i: self.show(i, removed=not removed, page=0))
            if self.page:
                self.button('Previous', lambda i: self.show(i, page=self.page-1))
            if (self.page+1)*PAGE_SIZE < len(entries):
                self.button('Next', lambda i: self.show(i, page=self.page+1))
            self.embed.set_footer(text=f'Page {self.page+1} · Nobody’s points or completion history are deleted')
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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
                notice='Restored.' if self.removed else 'Archived from the board. Find it under Archived chores if you want to restore it.'
            view=RemoveChoreView(self.owner,self.removed,notice=notice)
            await interaction.response.edit_message(embed=view.embed,view=view)

    def create_chore(name, frequency, points, notes, room=None):
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
            quest_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            timing.initialize(quest_id,frequency)
            if room is not None:
                db.execute('UPDATE quests SET category=? WHERE id=?',(room.strip()[:100] or 'general',quest_id))
        return f"Added **{discord.utils.escape_markdown(name)}**. It is open for sign-up; refresh Open chores to see it."

    class AddChoreModal(discord.ui.Modal):
        def __init__(self, owner, frequency):
            super().__init__(title=("Add "+timing.compact_label(frequency)+" chore")[:45], timeout=600)
            self.owner, self.frequency = owner, frequency
            self.name = discord.ui.TextInput(label="Chore name", placeholder="e.g. Empty dishwasher and put dishes away", max_length=100)
            self.notes = discord.ui.TextInput(label="Instructions / timing (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000, placeholder="What counts as done? Choose weekdays in the schedule picker; notes don't send reminders.")
            self.points = discord.ui.TextInput(label="Points (optional; blank means 5)", required=False, default="5", max_length=7)
            self.room = discord.ui.TextInput(label="Room (optional)",required=False,max_length=100)
            for item in (self.name, self.notes, self.points, self.room):
                self.add_item(item)

        async def on_submit(self, interaction):
            if not can_add(interaction, self.owner):
                await interaction.response.send_message("Use the form you opened from the household panel.", ephemeral=True)
                return
            message = create_chore(self.name.value, self.frequency, self.points.value, self.notes.value, self.room.value)
            await interaction.response.send_message(message,view=ReturnView(interaction.user.id), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

        async def on_error(self, interaction, error):
            if not interaction.response.is_done():
                await interaction.response.send_message("Couldn't confirm the result. Check Open chores before submitting again.", ephemeral=True)

    class AddChoreMenu(SafeView):
        def __init__(self, owner, edit_id=None, expected=None):
            super().__init__(timeout=600)
            self.owner = owner
            select = discord.ui.Select(placeholder="How often does this chore repeat?", options=[
                discord.SelectOption(label="Daily", value="daily", description="Returns at midnight; can be reserved for a week"),
                discord.SelectOption(label="Daily · AM",value="daily-am",description="Separate morning responsibility; returns at midnight"),
                discord.SelectOption(label="Daily · PM",value="daily-pm",description="Separate afternoon/evening responsibility; opens at noon"),
                discord.SelectOption(label="Weekly", value="weekly", emoji="🤍", description="Returns 🩷 Sun at 6 p.m.; can be reserved for a week"),
                discord.SelectOption(label="Monthly", value="monthly", emoji="🟫", description="Returns on the first day of the month"),
                discord.SelectOption(label="One time", value="one-time", description="Does not return automatically after completion"),
                discord.SelectOption(label="Twice daily", value="twice-daily", description="One completion before noon; another after noon"),
                discord.SelectOption(label="On a specific weekday", value="weekday", description="Choose Monday through Sunday; overdue chores stay due"),
                discord.SelectOption(label="Twice a week", value="two-days", description="Choose two weekdays"),
                discord.SelectOption(label="Every other week", value="alternating", description="Choose a weekday and Kas/Zel home or away weeks"),
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
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own schedule picker from the household panel.',ephemeral=True)
                return False
            return True

    def update_chore(quest_id,name,frequency,points,notes,expected,room=None):
        existing=db.execute('SELECT frequency FROM quests WHERE id=?',(quest_id,)).fetchone()
        if existing and frequency!=existing[0] and db.execute("SELECT 1 FROM dated_occurrences WHERE quest_id=? AND day>=? AND state!='released'",(quest_id,timing.now().date().isoformat())).fetchone():
            return 'Release dated claims and undo dated skips before changing the repeat schedule.'
        if existing and frequency!=existing[0] and namespace['chore_ui'].repeating.slots(quest_id):
            return 'Release repeating weekday signups before changing the repeat schedule.'
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
            if room is not None:
                db.execute('UPDATE quests SET category=? WHERE id=?',(room.strip()[:100] or 'general',quest_id))
            if old[0]!=frequency:
                db.execute('DELETE FROM occurrence_moves WHERE quest_id=?',(quest_id,))
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
            self.room.default=db.execute("SELECT category FROM quests WHERE id=?",(quest_id,)).fetchone()[0] or ""

        async def on_submit(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Use your own household edit form.',ephemeral=True)
                return
            result=update_chore(self.quest_id,self.name.value,self.frequency,self.points.value,self.notes.value,self.expected,self.room.value)
            await interaction.response.send_message(result,view=ReturnView(interaction.user.id),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    def feedback_context(qid):
        row=db.execute('SELECT name,frequency,points,notes FROM quests WHERE id=?',(qid,)).fetchone()
        return json.dumps(row) if row else None

    def save_feedback(qid,author_id,author_name,comment,better_timing,points,key,context):
        if not feedback_context(qid) or is_archived(qid):
            return 'This chore is no longer on the board. No feedback saved.'
        suggested=None
        if str(points).strip():
            try:
                suggested=int(str(points).strip())
            except ValueError:
                return 'Suggested points must be a whole number, or leave them blank.'
            if not 0<=suggested<=1000000:
                return 'Suggested points must be between 0 and 1,000,000.'
        comment,better_timing=comment.strip(),better_timing.strip()
        if not comment and not better_timing and suggested is None:
            return 'Add a comment, a timing idea, or a point suggestion.'
        if len(comment)>1000 or len(better_timing)>200:
            return 'Use up to 1,000 characters for comments and 200 for timing.'
        with db:
            cursor=db.execute('INSERT OR IGNORE INTO chore_feedback(submission_key,quest_id,author_id,author_name,comment,timing,suggested_points,created_at,context) VALUES(?,?,?,?,?,?,?,?,?)',(key,qid,str(author_id),author_name[:100],comment,better_timing,suggested,namespace['now_local']().isoformat(),context))
        return 'Feedback saved. The chore’s schedule and actual points are unchanged.' if cursor.rowcount else 'That feedback was already saved. Nothing duplicated.'

    def feedback_votes(qid):
        return db.execute('SELECT author_id,author_name,suggested_points FROM chore_feedback WHERE id IN (SELECT MAX(id) FROM chore_feedback WHERE quest_id=? AND suggested_points IS NOT NULL GROUP BY author_id) ORDER BY author_name COLLATE NOCASE,author_id',(qid,)).fetchall()

    async def notify_feedback(key):
        record=db.execute('SELECT id,author_name,comment,timing,suggested_points,context FROM chore_feedback WHERE submission_key=?',(key,)).fetchone()
        if not record:
            return
        with db:
            inserted=db.execute("INSERT OR IGNORE INTO feedback_notifications VALUES (?, 'sending')",(record[0],)).rowcount
        if not inserted:
            return
        context=json.loads(record[5])
        embed=discord.Embed(title='New chore review',description=discord.utils.escape_markdown(context[0])[:1000],color=0x6B9B77)
        embed.add_field(name='From',value=discord.utils.escape_markdown(record[1])[:200],inline=False)
        if record[2]:
            escaped=discord.utils.escape_markdown(record[2])
            for at in range(0,len(escaped),900):
                embed.add_field(name='Feedback',value=escaped[at:at+900],inline=False)
        if record[3]:
            embed.add_field(name='Timing idea',value=discord.utils.escape_markdown(record[3])[:1000],inline=False)
        if record[4] is not None:
            embed.add_field(name='Suggested points',value=str(record[4]),inline=False)
        embed.set_footer(text='Open /chores in the household server → Review inbox. Suggestions do not change chores automatically.')
        async def deliver():
            recipient=bot.get_user(REVIEW_OWNER_ID) or await bot.fetch_user(REVIEW_OWNER_ID)
            await recipient.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
        try:
            await asyncio.wait_for(deliver(),timeout=10)
            status='sent'
        except Exception:
            # Never retry an ambiguous delivery automatically. The saved inbox is authoritative.
            status='failed_or_uncertain'
        with db:
            db.execute('UPDATE feedback_notifications SET status=? WHERE feedback_id=?',(status,record[0]))

    class ReviewInbox(SafeView):
        def __init__(self,owner,page=0):
            super().__init__(timeout=600)
            self.owner=owner
            records=db.execute('SELECT f.quest_id,q.name,COUNT(*),MAX(f.id) FROM chore_feedback f JOIN quests q ON q.id=f.quest_id WHERE f.reviewed=0 GROUP BY f.quest_id ORDER BY MAX(f.id) DESC').fetchall() if owner==REVIEW_OWNER_ID else []
            page=min(max(page,0),max((len(records)-1)//5,0))
            chunk=records[page*5:(page+1)*5]
            self.embed=discord.Embed(title='Owner review inbox',description='Open feedback across all chores, including removed chores. Resolve review inside a chore to clear it from this inbox; history stays saved. New feedback is also sent privately to ginaria.',color=0x6B9B77)
            for qid,name,count,last in chunk:
                self.embed.add_field(name=discord.utils.escape_markdown(name)[:200],value=f'{count} open review(s)',inline=False)
            if not chunk:
                self.embed.add_field(name='All caught up',value='No open chore feedback.',inline=False)
            self.embed.set_footer(text=f'Page {page+1} of {max((len(records)-1)//5+1,1)}')
            if chunk:
                picker=discord.ui.Select(placeholder='Choose a chore to review…',options=[discord.SelectOption(label=name[:100],value=str(qid),description=f'{count} open review(s)') for qid,name,count,last in chunk])
                async def choose(interaction):
                    view=FeedbackView(owner,int(picker.values[0]))
                    await interaction.response.edit_message(embed=view.embed,view=view)
                picker.callback=choose
                self.add_item(picker)
            async def redraw(interaction,target):
                view=ReviewInbox(owner,target)
                await interaction.response.edit_message(embed=view.embed,view=view)
            for label,target in [('Previous',page-1),('Next',page+1),('Refresh',page)]:
                if label=='Previous' and page==0 or label=='Next' and (page+1)*5>=len(records):
                    continue
                button=discord.ui.Button(label=label,row=3)
                async def navigate(interaction,target=target):
                    await redraw(interaction,target)
                button.callback=navigate
                self.add_item(button)
            self.add_dashboard()

        async def interaction_check(self,interaction):
            if interaction.user.id!=REVIEW_OWNER_ID or self.owner!=REVIEW_OWNER_ID or not allowed(interaction):
                await interaction.response.send_message('The review inbox is for ginaria, the bot owner.',ephemeral=True)
                return False
            return True

    class FeedbackModal(discord.ui.Modal):
        def __init__(self,owner,qid,points=''):
            super().__init__(title='Review this chore',timeout=600)
            self.owner,self.qid=owner,qid
            self.submission_key=uuid4().hex
            self.context=feedback_context(qid)
            self.comment=discord.ui.TextInput(label='What could be better? (optional)',placeholder='Too much work, unclear instructions, or something else?',style=discord.TextStyle.paragraph,required=False,max_length=1000)
            self.timing=discord.ui.TextInput(label='Better day or time? (optional)',placeholder='e.g. Friday afternoon works better',required=False,max_length=200)
            self.points=discord.ui.TextInput(label='Suggested points (optional)',placeholder='e.g. 1, 2, 3, 5, 8, 13, 21 — or another number',default=str(points),required=False,max_length=7)
            for item in [self.comment,self.timing,self.points]:
                self.add_item(item)

        async def on_submit(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Chore review form.',ephemeral=True)
                return
            async with lock:
                result=save_feedback(self.qid,interaction.user.id,interaction.user.display_name,self.comment.value,self.timing.value,self.points.value,self.submission_key,self.context)
            if result.startswith('Feedback saved') or result.startswith('That feedback'):
                view=FeedbackView(self.owner,self.qid)
                await interaction.response.send_message(result,embed=view.embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                if result.startswith('Feedback saved'):
                    await notify_feedback(self.submission_key)
            else:
                await interaction.response.send_message(result,ephemeral=True)

    class FeedbackView(SafeView):
        def __init__(self,owner,qid,page=0,all_reviews=False,selected=None):
            super().__init__(timeout=600)
            self.owner,self.qid=owner,qid
            chore=db.execute('SELECT name,frequency,points FROM quests WHERE id=?',(qid,)).fetchone()
            self.embed=discord.Embed(title='Chore review · '+chore[0][:100],description=f'**Current: {chore[2]} points** · {timing.compact_label(chore[1])}\nSuggest a better time, clearer instructions, or more/fewer points. Suggestions never change the chore automatically.',color=0x6B9B77)
            votes=feedback_votes(qid)
            self.embed.add_field(name='Latest point suggestions · one per person',value=('\n'.join(f'{discord.utils.escape_markdown(name)[:80]}: **{points}**' for uid,name,points in votes[:10])+ (f'\n+ {len(votes)-10} more people' if len(votes)>10 else '')) if votes else 'No scores yet. Common effort scores: 0, 1, 2, 3, 5, 8, 13, 21.',inline=False)
            records=db.execute('SELECT id,author_name,comment,timing,suggested_points,created_at,context,reviewed FROM chore_feedback WHERE quest_id=?'+('' if all_reviews else ' AND reviewed=0')+' ORDER BY id DESC',(qid,)).fetchall()
            page=min(max(page,0),max((len(records)-1)//3,0))
            chunk=records[page*3:(page+1)*3]
            chosen=next((row for row in chunk if row[0]==selected),None)
            if chosen:
                row=chosen
                self.embed.add_field(name='From '+discord.utils.escape_markdown(row[1])[:90],value=row[5][:16].replace('T',' ')+(' · Reviewed' if row[7] else ' · Open')+(f' · Suggested {row[4]} points' if row[4] is not None else ''),inline=False)
                if row[2]:
                    escaped=discord.utils.escape_markdown(row[2])
                    for at in range(0,len(escaped),900):
                        self.embed.add_field(name='Feedback' if at==0 else 'Feedback continued',value=escaped[at:at+900],inline=False)
                if row[3]:
                    self.embed.add_field(name='Timing idea',value=discord.utils.escape_markdown(row[3]),inline=False)
                previous=json.loads(row[6])
                self.embed.add_field(name='Chore when submitted',value=f'{previous[0]} · {previous[2]} points · {timing.compact_label(previous[1])}'[:1000],inline=False)
            else:
                for row in chunk:
                    preview=(discord.utils.escape_markdown(row[2])[:180] or '')+('\nTime: '+discord.utils.escape_markdown(row[3])[:100] if row[3] else '')
                    score=f'Suggested **{row[4]} points**' if row[4] is not None else 'No point score'
                    self.embed.add_field(name=discord.utils.escape_markdown(row[1])[:100]+(' · reviewed' if row[7] else ''),value=score+('\n'+preview if preview else ''),inline=False)
                if not chunk:
                    self.embed.add_field(name='No '+('feedback' if all_reviews else 'open feedback'),value='Add feedback or suggest an effort score below.',inline=False)
            self.embed.set_footer(text=f'{"All feedback" if all_reviews else "Open feedback"} · Page {page+1} of {max((len(records)-1)//3+1,1)} · Reviewed feedback stays saved')
            async def redraw(interaction,**changes):
                values=dict(page=page,all_reviews=all_reviews,selected=selected)
                values.update(changes)
                view=FeedbackView(owner,qid,**values)
                await interaction.response.edit_message(content=None,embed=view.embed,view=view,allowed_mentions=discord.AllowedMentions.none())
            def button(label,callback,row=0):
                item=discord.ui.Button(label=label,row=row)
                item.callback=callback
                self.add_item(item)
            async def add(interaction):
                await interaction.response.send_modal(FeedbackModal(owner,qid))
            button('Add feedback',add)
            async def edit(interaction):
                ids=[row[0] for row in db.execute('SELECT id FROM quests ORDER BY name COLLATE NOCASE,id') if not is_archived(row[0])]
                view=EditChoreView(owner,page=ids.index(qid)//PAGE_SIZE,selected=qid) if qid in ids else ReturnView(owner)
                await interaction.response.edit_message(content=None,embed=getattr(view,'embed',None),view=view)
            button('Edit chore',edit)
            scores=discord.ui.Select(placeholder='Suggest an effort score…',row=1,options=[discord.SelectOption(label=str(value)+' points',value=str(value)) for value in (0,1,2,3,5,8,13,21)])
            async def score(interaction):
                await interaction.response.send_modal(FeedbackModal(owner,qid,scores.values[0]))
            scores.callback=score
            self.add_item(scores)
            if chunk:
                picker=discord.ui.Select(placeholder='Read a review in full…',row=2,options=[discord.SelectOption(label=(row[1]+(f' · {row[4]} points' if row[4] is not None else '')+' · '+row[5][:10])[:100],value=str(row[0]),default=row[0]==selected) for row in chunk])
                async def choose(interaction):
                    await redraw(interaction,selected=int(picker.values[0]))
                picker.callback=choose
                self.add_item(picker)
                if chosen and not chosen[7] and owner==REVIEW_OWNER_ID:
                    async def reviewed(interaction):
                        if interaction.user.id!=REVIEW_OWNER_ID:
                            await interaction.response.send_message('Only ginaria can resolve a review.',ephemeral=True)
                            return
                        with db:
                            db.execute('UPDATE chore_feedback SET reviewed=1 WHERE id=? AND quest_id=? AND reviewed=0',(selected,qid))
                        await redraw(interaction,selected=None)
                    button('Resolve review',reviewed)
            button('Open feedback',lambda i:redraw(i,all_reviews=False,page=0,selected=None),row=3)
            button('All feedback',lambda i:redraw(i,all_reviews=True,page=0,selected=None),row=3)
            if page:
                button('Previous',lambda i:redraw(i,page=page-1,selected=None),row=3)
            if (page+1)*3<len(records):
                button('Next',lambda i:redraw(i,page=page+1,selected=None),row=3)
            if owner==REVIEW_OWNER_ID:
                async def inbox(interaction):
                    view=workspace.Inbox(owner,interaction.guild)
                    await interaction.response.edit_message(embed=view.embed,view=view)
                button('Review inbox',inbox,row=4)
            self.add_dashboard()

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Chore review view.',ephemeral=True)
                return False
            return True

    class MissedChoreView(SafeView):
        def __init__(self,owner,qid,expected):
            super().__init__(timeout=600)
            self.owner=owner
            frequency=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()[0]
            self.embed=discord.Embed(title='If this chore is missed',description='Choose a setting to save it. Current: '+('Skip if missed' if timing.policy(qid)=='skip' else 'Keep overdue'))
            self.embed.add_field(name='Keep overdue',value='Leave unfinished work due until someone completes it.',inline=False)
            self.embed.add_field(name='Skip if missed',value='Drop the expired occurrence with no points or completion credit. Release only its single claim; keep weekly sign-ups and history.',inline=False)
            self.embed.add_field(name='Before you change it',value='Switching to Skip can drop an occurrence that is already overdue. One-time chores have no deadline. Daily/twice-daily chores expire at the next slot; weekday chores at the end of their day; weekly Sunday 6 p.m.; monthly at the next month.',inline=False)
            for label,policy in [('Keep overdue','keep'),('Skip if missed','skip')]:
                button=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if timing.policy(qid)==policy else discord.ButtonStyle.secondary,disabled=frequency=='one-time' and policy=='skip')
                async def choose(interaction,policy=policy):
                    async with lock:
                        if snapshot(qid)!=expected or is_archived(qid):
                            result='This chore changed. Reopen Edit chore before saving.'
                        else:
                            result=timing.set_policy(qid,policy)
                    await interaction.response.edit_message(content=result,embed=None,view=ReturnView(interaction.user.id))
                button.callback=choose
                self.add_item(button)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own missed-chore settings.',ephemeral=True)
                return False
            return True

    class ChooseDayView(SafeView):
        def __init__(self,owner,qid,expected,day=None):
            super().__init__(timeout=600)
            self.owner=owner
            row=db.execute('SELECT name,frequency FROM quests WHERE id=?',(qid,)).fetchone()
            self.embed=discord.Embed(title='Choose a recurring day',description=f'**{discord.utils.escape_markdown(row[0])}**\nChoose which weekday this chore repeats on. This changes its regular schedule for everyone, including future weeks. Weekly sign-ups, history, and earned points stay saved.')
            picker=discord.ui.Select(placeholder='Which day works?',options=[discord.SelectOption(label=value.capitalize(),value=value,emoji=DAY_COLORS[value],default=value==day) for value in WEEKDAYS])
            async def choose(interaction):
                view=ChooseDayView(owner,qid,expected,picker.values[0])
                await interaction.response.edit_message(embed=view.embed,view=view)
            picker.callback=choose
            self.add_item(picker)
            if day:
                due=timing.next_weekday(timing.now(),WEEKDAYS.index(day))
                completed=db.execute('SELECT completed,last_completed FROM quests WHERE id=?',(qid,)).fetchone()
                if completed[0] and completed[1]:
                    last=datetime.fromisoformat(completed[1])
                    if last.tzinfo is None:
                        last=last.replace(tzinfo=api.QUEST_TIMEZONE)
                    next_repeat=datetime.fromisoformat(timing.calculate_reset(last,day))
                    if next_repeat>=timing.now():
                        due=next_repeat

                self.embed.add_field(name='New schedule',value=f'Every {day_badge(day,True)} · next scheduled date {due:%b %d}\nCompleted work stays completed until its next repeat. Tap Save day to confirm.',inline=False)
                button=discord.ui.Button(label='Save day',style=discord.ButtonStyle.primary,row=1)
                async def save(interaction):
                    async with lock:
                        api.reset_due_quests()
                        current=db.execute('SELECT name,frequency,points,notes FROM quests WHERE id=?',(qid,)).fetchone()
                        if not current or current[1] not in ('weekly',*WEEKDAYS):
                            result='This is no longer a weekly chore. Reopen its schedule settings.'
                        else:
                            result=update_chore(qid,current[0],day,str(current[2]),current[3] or '',expected)
                            if result.startswith('Saved'):
                                result=f'Saved: every {day_badge(day,True)}. History, earned points, and weekly sign-ups are unchanged.'
                    await interaction.response.edit_message(content=result,embed=None,view=ReturnView(interaction.user.id))
                button.callback=save
                self.add_item(button)
            cancel=discord.ui.Button(label='Cancel',row=1)
            async def cancel_day(interaction):
                await interaction.response.edit_message(content='Canceled. The schedule is unchanged.',embed=None,view=ReturnView(interaction.user.id))
            cancel.callback=cancel_day
            self.add_item(cancel)
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

        async def interaction_check(self,interaction):
            if not can_add(interaction,self.owner):
                await interaction.response.send_message('Open your own Change regular day view from My chores or Edit chore.',ephemeral=True)
                return False
            return True

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
                select=discord.ui.Select(placeholder='Choose a chore…',options=[chore_option(r[0],r[1],selected=r[0]==selected) for r in chunk])
                async def choose(interaction):
                    await self.show(interaction,selected=int(select.values[0]))
                select.callback=choose
                self.add_item(select)
            if chosen:
                expected=snapshot(chosen[0])
                self.embed.add_field(name=chosen[1][:256],value=timing.label(chosen[2],chosen[0]),inline=False)
                async def details(interaction):
                    await interaction.response.send_modal(EditChoreModal(owner,chosen[0],chosen[2],expected))
                async def schedule(interaction):
                    await interaction.response.send_message('Choose the replacement schedule, then review and submit the prefilled form.',view=AddChoreMenu(owner,chosen[0],expected),ephemeral=True)
                self.button('Edit details',details)
                self.button('Change schedule',schedule)
                async def missed(interaction):
                    view=MissedChoreView(owner,chosen[0],expected)
                    await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                self.button('Missed chores',missed)
                review_button=discord.ui.Button(label='Chore review',row=2)
                async def review(interaction):
                    view=FeedbackView(owner,chosen[0])
                    await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                review_button.callback=review
                self.add_item(review_button)

                if chosen[2] in ('weekly',*WEEKDAYS):
                    day_button=discord.ui.Button(label='Change regular day',row=2)
                    async def day_choice(interaction):
                        view=ChooseDayView(owner,chosen[0],expected)
                        await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)
                    day_button.callback=day_choice
                    self.add_item(day_button)

            if self.page:
                self.button('Previous',lambda i:self.show(i,page=self.page-1))
            if (self.page+1)*PAGE_SIZE<len(entries):
                self.button('Next',lambda i:self.show(i,page=self.page+1))
            self.add_dashboard()
            if hasattr(self,'embed'):
                self.embed.color=0x6B9B77

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

    HELP_TOPICS={
        'overview':('Start here',[
            ('Today','Open chores → Claim. My chores → choose a chore → Done. Drop releases it; Reassign gives it to someone; Trade waits for the other person’s acceptance.'),
            ('Plan the week','Weekly sign-ups reserves this or next week. Release week gives it up. Weeks end Sunday at 6 p.m. The overview switches By person / By chore / By day.'),
            ('Change chores','Add / Edit / Archive are shared household tools. Archived chores → Restore brings a chore back. Points already earned stay saved.'),
            ('Private controls','Use /chores for a private dashboard. Button replies are private. Dashboard takes you back; reopen /chores after a restart or 10 minutes. !help lists older commands.'),
            ('Day colors',DAY_LEGEND)]),
        'daily':('Doing & changing your chores',[
            ('Finish work','My chores → choose chore → Done. Points are awarded once for that occurrence.'),
            ('Drop or give away','Drop confirms whether it releases one occurrence, this whole week, or an ongoing assignment. Reassign shows the person and scope before you confirm.'),
            ('Trade','Offer your chore for another person’s owned chore. They accept in My chores → Trade requests. Decline or cancel keeps ownership unchanged. Trade DMs follow each recipient’s preference.')]),
        'planning':('Planning the week',[
            ('Weekly ownership','Sign up for this week or next week. Repeating daily chores stay yours after Done. Weeks change Sunday at 6 p.m. Eastern.'),
            ('Pick a day','My chores or Edit chore → Change regular day → Save day sets the recurring weekday for future weeks too.'),
            ('Three ways to look','The overview can group By person, By chore, or By day. Needs someone means unclaimed. Flexible weekly work is not assigned an invented due day.')]),
        'dates':('Trips & traded days',[
            ('Add dates','Who’s home? → select person → Mark home / Mark away → first and last full dates (YYYY-MM-DD). Dates are Eastern and inclusive.'),
            ('Rotation & coverage','Overrides expire automatically. Existing sign-ups stay saved; coverage warnings show work to review. Cancel an exception to restore the rotation.'),
            ('Account setup','An administrator selects Kas and Zel in Household setup. The default handoff is Sunday 6 p.m. Specific dated exceptions take precedence.')]),
        'manage':('Chore settings',[
            ('Add or edit','Choose a schedule and fill in the form. New chores start at 5 points; explicit zero is allowed.'),
            ('Keep or skip','Edit chore → Missed chores. Keep overdue leaves work due. Skip if missed drops an expired occurrence without points and releases only its single claim. Weekly sign-ups stay saved. One-time work has no deadline.'),
            ('Archive or restore','Archive hides a chore after confirmation. Archived chores → Restore brings it back with history and points retained.')]),
        'feedback':('Review effort & points',[('Give feedback','Choose a chore → Chore review. Add a comment, a better day/time, or an effort score. Common scores are 0, 1, 2, 3, 5, 8, 13, 21, but other whole numbers are allowed.'),('Owner inbox','New feedback is sent privately to ginaria. Ginaria can use Dashboard → Review inbox to see open feedback across all chores, even if DMs are blocked.'),('Review together','See each person’s latest point suggestion. Suggestions never change actual points automatically; use Edit chore if the household agrees. Owner resolution keeps the feedback in All feedback.')]),
        'timing':('Schedules & day colors',[
            ('Reset times','Daily: midnight. Twice daily: midnight and noon. Weekly: Sunday 6 p.m. Monthly: first day of the month. All times are Eastern.'),
            ('Fixed days','Weekday and every-other-week chores follow the chosen colored day and Keep / Skip setting. Notes do not send reminders. Away/home recurring chore dates follow the base rotation, independently of person exceptions.'),
            ('Day colors',DAY_LEGEND)])}

    def help_embed(topic='overview'):
        title,fields=HELP_TOPICS.get(topic,HELP_TOPICS['overview'])
        embed=discord.Embed(title='Sprig help · '+title,description='Choose a topic below. This guide is private.',color=0x6B9B77)
        for name,value in fields:
            embed.add_field(name=name,value=value,inline=False)
        return embed

    class HelpView(SafeView):
        def __init__(self,owner,topic='overview'):
            super().__init__(timeout=600)
            self.owner=owner
            self.embed=help_embed(topic)
            picker=discord.ui.Select(placeholder='What do you need help with?',options=[discord.SelectOption(label=value[0],value=key,default=key==topic) for key,value in HELP_TOPICS.items()])
            async def choose(interaction):
                view=HelpView(owner,picker.values[0])
                await interaction.response.edit_message(embed=view.embed,view=view)
            picker.callback=choose
            self.add_item(picker)
            self.add_dashboard()

        async def interaction_check(self,interaction):
            if interaction.user.id!=self.owner or not allowed(interaction):
                await interaction.response.send_message('Open your own Help from the dashboard.',ephemeral=True)
                return False
            return True

    class Launcher(SafeView):
        def __init__(self,timeout=None,legacy=False):
            super().__init__(timeout=timeout)
            # Keep both the persistent dashboard and fresh panels in the same order.
            layout=[('My chores',0),('Open chores',0),('Who’s doing what?',0),('Who’s home?',1),('Add chore',1),('Help',1)]
            if not legacy:layout=[('My chores',0),('Who’s home?',1),('Add chore',1),('Help',1)]
            buttons={item.label:item for item in self.children}
            self.clear_items()
            for label,row in layout:
                item=buttons[label]
                item.row=row
                item.label={'My chores':'My chores' if legacy else 'Chores','Open chores':'Pick up chores','Who’s doing what?':'Household','Add chore':'Manage chores'}.get(label,label)
                item.style=discord.ButtonStyle.primary if label=='My chores' else discord.ButtonStyle.secondary
                self.add_item(item)

        async def interaction_check(self, interaction):
            if not allowed(interaction):
                await interaction.response.send_message("Use the current household chore board.", ephemeral=True)
                return False
            return True

        async def open_list(self, interaction, mode):
            view = workspace.Chores(interaction.user.id,interaction.guild,who='mine' if mode=='mine' else 'unclaimed')
            await interaction.response.send_message(**workspace.payload(view),ephemeral=True)

        @discord.ui.button(label="Who’s doing what?", custom_id="sprig:responsibilities:v1", row=1)
        async def responsibility_button(self,interaction,button):
            view=workspace.Chores(interaction.user.id,interaction.guild,who='everyone')
            await interaction.response.send_message(**workspace.payload(view),ephemeral=True)

        @discord.ui.button(label="Reassign",custom_id="sprig:reassign:v1",row=1)
        async def reassign_button(self,interaction,button):
            view=ReassignView(interaction.user.id)
            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)

        @discord.ui.button(label="Who’s home?",custom_id="sprig:attendance:v1",row=3)
        async def attendance_button(self,interaction,button):
            view=workspace.Trips(interaction.user.id,interaction.guild)
            await interaction.response.send_message(**workspace.payload(view),ephemeral=True)

        @discord.ui.button(label='Review inbox',custom_id='sprig:review-inbox:v1',row=3)
        async def review_inbox_button(self,interaction,button):
            if interaction.user.id!=REVIEW_OWNER_ID:
                await interaction.response.send_message('The review inbox is for ginaria, the bot owner. Choose a chore → Chore review to give feedback.',ephemeral=True)
                return
            view=ReviewInbox(interaction.user.id)
            await interaction.response.send_message(embed=view.embed,view=view,ephemeral=True)

        @discord.ui.button(label="Help", custom_id="sprig:help:v1", row=1)
        async def help_button(self, interaction, button):
            view=workspace.Guide(interaction.user.id)
            await interaction.response.send_message(**workspace.payload(view),ephemeral=True)

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
            await interaction.response.send_message("Select Kas and Zel's Discord accounts, then Save. Weeks switch Sunday at 6 p.m. Eastern; Oct 18, 2026 starts an away week.", view=HouseholdSetup(interaction.user.id), ephemeral=True)

        @discord.ui.button(label="Add chore", style=discord.ButtonStyle.success, custom_id="sprig:add:v1")
        async def add_button(self, interaction, button):
            view=workspace.Manage(interaction.user.id,interaction.guild)
            await interaction.response.send_message(**workspace.payload(view),ephemeral=True)

        @discord.ui.button(label="Archive chore", style=discord.ButtonStyle.secondary, custom_id="sprig:remove:v1", row=1)
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
        if not private:
            text=BOARD_TEXT+'\nThis starter message is public. Its buttons open private controls. Use **/chores** for a fully private panel.'
            await ctx.send(text,view=Launcher(),ephemeral=False,allowed_mentions=discord.AllowedMentions.none())
            return
        view=workspace.Chores(ctx.author.id,ctx.guild)
        await ctx.send(**workspace.payload(view),ephemeral=True)

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
        bot.add_view(Launcher(legacy=True))
        saved=location()
        if saved and saved[2]!='pending':
            # Register the local handler after restarts; do not sync remotely
            # until an administrator explicitly enables the slash command.
            bot.tree.add_command(bot.tree.get_command('chores'),guild=discord.Object(id=int(saved[0])),override=True)

    bot.setup_hook = setup_hook
    result = SimpleNamespace(mutation_lock=lock,allowed=allowed, week_start=week_start, chore_option=chore_option, Context=Context, ReviewInbox=ReviewInbox, notify_feedback=notify_feedback, FeedbackView=FeedbackView, FeedbackModal=FeedbackModal, save_feedback=save_feedback, feedback_votes=feedback_votes, feedback_context=feedback_context, HelpView=HelpView, ReturnView=ReturnView, attendance=attendance, week_status=week_status, can_take_week=can_take_week, coverage_warning=coverage_warning, AttendanceView=AttendanceView, AttendanceModal=AttendanceModal, ChooseDayView=ChooseDayView, owned_scope=owned_scope, drop_chore=drop_chore, trade_snapshot=trade_snapshot, propose_trade=propose_trade, respond_trade=respond_trade, TradeOfferView=TradeOfferView, TradeInboxView=TradeInboxView, DropChoreView=DropChoreView, MissedChoreView=MissedChoreView, ReassignView=ReassignView, reassign=reassign, reassign_snapshot=reassign_snapshot, responsibility_view=responsibility_view, responsibility_rows=responsibility_rows, ResponsibilityView=ResponsibilityView, Launcher=Launcher, PersonalView=PersonalView, WeeklyView=WeeklyView, HouseholdSetup=HouseholdSetup, AddChoreModal=AddChoreModal, AddChoreMenu=AddChoreMenu, RemoveChoreView=RemoveChoreView, EditChoreView=EditChoreView, EditChoreModal=EditChoreModal, RepeatMenu=RepeatMenu, WeekdayMenu=WeekdayMenu, update_chore=update_chore, ready=timing.ready, completion_reset=timing.completion_reset, timing=timing, is_archived=is_archived, create_chore=create_chore, snapshot=snapshot, rows=rows, week_key=week_key, available=available, weekly_owner=weekly_owner, signup=signup)

    from repeating_signups import install as install_repeating
    result.repeating=install_repeating(namespace,result)
    from dated_occurrences import install as install_dated
    result.dated=install_dated(namespace,result)

    from chore_history import install as install_history
    install_history(namespace,result)
    from chore_workspace import install as install_workspace
    workspace=install_workspace(namespace,result,lock)
    result.workspace=workspace
    from chore_planning import install as install_planning
    result.planning=install_planning(namespace,result,workspace,lock)
    from chore_insights import install as install_insights
    result.insights=install_insights(namespace,result,workspace)
    # Changes away and back must not revive an old action or stored trade.
    # SQLite increments these counters in the same transaction as each mutation,
    # including legacy commands, Undo, and rollback. Navigation never bumps them.
    for table,key in [('quests','id'),('claims','quest_id'),('week_signups','quest_id'),
            ('chore_timing','quest_id'),('missed_chore_policy','quest_id'),
            ('occurrence_moves','quest_id'),('archived_chores','quest_id')]:
        for event,reference in [('INSERT','NEW'),('UPDATE','NEW'),('DELETE','OLD')]:
            changed = ''
            if event=='UPDATE':
                columns=[r[1] for r in db.execute('PRAGMA table_info('+table+')')]
                changed=' WHEN '+ ' OR '.join(f'OLD."{column}" IS NOT NEW."{column}"' for column in columns)
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS chore_revision_{table}_{event.lower()}
                AFTER {event} ON {table}{changed} BEGIN
                INSERT INTO chore_revisions(quest_id,revision) VALUES({reference}.{key},1)
                ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1;
                END""")
    db.commit()
    result.announce_update = announce_update
    result.announcement_mode = announcement_mode
    result.set_announcement_mode = set_announcement_mode
    return result
