"""Offline integration checks using a temporary copy and temporary SQLite DB."""
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "test-deps"))
import discord


def semantic_payload(kwargs):
    # Keep existing rule/navigation assertions against the source view. V2 tests
    # separately inspect wire_payload/wire_result and actual serialized components.
    result=dict(kwargs)
    view=result.get('view')
    if isinstance(view,discord.ui.LayoutView) and hasattr(view,'source'):
        result.update(view=view.source,embed=getattr(view.source,'embed',None),content=view.notice)
    return result


class Response:
    def __init__(self):
        self.payload = None
        self.wire_payload = None
        self.acknowledged = False

    def is_done(self):
        return self.acknowledged

    async def defer(self, **kwargs):
        self.acknowledged = True

    async def send_message(self, *args, **kwargs):
        self.wire_payload = (args, kwargs)
        self.payload = (args, semantic_payload(kwargs))

    async def edit_message(self, **kwargs):
        self.wire_payload = kwargs
        self.payload = semantic_payload(kwargs)

    async def send_modal(self, modal):
        self.payload = modal


class Interaction:
    def __init__(self, user_id=10):
        self.user = SimpleNamespace(id=user_id, display_name=f"Person {user_id}")
        self.guild_id, self.channel_id = 1, 2
        self.guild = SimpleNamespace(get_member=lambda uid: SimpleNamespace(display_name=f"Person {uid}"))
        self.response = Response()
        self.followup = SimpleNamespace(send=self.response.send_message)
        self.result = None

    async def edit_original_response(self, **kwargs):
        self.wire_result = kwargs
        self.result = semantic_payload(kwargs)


class BoardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        shutil.copyfile(HERE / "sprig_bot.py", root / "sprig_bot.py")
        os.environ["DISCORD_TOKEN"] = "offline-test-placeholder"
        os.environ["QUEST_TIMEZONE"] = "America/New_York"
        spec = importlib.util.spec_from_file_location("sprig_offline", root / "sprig_bot.py")
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.db = self.app.db
        self.ui = self.app.chore_ui
        self.dm = SimpleNamespace(send=AsyncMock())
        self.dm_patch = patch.object(self.app.bot, "get_user", return_value=self.dm)
        self.dm_patch.start()
        self.db.execute("INSERT INTO chore_board VALUES (1, '1', '2', '3')")
        self.db.execute("INSERT INTO quests (name, frequency, points) VALUES ('Fill dishwasher', 'daily', 5)")
        self.db.execute("INSERT INTO quests (name, frequency, points, assigned_to) VALUES ('My bathroom', 'weekly', 10, '10')")
        self.db.commit()

    async def asyncTearDown(self):
        self.dm_patch.stop()
        await self.app.bot.close()
        self.db.close()
        self.temp.cleanup()

    async def test_claim_done_and_repeat_click_awards_once(self):
        claim_view = self.ui.PersonalView(10, selected=1)
        event = Interaction()
        await claim_view.act(event, "claim")
        self.assertEqual(self.db.execute("SELECT user_id FROM claims WHERE quest_id = 1").fetchone(), ('10',))
        first = self.ui.PersonalView(10, "mine", selected=1)
        stale = self.ui.PersonalView(10, "mine", selected=1)
        await asyncio.gather(first.act(Interaction(), "done"), stale.act(Interaction(), "done"))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id = '10'").fetchone(), (5,))
        completed, reset_after = self.db.execute("SELECT completed, reset_after FROM quests WHERE id = 1").fetchone()
        self.assertEqual(completed, 1)
        self.assertIsNotNone(reset_after)
        self.assertEqual(self.ui.rows(10, "open"), [])

    async def test_competing_claims_only_one_wins(self):
        first = self.ui.PersonalView(10, selected=1)
        second = self.ui.PersonalView(20, selected=1)
        await asyncio.gather(first.act(Interaction(10), "claim"), second.act(Interaction(20), "claim"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM claims WHERE quest_id = 1").fetchone(), (1,))
        self.assertEqual(self.ui.rows(20, "mine"), [])

    async def test_release_and_assigned_ownership(self):
        self.assertEqual([r[0] for r in self.ui.rows(10, "mine")], [2])
        self.assertEqual(self.ui.rows(20, "mine"), [])
        wrong = Interaction(20)
        view = self.ui.PersonalView(10, "mine", selected=2)
        self.assertFalse(await view.interaction_check(wrong))
        self.assertNotIn("Release", [c.label for c in view.children if isinstance(c, discord.ui.Button)])
        await self.ui.PersonalView(10, selected=1).act(Interaction(), "claim")
        await self.ui.PersonalView(10, "mine", selected=1).act(Interaction(), "unclaim")
        self.assertEqual([r[0] for r in self.ui.rows(20, "open")], [1])

    async def test_reset_invalidates_old_completion_button(self):
        self.db.execute("INSERT INTO claims VALUES (1, '10')")
        self.db.commit()
        old = self.ui.PersonalView(10, "mine", selected=1)
        await old.act(Interaction(), "done")
        self.db.execute("UPDATE quests SET reset_after = '2020-01-01T00:00:00-05:00' WHERE id = 1")
        self.db.commit()
        self.app.reset_due_quests()
        await self.ui.PersonalView(10, selected=1).act(Interaction(), "claim")
        await old.act(Interaction(), "done")
        self.assertEqual(self.db.execute("SELECT completed FROM quests WHERE id = 1").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id = '10'").fetchone(), (5,))

    async def test_large_list_pagination_and_persistent_launcher(self):
        self.db.executemany("INSERT INTO quests (name) VALUES (?)", [(f"Task {i:03}" + 'x' * 120,) for i in range(65)])
        self.db.commit()
        view = self.ui.PersonalView(10)
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        self.assertEqual(len(select.options), 20)
        self.assertTrue(all(len(o.label) <= 100 for o in select.options))
        self.assertLessEqual(len(view.embed.fields[0].value), 1024)
        self.assertTrue(self.ui.Launcher().is_persistent())
        await self.app.bot.setup_hook()
        self.assertTrue(any(v.is_persistent() for v in self.app.bot.persistent_views))
        last = self.ui.PersonalView(10, page=100)
        self.assertEqual(last.page, 3)

    async def test_wrong_channel_rejected_and_no_duplicate_board(self):
        event = Interaction()
        event.channel_id = 99
        self.assertFalse(await self.ui.Launcher().interaction_check(event))
        messages = []
        async def send(content):
            messages.append(content)
        await self.app.bot.get_command("choreboard").callback(SimpleNamespace(send=send))
        self.assertIn("already set up", messages[0])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chore_board").fetchone(), (1,))

    async def test_interrupted_setup_does_not_post_again(self):
        self.db.execute("DELETE FROM chore_board")
        self.db.commit()
        async def uncertain_send(*args, **kwargs):
            raise TimeoutError("delivery outcome unknown")
        context = SimpleNamespace(guild=SimpleNamespace(id=1), channel=SimpleNamespace(id=2), send=uncertain_send)
        with self.assertRaises(TimeoutError):
            await self.app.bot.get_command("choreboard").callback(context)
        messages = []
        async def capture(content, **kwargs):
            messages.append(content)
        context.send = capture
        await self.app.bot.get_command("choreboard").callback(context)
        self.assertEqual(len(messages), 1)
        self.assertIn("won't post a duplicate", messages[0])

    async def test_select_callback_renders_actions(self):
        view = self.ui.PersonalView(10)
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        select._values = ['1']
        event = Interaction()
        await select.callback(event)
        selected_view = event.response.payload['view']
        self.assertIn('Claim', [c.label for c in selected_view.children if isinstance(c, discord.ui.Button)])
        mine = self.ui.PersonalView(10, 'mine', selected=2)
        await mine.act(Interaction(), 'done')
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id = 2').fetchone(), (1,))

    def clock(self, stamp):
        instant = datetime.fromisoformat(stamp).replace(tzinfo=self.app.QUEST_TIMEZONE)
        return patch.object(self.app, 'now_local', return_value=instant)

    async def test_weekly_daily_owner_survives_done_and_midnight(self):
        with self.clock('2026-10-19T12:00:00'):
            self.ui.signup(10, 1, self.ui.week_key())
            await self.ui.PersonalView(10, 'mine', selected=1).act(Interaction(), 'done')
            self.assertEqual(self.ui.weekly_owner(1), '10')
            self.assertEqual(self.ui.rows(10, 'mine')[0][0], 2)
        with self.clock('2026-10-20T12:00:00'):
            self.assertIn(1, [r[0] for r in self.ui.rows(10, 'mine')])
            self.assertNotIn(1, [r[0] for r in self.ui.rows(20, 'open')])
            await self.ui.PersonalView(10, 'mine', selected=1).act(Interaction(), 'done')
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id = '10'").fetchone(), (10,))

    async def test_exact_sunday_handoff_and_next_week_reservation(self):
        with self.clock('2026-10-19T12:00:00'):
            self.ui.signup(10, 1, self.ui.week_key())
            self.ui.signup(20, 1, self.ui.week_key(1))
        with self.clock('2026-10-25T17:59:59'):
            self.assertEqual(self.ui.weekly_owner(1), '10')
        with self.clock('2026-10-25T18:00:00'):
            self.assertEqual(self.ui.weekly_owner(1), '20')
            self.assertNotIn(1, [r[0] for r in self.ui.rows(10, 'mine')])
            self.assertIn(1, [r[0] for r in self.ui.rows(20, 'mine')])

    async def test_alternating_weeks_and_dst(self):
        self.db.execute("INSERT INTO alternating_members VALUES ('10')")
        self.db.commit()
        for stamp, expected in [('2026-10-19T12:00:00', False), ('2026-10-25T18:00:00', True), ('2026-11-01T17:59:59', True), ('2026-11-01T18:00:00', False), ('2026-11-08T18:00:00', True)]:
            with self.clock(stamp):
                self.assertEqual(self.ui.available(10), expected, stamp)
                self.assertTrue(self.ui.available(20), stamp)
        with self.clock('2026-10-19T12:00:00'):
            self.assertIn("away", self.ui.signup(10, 1, self.ui.week_key()))
            self.assertIn("signed up", self.ui.signup(10, 1, self.ui.week_key(1)))

    async def test_legacy_commands_cannot_bypass_week_owner_or_away(self):
        with self.clock('2026-10-19T12:00:00'):
            self.ui.signup(10, 1, self.ui.week_key())
            messages = []
            async def send(message):
                messages.append(message)
            event = Interaction(20)
            context = SimpleNamespace(author=event.user, guild=event.guild, send=send)
            await self.app.bot.get_command('claim').callback(context, 1)
            await self.app.bot.get_command('done').callback(context, 1)
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id = 1').fetchone(), (0,))
            self.assertIsNone(self.db.execute('SELECT user_id FROM claims WHERE quest_id = 1').fetchone())
            self.db.execute("INSERT INTO alternating_members VALUES ('20')")
            self.db.commit()
            await self.app.bot.get_command('claim').callback(context, 1)
            self.assertIn("away", messages[-1])

    async def test_weekly_competition_release_and_completed_preservation(self):
        with self.clock('2026-10-19T12:00:00'):
            first = self.ui.WeeklyView(10, selected=1)
            second = self.ui.WeeklyView(20, selected=1)
            await asyncio.gather(first.act(Interaction()), second.act(Interaction(20)))
            self.assertEqual(self.ui.weekly_owner(1), '10')
            await self.ui.PersonalView(10, 'mine', selected=1).act(Interaction(), 'done')
            await self.ui.WeeklyView(10, selected=1).act(Interaction(), release=True)
            self.assertIsNone(self.ui.weekly_owner(1))
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id = 1').fetchone(), (1,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id = '10'").fetchone(), (5,))

    async def test_stale_weekly_click_after_handoff_does_not_reserve_wrong_week(self):
        with self.clock('2026-10-25T17:59:00'):
            old = self.ui.WeeklyView(10, selected=1)
        with self.clock('2026-10-25T18:01:00'):
            await old.act(Interaction())
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM week_signups').fetchone(), (0,))

    async def test_weekly_data_persists_and_assigned_chore_cannot_be_reserved(self):
        with self.clock('2026-10-19T12:00:00'):
            self.ui.signup(10, 1, self.ui.week_key(1))
            self.assertIn('no longer', self.ui.signup(20, 2, self.ui.week_key()))
            import sqlite3
            other = sqlite3.connect(Path(self.temp.name) / 'sprig.db')
            self.assertEqual(other.execute('SELECT user_id FROM week_signups').fetchone(), ('10',))
            other.close()

    async def test_new_week_owner_supersedes_previous_occurrence_claim(self):
        with self.clock('2026-10-19T12:00:00'):
            self.ui.signup(20, 1, self.ui.week_key(1))
            self.db.execute("INSERT INTO claims VALUES (1, '10')")
            self.db.commit()
        with self.clock('2026-10-25T18:00:00'):
            self.assertIn(1, [r[0] for r in self.ui.rows(20, 'mine')])
            self.assertIsNone(self.db.execute('SELECT user_id FROM claims WHERE quest_id = 1').fetchone())

    async def test_household_setup_requires_admin_and_selection(self):
        view = self.ui.HouseholdSetup(10)
        event = Interaction()
        event.user.guild_permissions = SimpleNamespace(manage_guild=False)
        self.assertFalse(await view.interaction_check(event))
        event.user.guild_permissions.manage_guild = True
        self.assertTrue(await view.interaction_check(event))
        await view.save(event)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM alternating_members').fetchone(), (0,))
        with self.clock('2026-10-19T12:00:00'):
            view.members = ['10', '30']
            await view.save(event)
            self.assertFalse(self.ui.available(10))
            self.assertFalse(self.ui.available(30))
            self.assertTrue(self.ui.available(20))

    async def test_add_form_preserves_existing_and_blocks_duplicate(self):
        before = self.db.execute('SELECT * FROM quests ORDER BY id').fetchall()
        message = self.ui.create_chore('  Sweep   kitchen ', 'daily', '', 'Afternoon')
        self.assertIn('Added', message)
        self.assertEqual(self.db.execute("SELECT frequency, points, notes, assigned_to FROM quests WHERE name = 'Sweep kitchen'").fetchone(), ('daily', 5, 'Afternoon', None))
        self.assertIn('already exists', self.ui.create_chore('sweep kitchen', 'daily', '5', ''))
        self.assertEqual(self.db.execute('SELECT * FROM quests ORDER BY id LIMIT 2').fetchall(), before)
        self.assertIn('already exists', self.ui.create_chore('Fill dishwasher', 'daily', '5', ''))

    async def test_starting_points_default_five_and_explicit_zero_allowed(self):
        self.assertEqual(self.ui.AddChoreModal(10,'daily').points.default,'5')
        self.ui.create_chore('Free chore','daily','0','')
        self.assertEqual(self.db.execute("SELECT points FROM quests WHERE name='Free chore'").fetchone()[0],0)
        self.ui.update_chore(2,'My bathroom','weekly','','',self.ui.snapshot(2))
        self.assertEqual(self.db.execute('SELECT points FROM quests WHERE id=2').fetchone()[0],5)

    async def test_add_form_rejects_bad_input_without_writes(self):
        for name, frequency, points in [(' ', 'daily', '0'), ('New', 'yearly', '0'), ('New', 'daily', '-1'), ('New', 'daily', 'many')]:
            self.ui.create_chore(name, frequency, points, '')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(), (2,))

    async def test_add_menu_opens_modal_and_admin_submit(self):
        menu = self.ui.AddChoreMenu(10)
        event = Interaction()
        event.user.guild_permissions = SimpleNamespace(manage_guild=True)
        self.assertTrue(await menu.interaction_check(event))
        menu.children[0]._values = ['monthly']
        await menu.children[0].callback(event)
        modal = event.response.payload
        self.assertEqual(modal.frequency, 'monthly')
        modal.name._value = 'Clean microwave and turntable'
        modal.notes._value = 'Include turntable'
        modal.points._value = '0'
        await modal.on_submit(event)
        self.assertEqual(self.db.execute("SELECT frequency FROM quests WHERE name = 'Clean microwave and turntable'").fetchone(), ('monthly',))
        await modal.on_submit(event)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(), (3,))

    async def test_add_modal_rechecks_permissions_and_location(self):
        modal = self.ui.AddChoreModal(10, 'daily')
        modal.name._value = 'Should not be added'
        for user_id, admin, channel in [(20, True, 2), (10, True, 99)]:
            event = Interaction(user_id)
            event.user.guild_permissions = SimpleNamespace(manage_guild=admin)
            event.channel_id = channel
            await modal.on_submit(event)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(), (2,))

    async def test_panel_refresh_edits_saved_message_without_posting_new_board(self):
        edits, notices = [], []
        async def edit(**kwargs):
            edits.append(kwargs)
        async def fetch(message_id):
            self.assertEqual(message_id, 3)
            return SimpleNamespace(author=SimpleNamespace(id=777), edit=edit)
        async def send(content):
            notices.append(content)
        self.app.bot._connection.user = SimpleNamespace(id=777)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), channel=SimpleNamespace(id=2, fetch_message=fetch), send=send)
        await self.app.bot.get_command('refreshchoreboard').callback(ctx)
        self.assertEqual(len(edits), 1)
        self.assertIn('Manage chores', [c.label for c in edits[0]['view'].children])
        self.assertEqual(self.db.execute('SELECT message_id FROM chore_board').fetchone(), ('3',))

    async def test_everyone_can_add_without_admin(self):
        event=Interaction()
        event.user.guild_permissions=SimpleNamespace(manage_guild=False)
        menu=self.ui.AddChoreMenu(10)
        self.assertTrue(await menu.interaction_check(event))
        modal=self.ui.AddChoreModal(10,'daily')
        modal.name._value='Sweep patio'
        modal.notes._value=''
        modal.points._value=''
        await modal.on_submit(event)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM quests WHERE name = 'Sweep patio'").fetchone(),(1,))

    async def test_remove_requires_confirmation_and_restore_keeps_data(self):
        self.db.execute("INSERT INTO claims VALUES (1,'10')")
        self.db.commit()
        before=self.db.execute('SELECT * FROM quests WHERE id=1').fetchone()
        view=self.ui.RemoveChoreView(10,selected=1)
        self.assertFalse(self.ui.is_archived(1))
        await view.act(Interaction())
        self.assertTrue(self.ui.is_archived(1))
        self.assertNotIn(1,[r[0] for r in self.ui.rows(10,'mine')])
        self.assertIn('no longer',self.ui.signup(10,1,self.ui.week_key()))
        await self.ui.RemoveChoreView(10,removed=True,selected=1).act(Interaction())
        self.assertEqual(self.db.execute('SELECT * FROM quests WHERE id=1').fetchone(),before)
        self.assertEqual(self.db.execute('SELECT user_id FROM claims WHERE quest_id=1').fetchone(),('10',))

    async def test_removed_chore_cannot_complete_through_old_button(self):
        await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
        old=self.ui.PersonalView(10,'mine',selected=1)
        await self.ui.RemoveChoreView(10,selected=1).act(Interaction())
        await old.act(Interaction(),'done')
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(0,))

    async def test_removal_rechecks_changed_chore(self):
        stale=self.ui.RemoveChoreView(10,selected=1)
        await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
        await stale.act(Interaction())
        self.assertFalse(self.ui.is_archived(1))

    async def test_twice_daily_completion_limits_and_weekly_owner(self):
        with self.clock('2026-10-19T09:00:00'):
            self.ui.create_chore('Dishwasher filling','twice-daily','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Dishwasher filling'").fetchone()[0]
            self.ui.signup(10,qid,self.ui.week_key())
            early=self.ui.PersonalView(10,'mine',selected=qid)
            await early.act(Interaction(),'done')
            await early.act(Interaction(),'done')
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(5,))
        with self.clock('2026-10-19T11:59:59'):
            self.assertNotIn(qid,[r[0] for r in self.ui.rows(10,'mine')])
        with self.clock('2026-10-19T12:00:00'):
            self.assertIn(qid,[r[0] for r in self.ui.rows(10,'mine')])
            await self.ui.PersonalView(10,'mine',selected=qid).act(Interaction(),'done')
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        with self.clock('2026-10-20T00:00:00'):
            self.assertIn(qid,[r[0] for r in self.ui.rows(10,'mine')])
            self.assertEqual(self.ui.weekly_owner(qid),'10')

    async def test_weekday_stays_hidden_until_due_and_overdue_until_done(self):
        with self.clock('2026-10-19T09:00:00'):
            self.ui.create_chore('Curb trash Wednesday','wednesday','0','Evening')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Curb trash Wednesday'").fetchone()[0]
            self.assertNotIn(qid,[r[0] for r in self.ui.rows(10,'open')])
            self.ui.signup(10,qid,self.ui.week_key())
        with self.clock('2026-10-21T00:00:00'):
            self.assertIn(qid,[r[0] for r in self.ui.rows(10,'mine')])
        with self.clock('2026-10-22T10:00:00'):
            self.assertIn(qid,[r[0] for r in self.ui.rows(10,'mine')])
            await self.ui.PersonalView(10,'mine',selected=qid).act(Interaction(),'done')
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone(),(1,))
        with self.clock('2026-10-27T23:59:59'):
            self.assertNotIn(qid,[r[0] for r in self.ui.rows(20,'open')])
        with self.clock('2026-10-28T00:00:00'):
            self.assertIn(qid,[r[0] for r in self.ui.rows(20,'open')])

    async def test_weekday_created_on_due_day_is_ready_immediately(self):
        with self.clock('2026-10-21T20:00:00'):
            self.ui.create_chore('Wednesday job','wednesday','0','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Wednesday job'").fetchone()[0]
            self.assertTrue(self.ui.ready(qid))

    async def test_weekday_and_twice_daily_resets_across_dst(self):
        from zoneinfo import ZoneInfo
        when=datetime(2026,10,31,20,tzinfo=ZoneInfo('America/New_York'))
        next_reset=self.app.calculate_reset_after(when,'sunday')
        self.assertTrue(next_reset.startswith('2026-11-01T00:00:00-04:00'))
        after_fallback=datetime(2026,11,1,10,tzinfo=ZoneInfo('America/New_York'))
        self.assertEqual(self.app.calculate_reset_after(after_fallback,'twice-daily'),'2026-11-01T12:00:00-05:00')

    async def test_edit_prefilled_form_preserves_completion_and_assignment(self):
        event=Interaction()
        event.user.guild_permissions=SimpleNamespace(manage_guild=False)
        before=self.db.execute('SELECT assigned_to FROM quests WHERE id=2').fetchone()
        expected=self.ui.snapshot(2)
        modal=self.ui.EditChoreModal(10,2,'weekly',expected)
        self.assertEqual(modal.name.default,'My bathroom')
        modal.name._value='Clean my bathroom'
        modal.notes._value='Towels and trash'
        modal.points._value='12'
        await modal.on_submit(event)
        self.assertEqual(self.db.execute('SELECT name,notes,points FROM quests WHERE id=2').fetchone(),('Clean my bathroom','Towels and trash',12))
        self.assertEqual(self.db.execute('SELECT assigned_to FROM quests WHERE id=2').fetchone(),before)
        self.assertIn('changed',self.ui.update_chore(2,'Stale overwrite','daily','1','',expected))

    async def test_edit_schedule_retains_earned_points_and_completed_cycle(self):
        with self.clock('2026-10-19T09:00:00'):
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            result=self.ui.update_chore(1,'Fill dishwasher','twice-daily','8','',self.ui.snapshot(1))
            self.assertIn('Saved',result)
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(1,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(5,))
        with self.clock('2026-10-19T12:00:00'):
            self.assertIn(1,[r[0] for r in self.ui.rows(10,'open')])

    async def test_edit_duplicate_and_week_signup_incompatible_schedule(self):
        with self.clock('2026-10-19T09:00:00'):
            self.assertIn('already',self.ui.update_chore(1,'My bathroom','daily','5','',self.ui.snapshot(1)))
            self.ui.signup(10,1,self.ui.week_key())
            self.assertIn('Release',self.ui.update_chore(1,'Fill dishwasher','monthly','5','',self.ui.snapshot(1)))
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=1').fetchone(),('daily',))

    async def test_weekday_picker_opens_named_schedule_form(self):
        picker=self.ui.WeekdayMenu(10)
        picker.children[0]._values=['wednesday']
        event=Interaction()
        self.assertTrue(await picker.interaction_check(event))
        await picker.children[0].callback(event)
        self.assertEqual(event.response.payload.frequency,'wednesday')

    async def test_board_link_available_to_non_admin_in_another_channel(self):
        messages=[]
        async def send(message,**kwargs):
            messages.append(message)
        channel=SimpleNamespace(permissions_for=lambda member:SimpleNamespace(view_channel=True,read_message_history=True))
        ctx=SimpleNamespace(guild=SimpleNamespace(id=1,get_channel=lambda cid:channel if cid==2 else None),author=SimpleNamespace(id=20),channel=SimpleNamespace(id=99),send=send)
        before=self.db.execute('SELECT * FROM chore_board').fetchall()
        await self.app.bot.get_command('board').callback(ctx)
        self.assertIn('https://discord.com/channels/1/2/3',messages[0])
        self.assertEqual(self.db.execute('SELECT * FROM chore_board').fetchall(),before)

    async def test_board_link_never_exposes_other_server_or_hidden_channel(self):
        messages=[]
        async def send(message,**kwargs):
            messages.append(message)
        hidden=SimpleNamespace(permissions_for=lambda member:SimpleNamespace(view_channel=False,read_message_history=False))
        for guild in [None,SimpleNamespace(id=99),SimpleNamespace(id=1,get_channel=lambda cid:hidden)]:
            await self.app.bot.get_command('board').callback(SimpleNamespace(guild=guild,author=SimpleNamespace(id=20),send=send))
        self.assertTrue(all('https://' not in m for m in messages))

    async def test_board_shortcut_does_not_recreate_pending_panel(self):
        self.db.execute("UPDATE chore_board SET message_id='pending'")
        self.db.commit()
        messages=[]
        async def send(message,**kwargs):
            messages.append(message)
        await self.app.bot.get_command('board').callback(SimpleNamespace(send=send))
        self.assertEqual(self.db.execute('SELECT message_id FROM chore_board').fetchone(),('pending',))
        self.assertIn('check setup',messages[0])

    async def test_chores_prefix_opens_controls_here_without_jump(self):
        messages=[]
        async def send(content,**kwargs):
            messages.append((content,kwargs))
        channel=SimpleNamespace(permissions_for=lambda user:SimpleNamespace(view_channel=True,read_message_history=True))
        ctx=SimpleNamespace(interaction=None,guild=SimpleNamespace(id=1,get_channel=lambda cid:channel),channel=SimpleNamespace(id=99),author=SimpleNamespace(id=10),send=send)
        await self.app.bot.get_command('chores').callback(ctx)
        content,options=messages[0]
        self.assertNotIn('https://discord.com/',content)
        self.assertIn('starter message is public',content)
        self.assertIn('Tap **Help**',content)
        self.assertFalse(options['ephemeral'])
        self.assertIn('Pick up chores',[c.label for c in options['view'].children])
        self.assertEqual(options['view'].timeout,600)

    async def test_slash_chores_is_private_and_actions_stay_private(self):
        messages=[]
        async def send(content,**kwargs):
            messages.append((content,kwargs))
        ctx=SimpleNamespace(interaction=object(),guild=SimpleNamespace(id=1),channel=SimpleNamespace(id=2),author=SimpleNamespace(id=10),send=send)
        await self.app.bot.get_command('chores').callback(ctx)
        self.assertTrue(messages[0][1]['ephemeral'])
        event=Interaction()
        await next(c for c in messages[0][1]['view'].children if c.label=='Pick up chores').callback(event)
        self.assertIsInstance(event.response.payload,dict)
        self.assertIsInstance(event.response.payload['view'],self.ui.workspace.Browse)

    async def test_private_panel_does_not_bypass_hidden_channel(self):
        hidden=SimpleNamespace(permissions_for=lambda user:SimpleNamespace(view_channel=False,read_message_history=False))
        event=Interaction()
        event.channel_id=99
        event.guild.get_channel=lambda cid:hidden
        self.assertFalse(await self.ui.Launcher().interaction_check(event))
        self.assertTrue(event.response.payload[1]['ephemeral'])

    async def test_two_weekdays_due_overdue_and_next_occurrence(self):
        with self.clock('2026-10-19T10:00:00'):
            self.assertIn('Added',self.ui.create_chore('Morning room trash','days:tuesday,friday','0',''))
            qid=self.db.execute("SELECT id FROM quests WHERE name='Morning room trash'").fetchone()[0]
            self.assertFalse(self.ui.ready(qid))
        with self.clock('2026-10-20T00:00:00'):
            self.assertTrue(self.ui.ready(qid))
        with self.clock('2026-10-22T10:00:00'):
            self.assertTrue(self.ui.ready(qid))
            reset=self.ui.completion_reset(qid,self.app.now_local(),'days:tuesday,friday')
            self.assertTrue(reset.startswith('2026-10-23T00:00:00'))
            self.assertFalse(self.ui.ready(qid))
        with self.clock('2026-10-23T00:00:00'):
            self.assertTrue(self.ui.ready(qid))

    async def test_alternating_monday_away_anchor_and_signups(self):
        with self.clock('2026-10-19T10:00:00'):
            self.ui.create_chore('Recycling','away:monday','0','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Recycling'").fetchone()[0]
            self.assertTrue(self.ui.ready(qid))
            self.assertIn('not scheduled',self.ui.signup(10,qid,self.ui.week_key(1)))
            self.assertIn('signed up',self.ui.signup(10,qid,self.ui.week_key()))
            self.assertNotIn(str(qid),[option.value for child in self.ui.WeeklyView(10,1).children if isinstance(child,discord.ui.Select) for option in child.options])
            reset=self.ui.completion_reset(qid,self.app.now_local(),'away:monday')
            self.assertTrue(reset.startswith('2026-11-02T00:00:00-05:00'))
        with self.clock('2026-10-26T10:00:00'):
            self.assertFalse(self.ui.ready(qid))
        with self.clock('2026-11-02T00:00:00'):
            self.assertTrue(self.ui.ready(qid))

    async def test_alternating_saturday_overdue_does_not_disappear(self):
        with self.clock('2026-10-19T10:00:00'):
            self.ui.create_chore('Yard check','away:saturday','0','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Yard check'").fetchone()[0]
            self.assertFalse(self.ui.ready(qid))
        with self.clock('2026-10-24T00:00:00'):
            self.assertTrue(self.ui.ready(qid))
        with self.clock('2026-10-26T10:00:00'):
            self.assertTrue(self.ui.ready(qid))
            self.assertIn('signed up',self.ui.signup(10,qid,self.ui.week_key()))
            reset=self.ui.completion_reset(qid,self.app.now_local(),'away:saturday')
            self.assertTrue(reset.startswith('2026-11-07T00:00:00-05:00'))

    async def test_alternating_sunday_midnight_is_before_handoff(self):
        with self.clock('2026-10-25T17:59:00'):
            self.assertTrue(self.ui.timing.matches(self.app.now_local().date(),'away:sunday'))
            self.assertFalse(self.ui.timing.matches(self.app.now_local().date(),'home:sunday'))
            self.assertTrue(self.ui.timing.in_week('away:sunday',self.app.now_local().replace(day=18,hour=18)))
        with self.clock('2026-10-25T18:00:00'):
            start=self.app.now_local()
            self.assertFalse(self.ui.timing.in_week('away:monday',start))
            self.assertTrue(self.ui.timing.in_week('home:monday',start))

    async def test_extended_schedule_claim_done_reset_and_reload(self):
        with self.clock('2026-10-19T10:00:00'):
            self.ui.create_chore('Alternating recycling','away:monday','4','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Alternating recycling'").fetchone()[0]
            await self.ui.PersonalView(10,selected=qid).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=qid).act(Interaction(),'done')
            row=self.db.execute('SELECT completed,reset_after FROM quests WHERE id=?',(qid,)).fetchone()
            self.assertEqual(row[0],1)
            self.assertTrue(row[1].startswith('2026-11-02'))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],4)
            from chore_timing import ChoreTiming
            timing=ChoreTiming(vars(self.app),self.db)
            self.assertFalse(timing.ready(qid))
        with self.clock('2026-10-26T10:00:00'):
            self.app.reset_due_quests()
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()[0],1)
        with self.clock('2026-11-02T00:00:00'):
            self.app.reset_due_quests()
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone()[0],0)
            self.assertTrue(timing.ready(qid))

    async def test_repeat_picker_creates_and_edits_with_canonical_days(self):
        menu=self.ui.RepeatMenu(10,'two-days')
        menu.children[0]._values=['friday','tuesday']
        event=Interaction()
        await menu.children[0].callback(event)
        self.assertEqual(event.response.payload.frequency,'days:tuesday,friday')
        expected=self.ui.snapshot(1)
        menu=self.ui.RepeatMenu(10,'alternating',1,expected,'home')
        menu.children[0]._values=['saturday']
        event=Interaction()
        await menu.children[0].callback(event)
        self.assertEqual(event.response.payload.frequency,'home:saturday')
        self.assertEqual(event.response.payload.expected,expected)
        other=Interaction(20)
        self.assertFalse(await menu.interaction_check(other))

    async def test_roster_weekly_owner_done_and_unclaimed(self):
        with self.clock('2026-10-19T10:00:00'):
            self.ui.signup(20,1,self.ui.week_key())
            self.db.execute('UPDATE quests SET completed=1 WHERE id=1')
            self.db.commit()
            self.ui.create_chore('Sweep kitchen','daily','0','')
            rows=self.ui.responsibility_rows()
            filling=next(r for r in rows if r[1]==1)
            self.assertEqual((filling[0],filling[4]),('20','Weekly sign-up'))
            self.assertIn('Done',filling[5])
            self.assertTrue(any(r[0] is None and r[2]=='Sweep kitchen' for r in rows))
            self.assertEqual(next(r for r in rows if r[1]==2)[0],'10')

    async def test_roster_next_week_ignores_current_claim_and_reservation(self):
        with self.clock('2026-10-19T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES (1,'20')")
            self.db.commit()
            self.assertEqual(next(r for r in self.ui.responsibility_rows() if r[1]==1)[0],'20')
            self.assertIsNone(next(r for r in self.ui.responsibility_rows(1) if r[1]==1)[0])
            self.ui.signup(10,1,self.ui.week_key(1))
            self.assertEqual(next(r for r in self.ui.responsibility_rows(1) if r[1]==1)[0],'10')

    async def test_roster_excludes_archived_and_wrong_alternating_week(self):
        with self.clock('2026-10-19T10:00:00'):
            self.ui.create_chore('Away recycling','away:monday','0','')
            self.db.execute("INSERT INTO archived_chores VALUES (2,'10','test')")
            self.db.commit()
            self.assertNotIn(2,[r[1] for r in self.ui.responsibility_rows()])
            self.assertNotIn('Away recycling',[r[2] for r in self.ui.responsibility_rows(1)])
            self.assertIn('Away recycling',[r[2] for r in self.ui.responsibility_rows()])

    async def test_roster_launcher_private_and_navigation_refreshes(self):
        with self.clock('2026-10-19T10:00:00'):
            event=Interaction()
            button=next(c for c in self.ui.Launcher().children if c.label=='Household')
            await button.callback(event)
            options=event.response.payload[1]
            self.assertTrue(options['ephemeral'])
            view=options['view']
            self.assertTrue(await view.interaction_check(event))
            self.assertFalse(await view.interaction_check(Interaction(20)))
            await next(c for c in view.children if getattr(c,'label',None)=='Next week').callback(event)
            self.assertEqual(event.response.payload['view'].state['tab'],'next')
            self.assertIn('Next week',event.response.payload['embed'].description)

    async def test_claim_and_done_fast_path_use_single_response(self):
        with self.clock('2026-10-20T10:00:00'):
            claim=Interaction()
            await self.ui.PersonalView(10,selected=1).act(claim,'claim')
            self.assertFalse(claim.response.acknowledged)
            self.assertIsNotNone(claim.response.payload['view'])
            self.assertIsNone(claim.result)
            done=Interaction()
            await self.ui.PersonalView(10,'mine',selected=1).act(done,'done')
            self.assertFalse(done.response.acknowledged)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],5)

    async def test_slow_claim_defers_and_mutates_only_once(self):
        import chore_board
        command=self.app.bot.get_command('claim')
        original=command.callback
        calls=[]
        async def slow(ctx,qid):
            calls.append(qid)
            await asyncio.sleep(0.03)
            await original(ctx,qid)
        with self.clock('2026-10-20T10:00:00'),patch.object(chore_board,'ACTION_ACK_SECONDS',0.001),patch.object(command,'_callback',slow):
            event=Interaction()
            await self.ui.PersonalView(10,selected=1).act(event,'claim')
            self.assertTrue(event.response.acknowledged)
            self.assertIsNotNone(event.result['view'])
            self.assertEqual(calls,[1])
            self.assertEqual(self.db.execute('SELECT count(*) FROM claims WHERE quest_id=1').fetchone()[0],1)

    async def test_roster_reuses_name_lookup_until_expiry_and_prefers_live_cache(self):
        guild=SimpleNamespace(id=1,get_member=lambda uid:None,fetch_member=AsyncMock(return_value=SimpleNamespace(display_name='Katie')))
        import chore_board
        with patch.object(chore_board,'monotonic',return_value=100):
            await self.ui.responsibility_view(10,guild)
            await self.ui.responsibility_view(10,guild,1)
            guild.fetch_member.assert_awaited_once()
        with patch.object(chore_board,'monotonic',return_value=401):
            await self.ui.responsibility_view(10,guild)
            self.assertEqual(guild.fetch_member.await_count,2)
        guild.get_member=lambda uid:SimpleNamespace(display_name='New nickname')
        view=await self.ui.responsibility_view(10,guild)
        self.assertIn('New nickname',str(view.embed.to_dict()))
        self.assertEqual(guild.fetch_member.await_count,2)

    async def test_roster_fetches_uncached_member_nickname(self):
        guild=SimpleNamespace(get_member=lambda uid:None,fetch_member=AsyncMock(return_value=SimpleNamespace(display_name='Katie nickname')))
        view=await self.ui.responsibility_view(10,guild)
        self.assertIn('Katie nickname',str(view.embed.to_dict()))
        self.assertNotIn('Account 10',str(view.embed.to_dict()))
        guild.fetch_member.assert_awaited_once_with(10)

    async def test_roster_uses_existing_user_lookup_when_member_unavailable(self):
        error=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),'No access')
        guild=SimpleNamespace(get_member=lambda uid:None,fetch_member=AsyncMock(side_effect=error))
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',new=AsyncMock(return_value=SimpleNamespace(display_name='Known user'))) as fetch:
            view=await self.ui.responsibility_view(10,guild)
            self.assertIn('Known user',str(view.embed.to_dict()))
            fetch.assert_awaited_once_with(10)

    async def test_roster_keeps_readable_fallback_when_discord_lookup_fails(self):
        error=discord.NotFound(SimpleNamespace(status=404,reason='Not Found'),'Gone')
        guild=SimpleNamespace(get_member=lambda uid:None,fetch_member=AsyncMock(side_effect=error))
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',new=AsyncMock(side_effect=error)):
            view=await self.ui.responsibility_view(10,guild)
            self.assertIn('Unknown user (10)',str(view.embed.to_dict()))

    async def test_roster_paginates_and_missing_members_have_fallback(self):
        with self.clock('2026-10-19T10:00:00'):
            for number in range(25):
                self.ui.create_chore('Chore '+str(number),'daily','0','')
            guild=SimpleNamespace(get_member=lambda uid:None)
            view=self.ui.ResponsibilityView(10,guild)
            self.assertLessEqual(len(view.embed.fields),3)
            self.assertIn('Account 10',str(view.embed.to_dict()))
            ids=[]
            for page in range(3):
                chunk=self.ui.ResponsibilityView(10,guild,page=page)
                ids.extend(r[1] for r in chunk.entries[chunk.page*12:(chunk.page+1)*12])
                self.assertLess(len(str(chunk.embed.to_dict())),6000)
            self.assertEqual(len(ids),27)
            self.assertEqual(len(set(ids)),27)

    async def test_dashboard_layout_is_consistent_for_saved_and_fresh_panels(self):
        expected=[('My chores',0),('Pick up chores',0),('Household',0),('Who’s home?',1),('Manage chores',1),('Help',1)]
        for timeout in [None,600]:
            view=self.ui.Launcher(timeout=timeout)
            self.assertEqual([(c.label,c.row) for c in view.children],expected)
            self.assertEqual([c.label for c in view.children if c.style==discord.ButtonStyle.primary],['My chores'])
            self.assertTrue(all(c.style==discord.ButtonStyle.secondary for c in view.children if c.label!='My chores'))
            self.assertEqual(len({c.custom_id for c in view.children}),6)

    async def test_reassign_occurrence_retains_points_history_and_blocks_stale(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES (1,'10')")
            self.db.execute("INSERT INTO users(id,points) VALUES ('10',25)")
            self.db.commit()
            before=self.db.execute('SELECT * FROM users').fetchall()
            expected=self.ui.reassign_snapshot(1)
            self.assertIn('reassigned',self.ui.reassign(1,20,'occurrence',expected))
            self.assertEqual(self.db.execute('SELECT user_id FROM claims WHERE quest_id=1').fetchone(),('20',))
            self.assertIn('changed',self.ui.reassign(1,30,'occurrence',expected))
            self.assertEqual(before,self.db.execute('SELECT * FROM users').fetchall())

    async def test_reassign_week_does_not_change_other_week_or_completion(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.ui.signup(30,1,self.ui.week_key(1))
            self.db.execute('UPDATE quests SET completed=1,last_completed=?,reset_after=? WHERE id=1',('2026-10-20T09:00:00-04:00','2026-10-21T00:00:00-04:00'))
            self.db.commit()
            before=self.db.execute('SELECT completed,last_completed,points FROM quests WHERE id=1').fetchone()
            self.assertIn('reassigned',self.ui.reassign(1,20,'week0',self.ui.reassign_snapshot(1)))
            self.assertEqual(self.ui.weekly_owner(1),'20')
            self.assertEqual(self.ui.weekly_owner(1,1),'30')
            self.assertEqual(before,self.db.execute('SELECT completed,last_completed,points FROM quests WHERE id=1').fetchone())

    async def test_reassign_checks_away_schedule_and_scope_conflicts(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO alternating_members VALUES ('20')")
            self.db.commit()
            self.assertIn('away',self.ui.reassign(1,20,'week0',self.ui.reassign_snapshot(1)))
            self.assertIn('reassigned',self.ui.reassign(1,20,'week1',self.ui.reassign_snapshot(1)))
            self.assertIn('weekly sign-ups',self.ui.reassign(1,10,'assignment',self.ui.reassign_snapshot(1)))
            self.assertIn('Ongoing assignment',self.ui.reassign(2,10,'week0',self.ui.reassign_snapshot(2)))

    async def test_reassign_ongoing_preserves_name_and_no_current_occurrence_bypass(self):
        with self.clock('2026-10-20T10:00:00'):
            self.assertIn('saved',self.ui.reassign(2,20,'assignment',self.ui.reassign_snapshot(2)))
            self.assertEqual(self.db.execute('SELECT name,assigned_to FROM quests WHERE id=2').fetchone(),('My bathroom','20'))
            self.assertIn('scope',self.ui.reassign(2,10,'occurrence',self.ui.reassign_snapshot(2)))
            self.ui.signup(10,1,self.ui.week_key())
            self.assertIn('scope',self.ui.reassign(1,20,'occurrence',self.ui.reassign_snapshot(1)))

    async def test_reassign_rejects_sunday_rollover_and_future_owner_change(self):
        with self.clock('2026-10-24T10:00:00'):
            expected=self.ui.reassign_snapshot(1)
            self.ui.signup(30,1,self.ui.week_key(1))
            self.assertIn('changed',self.ui.reassign(1,20,'week1',expected))
            expected=self.ui.reassign_snapshot(1)
        with self.clock('2026-10-25T18:00:00'):
            self.assertIn('changed',self.ui.reassign(1,20,'week0',expected))

    async def test_reassign_picker_confirms_only_a_human_in_this_server(self):
        with self.clock('2026-10-20T10:00:00'):
            expected=self.ui.reassign_snapshot(1)
            view=self.ui.ReassignView(10,qid=1,scope='week0',expected=expected)
            picker=next(c for c in view.children if isinstance(c,discord.ui.UserSelect))
            event=Interaction()
            picker._values=[SimpleNamespace(id=99,bot=True,guild=SimpleNamespace(id=1))]
            await picker.callback(event)
            self.assertIn('not a bot',event.response.payload[0][0])
            person=SimpleNamespace(id=20,bot=False,guild=SimpleNamespace(id=1),display_name='New person')
            picker._values=[person]
            await picker.callback(event)
            confirm=event.response.payload['view']
            self.assertIn('New person',str(confirm.embed.to_dict()))
            self.assertIsNone(self.ui.weekly_owner(1))
            await confirm.confirm(event)
            self.assertEqual(self.ui.weekly_owner(1),'20')
            self.assertIn('reassigned',event.result['content'])
            self.assertIsInstance(event.result['view'],self.ui.ReturnView)

    async def test_overview_groups_people_and_unclaimed_without_repeated_paragraphs(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Sweep kitchen','daily','5','')
            self.ui.create_chore('Morning room trash','days:tuesday,friday','5','')
            view=self.ui.ResponsibilityView(10,Interaction().guild)
            groups=[field for field in view.embed.fields if field.name=='Needs someone']
            self.assertEqual(len(groups),1)
            self.assertIn('Sweep kitchen',groups[0].value)
            self.assertIn('🟠 Tue / 🔵 Fri',groups[0].value)
            self.assertNotIn('Scheduled / outstanding next week',str(view.embed.to_dict()))
            self.assertNotIn('Nobody signed up',str(view.embed.to_dict()))
            self.assertLess(len(view.embed.description),400)
            self.assertTrue(all(len(field.value)<=1024 for field in view.embed.fields))

    async def test_reassign_private_ui_ownership_and_cancel(self):
        event=Interaction()
        view=self.ui.ReassignView(10)
        self.assertTrue(await view.interaction_check(event))
        self.assertFalse(await view.interaction_check(Interaction(20)))
        before=list(self.db.iterdump())
        await view.cancel(event)
        self.assertEqual(before,list(self.db.iterdump()))

    async def test_rainbow_days_match_legend_schedules_and_weekday_picker(self):
        from chore_timing import WEEKDAYS,DAY_COLORS,DAY_LEGEND
        colors=['🔴','🟠','🟡','🟢','🔵','🟣','🩷']
        self.assertEqual(list(DAY_COLORS.values()),colors)
        picker=self.ui.WeekdayMenu(10).children[0]
        for day,color,option in zip(WEEKDAYS,colors,picker.options):
            self.assertIn(color,self.ui.timing.label(day))
            self.assertIn(day.capitalize(),self.ui.timing.label(day))
            self.assertEqual(str(option.emoji),color)
        self.assertIn('🟠',self.ui.timing.label('days:tuesday,friday'))
        self.assertIn('🔵',self.ui.timing.label('days:tuesday,friday'))
        self.assertIn('🟣',self.ui.timing.label('away:saturday'))
        view=self.ui.ResponsibilityView(10,Interaction().guild)
        self.assertIn(DAY_LEGEND,view.embed.description)

    async def test_missed_policy_defaults_keep_and_weekday_skip_expires_at_midnight(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Tuesday cleanup','tuesday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Tuesday cleanup'").fetchone()[0]
            self.assertEqual(self.ui.timing.policy(qid),'keep')
            self.ui.signup(10,qid,self.ui.week_key())
            self.assertIn('Saved',self.ui.timing.set_policy(qid,'skip'))
        with self.clock('2026-10-20T23:59:59'):
            self.app.reset_due_quests()
            self.assertTrue(self.ui.ready(qid))
        with self.clock('2026-10-21T00:00:00'):
            self.app.reset_due_quests()
            self.assertFalse(self.ui.ready(qid))
            self.assertEqual(self.ui.weekly_owner(qid),'10')
            self.assertEqual(self.db.execute('SELECT completed,last_completed FROM quests WHERE id=?',(qid,)).fetchone(),(0,None))
        with self.clock('2026-10-27T00:00:00'):
            self.app.reset_due_quests()
            self.assertTrue(self.ui.ready(qid))

    async def test_keep_overdue_and_switch_to_skip_preserves_points(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Tuesday bins','tuesday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Tuesday bins'").fetchone()[0]
            self.db.execute('INSERT INTO claims VALUES (?,?)',(qid,'10'))
            self.db.execute("INSERT INTO users(id,points) VALUES ('10',30)")
            self.db.commit()
        with self.clock('2026-10-22T10:00:00'):
            self.app.reset_due_quests()
            self.assertTrue(self.ui.ready(qid))
            self.ui.timing.set_policy(qid,'skip')
            self.assertFalse(self.ui.ready(qid))
            self.assertIsNone(self.db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone())
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],30)

    async def test_daily_and_twice_daily_skip_only_release_expired_occurrence(self):
        for frequency,before,after in [('daily','2026-10-20T23:59:00','2026-10-21T00:00:00'),('twice-daily','2026-10-20T11:59:00','2026-10-20T12:00:00')]:
            with self.clock(before):
                self.db.execute('UPDATE quests SET frequency=? WHERE id=1',(frequency,))
                self.db.execute("INSERT OR REPLACE INTO claims VALUES (1,'10')")
                self.db.commit()
                self.ui.timing.set_policy(1,'skip')
                self.app.reset_due_quests()
                self.assertIsNotNone(self.db.execute('SELECT * FROM claims WHERE quest_id=1').fetchone())
            with self.clock(after):
                self.app.reset_due_quests()
                self.assertIsNone(self.db.execute('SELECT * FROM claims WHERE quest_id=1').fetchone())
                self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone()[0],0)

    async def test_skip_weekly_monthly_boundaries_and_one_time_rejected(self):
        for frequency,before,after in [('weekly','2026-10-25T17:59:00','2026-10-25T18:00:00'),('monthly','2026-10-31T23:59:00','2026-11-01T00:00:00')]:
            with self.clock(before):
                self.db.execute('UPDATE quests SET frequency=? WHERE id=1',(frequency,))
                self.db.execute("INSERT OR REPLACE INTO claims VALUES (1,'10')")
                self.db.commit()
                self.ui.timing.set_policy(1,'skip')
            with self.clock(after):
                self.app.reset_due_quests()
                self.assertIsNone(self.db.execute('SELECT * FROM claims WHERE quest_id=1').fetchone())
        self.db.execute("UPDATE quests SET frequency='one-time' WHERE id=1")
        self.db.commit()
        self.assertIn('no deadline',self.ui.timing.set_policy(1,'skip'))

    async def test_alternating_skip_persists_over_dst_and_downtime(self):
        with self.clock('2026-10-24T10:00:00'):
            self.ui.create_chore('Yard debris','away:saturday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Yard debris'").fetchone()[0]
            self.ui.timing.set_policy(qid,'skip')
        with self.clock('2026-11-08T10:00:00'):
            self.app.reset_due_quests()
            self.assertFalse(self.ui.ready(qid))
            self.assertTrue(self.ui.timing.state(qid)[0].startswith('2026-11-21T00:00:00-05:00'))
            from chore_timing import ChoreTiming
            loaded=ChoreTiming(vars(self.app),self.db)
            self.assertEqual(loaded.policy(qid),'skip')

    async def test_missed_policy_ui_stale_and_ownership_checks(self):
        event=Interaction()
        view=self.ui.MissedChoreView(10,1,self.ui.snapshot(1))
        self.assertFalse(await view.interaction_check(Interaction(20)))
        self.assertTrue(await view.interaction_check(event))
        self.ui.timing.set_policy(1,'skip')
        await view.children[0].callback(event)
        self.assertIn('changed',event.response.payload['content'])
        self.assertEqual(self.ui.timing.policy(1),'skip')

    async def test_day_colors_in_chore_lists_and_management_pickers(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Tuesday chore','tuesday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Tuesday chore'").fetchone()[0]
            for view in [self.ui.PersonalView(10),self.ui.WeeklyView(10),self.ui.EditChoreView(10),self.ui.RemoveChoreView(10),self.ui.ReassignView(10)]:
                picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
                option=next(o for o in picker.options if o.value==str(qid))
                self.assertEqual(str(option.emoji),'🟠')
                self.assertIn('Tue',option.description)
            personal=self.ui.PersonalView(10)
            self.assertIn('🟠 Tue',str(personal.embed.to_dict()))
            self.assertIn('dishwasher',self.ui.AddChoreModal(10,'tuesday').name.placeholder)
            self.assertIn('🟠',self.ui.AddChoreModal(10,'tuesday').title)
            daily_option=next(o for o in personal.children[0].options if o.value=='1')
            self.assertEqual(str(daily_option.emoji),'🟠')
            self.assertEqual(self.ui.timing.emoji('weekly'),'🤍')

    def setup_trade(self,weekly=False):
        self.ui.create_chore('Other chore','daily','7','')
        other=self.db.execute("SELECT id FROM quests WHERE name='Other chore'").fetchone()[0]
        if weekly:
            self.ui.signup(10,1,self.ui.week_key())
            self.ui.signup(20,other,self.ui.week_key())
        else:
            self.db.execute("INSERT INTO claims VALUES (1,'10')")
            self.db.execute('INSERT INTO claims VALUES (?,?)',(other,'20'))
            self.db.commit()
        return other

    async def test_my_chore_actions_and_private_inbox_are_available(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            view=self.ui.PersonalView(10,'mine',selected=1)
            labels=[c.label for c in view.children if isinstance(c,discord.ui.Button)]
            for name in ['Done','Drop','Reassign','Trade','Trade requests (0)']:
                self.assertIn(name,labels)
            for name in ['Drop','Reassign','Trade','Trade requests (0)']:
                event=Interaction()
                await next(c for c in view.children if getattr(c,'label',None)==name).callback(event)
                self.assertTrue(event.response.payload[1]['ephemeral'])

    async def test_drop_week_retains_other_weeks_history_and_points(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.ui.signup(10,1,self.ui.week_key(1))
            before=self.db.execute('SELECT * FROM quests WHERE id=1').fetchone()
            expected=self.ui.snapshot(1)
            self.assertIn('Dropped',self.ui.drop_chore(10,1,expected))
            self.assertIsNone(self.ui.weekly_owner(1))
            self.assertEqual(self.ui.weekly_owner(1,1),'10')
            self.assertEqual(before,self.db.execute('SELECT * FROM quests WHERE id=1').fetchone())
            self.assertIn('changed',self.ui.drop_chore(10,1,expected))

    async def test_drop_only_owner_and_confirm_or_cancel(self):
        with self.clock('2026-10-20T10:00:00'):
            self.setup_trade()
            expected=self.ui.snapshot(1)
            self.assertIn('no longer yours',self.ui.drop_chore(20,1,expected))
            view=self.ui.DropChoreView(10,1,expected)
            self.assertFalse(await view.interaction_check(Interaction(20)))
            event=Interaction()
            await view.children[1].callback(event)
            self.assertEqual(self.ui.owned_scope(1),('10','occurrence'))
            await view.children[0].callback(event)
            self.assertEqual(self.ui.owned_scope(1),(None,None))

    async def test_trade_proposal_waits_then_recipient_accepts_once(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.db.execute("INSERT INTO users(id,points) VALUES('10',40)")
            self.db.commit()
            before=self.db.execute('SELECT * FROM quests ORDER BY id').fetchall()
            self.assertIn('proposed',self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other)))
            self.assertEqual(self.ui.owned_scope(1),('10','occurrence'))
            self.assertIn('already waiting',self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other)))
            self.assertIn('Only the recipient',self.ui.respond_trade(10,1,'accept'))
            self.assertIn('accepted',self.ui.respond_trade(20,1,'accept'))
            self.assertEqual(self.ui.owned_scope(1),('20','occurrence'))
            self.assertEqual(self.ui.owned_scope(other),('10','occurrence'))
            self.assertEqual(before,self.db.execute('SELECT * FROM quests ORDER BY id').fetchall())
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],40)
            self.assertIn('no longer pending',self.ui.respond_trade(20,1,'accept'))

    async def test_weekly_trade_keeps_next_week_and_completion_history(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade(True)
            self.ui.signup(30,1,self.ui.week_key(1))
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.assertIn('accepted',self.ui.respond_trade(20,1,'accept'))
            self.assertEqual(self.ui.weekly_owner(1),'20')
            self.assertEqual(self.ui.weekly_owner(other),'10')
            self.assertEqual(self.ui.weekly_owner(1,1),'30')

    async def test_changed_chore_and_sunday_rollover_expire_trade(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.db.execute('UPDATE quests SET points=99 WHERE id=?',(other,))
            self.db.commit()
            self.assertIn('expired',self.ui.respond_trade(20,1,'accept'))
            self.assertEqual(self.ui.owned_scope(1)[0],'10')
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
        with self.clock('2026-10-25T18:00:00'):
            self.assertIn('expired',self.ui.respond_trade(20,2,'accept'))

    async def test_decline_cancel_and_away_trade_do_not_transfer(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.assertIn('declined',self.ui.respond_trade(20,1,'decline'))
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.assertIn('canceled',self.ui.respond_trade(10,2,'cancel'))
            self.db.execute("INSERT INTO alternating_members VALUES('20')")
            self.db.commit()
            self.assertNotIn('Trade proposed',self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other)))
            self.assertEqual(self.ui.owned_scope(1)[0],'10')

    async def test_trade_transaction_rolls_back_both_sides_on_failure(self):
        import sqlite3
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.db.execute(f"CREATE TRIGGER reject_swap BEFORE UPDATE ON claims WHEN NEW.quest_id={other} BEGIN SELECT RAISE(ABORT,'test failure'); END")
            self.db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                self.ui.respond_trade(20,1,'accept')
            self.assertEqual(self.ui.owned_scope(1)[0],'10')
            self.assertEqual(self.ui.owned_scope(other)[0],'20')
            self.assertEqual(self.db.execute('SELECT status FROM chore_trades WHERE id=1').fetchone()[0],'pending')

    async def test_trade_inbox_acceptance_private_view_and_ownership(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            inbox=self.ui.TradeInboxView(20,selected=1)
            self.assertFalse(await inbox.interaction_check(Interaction(30)))
            self.assertTrue(await inbox.interaction_check(Interaction(20)))
            event=Interaction(20)
            await next(c for c in inbox.children if getattr(c,'label',None)=='Accept trade').callback(event)
            self.assertIn('accepted',event.response.payload['content'])

    async def test_overview_chore_mode_is_alphabetical_and_identifies_owner(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            view=self.ui.ResponsibilityView(10,Interaction().guild,mode='chore')
            names=[entry[2][2] for entry in view.rendered]
            self.assertEqual(names,sorted(names,key=str.casefold))
            self.assertIn('Person 10',str(view.embed.to_dict()))
            self.assertIn('What’s being done',view.embed.title)

    async def test_overview_day_mode_separates_flexible_and_both_due_days(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Bins','days:tuesday,friday','5','')
            self.ui.create_chore('Wednesday fridge','wednesday','5','')
            view=self.ui.ResponsibilityView(10,Interaction().guild,mode='day')
            headings=[r[1] for r in view.rendered]
            self.assertIn('Every day',headings)
            self.assertIn('🤍 Any day this week',headings)
            self.assertIn('🟠 Tue · Oct 20',headings)
            self.assertIn('🟡 Wed · Oct 21',headings)
            self.assertIn('🔵 Fri · Oct 23',headings)
            self.assertEqual(sum(r[2][2]=='Bins' for r in view.rendered),2)
            self.assertLess(headings.index('🟠 Tue · Oct 20'),headings.index('🔵 Fri · Oct 23'))

    async def test_overview_modes_preserved_on_week_switch_and_reset_page(self):
        with self.clock('2026-10-20T10:00:00'):
            event=Interaction()
            view=self.ui.ResponsibilityView(10,event.guild)
            await next(c for c in view.children if c.label=='By day').callback(event)
            day_view=event.result['view']
            self.assertEqual(day_view.mode,'day')
            self.assertEqual(day_view.page,0)
            await next(c for c in day_view.children if getattr(c,'label',None)=='Next week').callback(event)
            self.assertEqual(event.result['view'].mode,'day')
            self.assertEqual(event.result['view'].offset,1)
            await next(c for c in event.result['view'].children if c.label=='By chore').callback(event)
            self.assertEqual(event.result['view'].offset,1)
            self.assertEqual(event.result['view'].mode,'chore')

    async def test_overview_modes_do_not_change_ownership_or_points(self):
        with self.clock('2026-10-20T10:00:00'):
            before=list(self.db.iterdump())
            for mode in ('person','chore','day'):
                view=self.ui.ResponsibilityView(10,Interaction().guild,mode=mode)
                self.assertTrue(all(len(f.value)<=1024 for f in view.embed.fields))
            self.assertEqual(before,list(self.db.iterdump()))

    async def test_choose_day_is_in_my_and_edit_weekly_chore(self):
        with self.clock('2026-10-20T10:00:00'):
            mine=self.ui.PersonalView(10,'mine',selected=2)
            edit=self.ui.EditChoreView(20,selected=2)
            for view in [mine,edit]:
                event=Interaction(view.owner)
                await next(c for c in view.children if getattr(c,'label',None)=='Change regular day').callback(event)
                self.assertTrue(event.response.payload[1]['ephemeral'])
                self.assertIn('Choose a recurring day',event.response.payload[1]['embed'].title)

    async def test_choose_day_confirm_preserves_points_signups_and_other_details(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.db.execute("UPDATE quests SET frequency='weekly' WHERE id=1")
            self.db.execute("INSERT INTO users(id,points) VALUES('10',50)")
            self.db.commit()
            expected=self.ui.snapshot(1)
            view=self.ui.ChooseDayView(20,1,expected)
            event=Interaction(20)
            view.children[0]._values=['friday']
            await view.children[0].callback(event)
            confirm=event.response.payload['view']
            self.assertIn('🔵 Friday',str(confirm.embed.to_dict()))
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=1').fetchone()[0],'weekly')
            await next(c for c in confirm.children if getattr(c,'label',None)=='Save day').callback(event)
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=1').fetchone()[0],'friday')
            self.assertEqual(self.ui.weekly_owner(1),'10')
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],50)
            self.assertEqual(self.db.execute('SELECT name,points FROM quests WHERE id=1').fetchone(),('Fill dishwasher',5))

    async def test_choose_day_rejects_stale_forms_and_cancel_is_noop(self):
        with self.clock('2026-10-20T10:00:00'):
            view=self.ui.ChooseDayView(10,2,self.ui.snapshot(2),'monday')
            self.assertFalse(await view.interaction_check(Interaction(20)))
            before=self.ui.snapshot(2)
            event=Interaction()
            await next(c for c in view.children if getattr(c,'label',None)=='Cancel').callback(event)
            self.assertEqual(before,self.ui.snapshot(2))
            self.db.execute("UPDATE quests SET notes='changed' WHERE id=2")
            self.db.commit()
            await next(c for c in view.children if getattr(c,'label',None)=='Save day').callback(event)
            self.assertIn('changed',event.response.payload['content'])
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=2').fetchone()[0],'weekly')

    async def test_home_exception_overrides_away_and_expires_inclusive(self):
        self.db.execute("INSERT INTO alternating_members VALUES('10')")
        self.db.commit()
        self.assertIn('Saved',self.ui.attendance.add(10,'2026-10-20','2026-10-21','home','Traded days'))
        for stamp,expected in [('2026-10-19T23:59:59',False),('2026-10-20T00:00:00',True),('2026-10-21T23:59:59',True),('2026-10-22T00:00:00',False),('2026-10-25T18:00:00',True)]:
            with self.clock(stamp):
                self.assertEqual(self.ui.available(10),expected,stamp)

    async def test_away_exception_blocks_claim_done_and_preserves_existing_owners(self):
        with self.clock('2026-10-26T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.db.execute("INSERT INTO claims VALUES(2,'10')")
            self.db.execute("INSERT INTO users(id,points) VALUES('10',50)")
            self.db.commit()
            self.ui.attendance.add(10,'2026-10-26','2026-10-28','away','Trip')
            self.app.reset_due_quests()
            self.assertFalse(self.ui.available(10))
            self.assertEqual(self.ui.weekly_owner(1),'10')
            self.assertEqual(self.db.execute('SELECT user_id FROM claims WHERE quest_id=2').fetchone()[0],'10')
            messages=[]
            async def send(message):
                messages.append(message)
            event=Interaction()
            ctx=SimpleNamespace(author=event.user,guild=event.guild,send=send)
            await self.app.bot.get_command('done').callback(ctx,1)
            self.assertIn('away',messages[-1])
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],50)
            self.assertIn('Check coverage',self.ui.coverage_warning(1,10))

    async def test_partial_week_signup_matches_actual_due_day(self):
        self.db.execute("INSERT INTO alternating_members VALUES('10')")
        self.db.commit()
        self.ui.attendance.add(10,'2026-10-20','2026-10-21','home')
        with self.clock('2026-10-19T10:00:00'):
            self.assertEqual(self.ui.week_status(10),'partial')
            self.ui.create_chore('Tuesday pickup','tuesday','5','')
            good=self.db.execute("SELECT id FROM quests WHERE name='Tuesday pickup'").fetchone()[0]
            self.ui.create_chore('Friday pickup','friday','5','')
            bad=self.db.execute("SELECT id FROM quests WHERE name='Friday pickup'").fetchone()[0]
            self.assertIn('signed up',self.ui.signup(10,good,self.ui.week_key()))
            self.assertIn('away on a scheduled',self.ui.signup(10,bad,self.ui.week_key()))
            self.assertIn('Check coverage',self.ui.signup(10,1,self.ui.week_key()))

    async def test_exception_overlap_duplicate_and_invalid_dates_are_rejected(self):
        a=self.ui.attendance
        self.assertIn('Saved',a.add(10,'2026-10-20','2026-10-22','away'))
        self.assertIn('already saved',a.add(10,'2026-10-20','2026-10-22','away'))
        self.assertIn('overlap',a.add(10,'2026-10-21','2026-10-23','home'))
        self.assertIn('Use dates',a.add(10,'2026-02-30','2026-03-01','home'))
        self.assertIn('date range',a.add(10,'2026-10-23','2026-10-20','home'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM availability_exceptions').fetchone()[0],1)

    async def test_exception_sunday_handoff_dst_and_separate_people(self):
        self.db.execute("INSERT INTO alternating_members VALUES('10')")
        self.db.execute("INSERT INTO alternating_members VALUES('20')")
        self.db.commit()
        self.ui.attendance.add(10,'2026-11-01','2026-11-01','home')
        with self.clock('2026-11-01T18:01:00'):
            self.assertTrue(self.ui.available(10))
            self.assertFalse(self.ui.available(20))
        with self.clock('2026-11-02T00:00:00'):
            self.assertFalse(self.ui.available(10))

    async def test_attendance_modal_private_save_and_coverage_notice(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            modal=self.ui.AttendanceModal(20,10,'Kas','away')
            modal.start._value='2026-10-20'
            modal.end._value='2026-10-21'
            modal.note._value='Trip'
            event=Interaction(20)
            await modal.on_submit(event)
            self.assertTrue(event.response.payload[1]['ephemeral'])
            self.assertIn('Responsibilities to review',event.response.payload[0][0])
            self.assertEqual(self.ui.weekly_owner(1),'10')

    async def test_attendance_ui_cancel_restores_rotation_without_deleting_record(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.attendance.add(10,'2026-10-20','2026-10-21','away')
            view=self.ui.AttendanceView(20,10,'Kas',selected=1)
            self.assertFalse(await view.interaction_check(Interaction(30)))
            event=Interaction(20)
            self.assertTrue(await view.interaction_check(event))
            await next(c for c in view.children if getattr(c,'label',None)=='Confirm cancel exception').callback(event)
            self.assertTrue(self.ui.available(10))
            self.assertEqual(self.db.execute('SELECT active FROM availability_exceptions WHERE id=1').fetchone()[0],0)

    async def test_attendance_button_private_and_rejects_bot(self):
        event=Interaction()
        button=next(c for c in self.ui.Launcher().children if c.label=='Who’s home?')
        await button.callback(event)
        self.assertTrue(event.response.payload[1]['ephemeral'])
        view=event.response.payload[1]['view']
        view.children[0]._values=[SimpleNamespace(id=99,bot=True,guild=SimpleNamespace(id=1))]
        await view.children[0].callback(event)
        self.assertIn('not bots',event.response.payload[0][0])

    async def test_attendance_change_invalidates_pending_trade(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.ui.attendance.add(20,'2026-10-21','2026-10-22','away')
            self.assertIn('expired',self.ui.respond_trade(20,1,'accept'))
            self.assertEqual(self.ui.owned_scope(1)[0],'10')

    async def test_coverage_warnings_in_overview_and_weekly_views(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.ui.attendance.add(10,'2026-10-21','2026-10-22','away')
            view=self.ui.ResponsibilityView(10,Interaction().guild)
            self.assertIn('Check coverage',str(view.embed.to_dict()))
            weekly=self.ui.WeeklyView(10)
            self.assertIn('Partly home',weekly.embed.description)
            self.assertIn('Away',str(weekly.embed.to_dict()))

    async def test_current_week_signup_requires_a_remaining_home_day(self):
        self.ui.attendance.add(10,'2026-10-21','2026-10-25','away')
        with self.clock('2026-10-22T10:00:00'):
            self.assertEqual(self.ui.week_status(10),'partial')
            self.assertFalse(self.ui.can_take_week(10,1,0))
            self.assertNotIn('signed up',self.ui.signup(10,1,self.ui.week_key()))

    async def test_home_exception_account_state_persists_and_reassign_honors_due_day(self):
        import sqlite3
        self.db.execute("INSERT INTO alternating_members VALUES('20')")
        self.db.commit()
        self.ui.attendance.add(20,'2026-10-20','2026-10-20','home')
        with self.clock('2026-10-19T10:00:00'):
            self.ui.create_chore('Tuesday task','tuesday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Tuesday task'").fetchone()[0]
            self.assertIn('reassigned',self.ui.reassign(qid,20,'week0',self.ui.reassign_snapshot(qid)))
            other=sqlite3.connect(Path(self.temp.name)/'sprig.db')
            self.assertEqual(other.execute('SELECT state,start_date,end_date FROM availability_exceptions WHERE user_id=?',('20',)).fetchone(),('home','2026-10-20','2026-10-20'))
            other.close()

    def assert_screen_limits(self,view):
        self.assertLessEqual(len(view.children),25)
        for row in range(5):
            width=sum(5 if isinstance(item,(discord.ui.Select,discord.ui.UserSelect)) else 1 for item in view.children if item.row==row)
            self.assertLessEqual(width,5)
        if hasattr(view,'embed'):
            embed=view.embed
            self.assertLessEqual(len(embed),6000)
            self.assertLessEqual(len(embed.fields),25)
            for field in embed.fields:
                self.assertLessEqual(len(field.value),1024)
                self.assertLessEqual(len(field.name),256)

    async def test_audited_screens_have_dashboard_and_respect_discord_limits(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            for index in range(45):
                self.ui.create_chore(f'{index:02d} Long chore '+('x'*65),'weekly','5','n'*900)
            views=[self.ui.PersonalView(10),self.ui.PersonalView(10,'mine',selected=1),self.ui.WeeklyView(10,selected=1),self.ui.ReassignView(10,qid=1,scope='week0',expected=self.ui.reassign_snapshot(1)),self.ui.EditChoreView(10),self.ui.RemoveChoreView(10),self.ui.AttendanceView(10,10,'Kas'),self.ui.TradeOfferView(10,1),self.ui.TradeInboxView(10),self.ui.ChooseDayView(10,2,self.ui.snapshot(2)),self.ui.MissedChoreView(10,1,self.ui.snapshot(1))]
            for mode in ('person','chore','day'):
                views.append(self.ui.ResponsibilityView(10,Interaction().guild,mode=mode))
            for view in views:
                self.assertIn('Dashboard',[getattr(c,'label',None) for c in view.children],type(view).__name__)
                self.assert_screen_limits(view)

    async def test_my_chore_action_and_navigation_rows_are_separate_on_middle_page(self):
        with self.clock('2026-10-20T10:00:00'):
            for index in range(45):
                self.ui.create_chore(f'Task {index:02d}','weekly','5','')
            self.db.execute("UPDATE quests SET assigned_to='10'")
            self.db.commit()
            plain=self.ui.PersonalView(10,'mine',page=1)
            qid=plain.entries[20][0]
            view=self.ui.PersonalView(10,'mine',page=1,selected=qid)
            rows={getattr(c,'label',None):c.row for c in view.children if isinstance(c,discord.ui.Button)}
            self.assertTrue(all(rows[label]==1 for label in ['Done','Drop','Reassign','Trade']))
            self.assertEqual(rows['Change regular day'],2)
            self.assertEqual(rows['Back to list'],3)
            self.assertNotIn('My chores',rows)
            self.assertEqual(rows['Previous'],4)
            self.assertEqual(rows['Dashboard'],4)
            self.assert_screen_limits(view)

    async def test_selected_chore_remains_highlighted_in_lists(self):
        with self.clock('2026-10-20T10:00:00'):
            for view in [self.ui.PersonalView(10,selected=1),self.ui.WeeklyView(10,selected=1),self.ui.EditChoreView(10,selected=1),self.ui.RemoveChoreView(10,selected=1)]:
                picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
                self.assertTrue(next(option for option in picker.options if option.value=='1').default)

    async def test_away_empty_state_does_not_claim_work_is_finished(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.attendance.add(10,'2026-10-20','2026-10-20','away')
            view=self.ui.PersonalView(10,'mine')
            self.assertIn('Away today',str(view.embed.to_dict()))
            self.assertIn('remain saved',str(view.embed.to_dict()))
            self.assertNotIn('All clear',str(view.embed.to_dict()))

    async def test_dashboard_back_navigation_never_changes_data(self):
        event=Interaction()
        view=self.ui.PersonalView(10)
        before=list(self.db.iterdump())
        await next(c for c in view.children if getattr(c,'label',None)=='Dashboard').callback(event)
        self.assertIsInstance(event.response.payload['view'],self.ui.workspace.Dashboard)
        self.assertEqual(event.response.payload['embed'].title,'🌱 Your chore workspace')
        self.assertEqual(before,list(self.db.iterdump()))

    async def test_help_topics_are_short_private_and_navigable(self):
        event=Interaction()
        view=self.ui.HelpView(10)
        self.assertLess(len(view.embed),1800)
        picker=view.children[0]
        for option in picker.options:
            picker._values=[option.value]
            await picker.callback(event)
            topic=event.response.payload['view']
            self.assertLess(len(topic.embed),1800)
            self.assertIn('Dashboard',[getattr(c,'label',None) for c in topic.children])
        self.assertFalse(await view.interaction_check(Interaction(20)))

    async def test_completed_weekly_day_preview_uses_actual_next_occurrence(self):
        with self.clock('2026-10-20T12:00:00'):
            self.db.execute("UPDATE quests SET completed=1,last_completed='2026-10-20T10:00:00-04:00' WHERE id=2")
            self.db.commit()
            view=self.ui.ChooseDayView(10,2,self.ui.snapshot(2),'tuesday')
            self.assertIn('Oct 27',str(view.embed.to_dict()))

    async def test_missed_setting_identifies_current_choice_and_disables_impossible_skip(self):
        view=self.ui.MissedChoreView(10,1,self.ui.snapshot(1))
        self.assertIn('Current: Keep overdue',view.embed.description)
        self.db.execute("UPDATE quests SET frequency='one-time' WHERE id=1")
        self.db.commit()
        one_time=self.ui.MissedChoreView(10,1,self.ui.snapshot(1))
        self.assertTrue(next(c for c in one_time.children if getattr(c,'label',None)=='Skip if missed').disabled)
        self.assert_screen_limits(one_time)

    async def test_active_tab_and_clean_completion_notice(self):
        with self.clock('2026-10-20T10:00:00'):
            view=self.ui.PersonalView(10)
            self.assertNotIn('Open chores',[getattr(c,'label',None) for c in view.children])
            event=Interaction()
            await self.ui.PersonalView(10,selected=1).act(event,'claim')
            self.assertIn('Added to My chores',event.response.payload['embed'].description)
            await self.ui.PersonalView(10,'mine',selected=1).act(event,'done')
            self.assertIn('+5 points',event.response.payload['embed'].description)
            self.assertNotIn('quest #',event.response.payload['embed'].description)

    async def test_feedback_preserves_points_schedule_and_ownership(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            self.db.execute("INSERT INTO users(id,points) VALUES('10',50)")
            self.db.commit()
            before=self.db.execute('SELECT * FROM quests ORDER BY id').fetchall()
            result=self.ui.save_feedback(1,10,'Kas','Takes longer than expected','Friday afternoon','8','review-one',self.ui.feedback_context(1))
            self.assertIn('Feedback saved',result)
            self.assertEqual(before,self.db.execute('SELECT * FROM quests ORDER BY id').fetchall())
            self.assertEqual(self.ui.weekly_owner(1),'10')
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],50)
            self.assertEqual(self.db.execute('SELECT comment,timing,suggested_points FROM chore_feedback').fetchone(),('Takes longer than expected','Friday afternoon',8))

    async def test_feedback_latest_vote_per_person_and_retry_deduplication(self):
        context=self.ui.feedback_context(1)
        self.ui.save_feedback(1,10,'Kas','','','3','vote-a',context)
        self.assertIn('already saved',self.ui.save_feedback(1,10,'Kas','','','3','vote-a',context))
        self.ui.save_feedback(1,10,'Kas','Changed my mind','','8','vote-b',context)
        self.ui.save_feedback(1,20,'Zel','','','0','vote-c',context)
        self.assertEqual(self.ui.feedback_votes(1),[('10','Kas',8),('20','Zel',0)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM chore_feedback').fetchone()[0],3)

    async def test_feedback_invalid_inputs_do_not_write_and_comments_need_no_vote(self):
        context=self.ui.feedback_context(1)
        for points in ('-1','3.5','lots','1000001'):
            self.ui.save_feedback(1,10,'Kas','Idea','',points,'bad-'+points,context)
        self.assertIn('Add a comment',self.ui.save_feedback(1,10,'Kas','','','','empty',context))
        self.assertEqual(self.db.execute('SELECT count(*) FROM chore_feedback').fetchone()[0],0)
        self.assertIn('saved',self.ui.save_feedback(1,10,'Kas','','Thursday evening','','timing',context))
        self.assertEqual(self.ui.feedback_votes(1),[])

    async def test_feedback_modal_permissions_private_and_original_context(self):
        modal=self.ui.FeedbackModal(10,1,'13')
        modal.comment._value='Needs clearer instructions'
        modal.timing._value=''
        modal.points._value='13'
        other=Interaction(20)
        await modal.on_submit(other)
        self.assertEqual(self.db.execute('SELECT count(*) FROM chore_feedback').fetchone()[0],0)
        self.db.execute("UPDATE quests SET name='New dishwasher name',points=8 WHERE id=1")
        self.db.commit()
        event=Interaction()
        await modal.on_submit(event)
        self.assertTrue(event.response.payload[1]['ephemeral'])
        import json
        context=json.loads(self.db.execute('SELECT context FROM chore_feedback').fetchone()[0])
        self.assertEqual((context[0],context[2]),('Fill dishwasher',5))
        self.assertEqual(self.db.execute('SELECT points FROM quests WHERE id=1').fetchone()[0],8)

    async def test_feedback_buttons_on_all_chore_entry_points(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            for view in [self.ui.PersonalView(10,'mine',selected=1),self.ui.WeeklyView(10,selected=1),self.ui.EditChoreView(20,selected=1)]:
                event=Interaction(view.owner)
                await next(c for c in view.children if getattr(c,'label',None)=='Chore review').callback(event)
                self.assertTrue(event.response.payload[1]['ephemeral'])
                self.assertIsInstance(event.response.payload[1]['view'],self.ui.FeedbackView)

    async def test_feedback_reviewed_history_pagination_full_text_and_limits(self):
        context=self.ui.feedback_context(1)
        for number in range(8):
            self.ui.save_feedback(1,10,'Kas','*'*1000,'x'*200,'8','long-'+str(number),context)
        view=self.ui.FeedbackView(301104023405199361,1,selected=8)
        self.assert_screen_limits(view)
        event=Interaction(301104023405199361)
        self.assertFalse(await view.interaction_check(Interaction(30)))
        await next(c for c in view.children if getattr(c,'label',None)=='Resolve review').callback(event)
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback WHERE id=8').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM chore_feedback').fetchone()[0],8)
        all_view=self.ui.FeedbackView(301104023405199361,1,all_reviews=True,selected=8)
        self.assertIn('Reviewed',str(all_view.embed.to_dict()))
        self.assert_screen_limits(all_view)
        self.assertIn('Next',[getattr(c,'label',None) for c in self.ui.FeedbackView(301104023405199361,1).children])

    async def test_feedback_rejects_archived_chore_and_score_picker_is_optional(self):
        view=self.ui.FeedbackView(10,1)
        picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
        picker._values=['5']
        event=Interaction()
        await picker.callback(event)
        self.assertEqual(event.response.payload.points.default,'5')
        self.db.execute("INSERT INTO archived_chores VALUES(1,'10','test')")
        self.db.commit()
        self.assertIn('no longer',self.ui.save_feedback(1,10,'Kas','Idea','','5','archived',self.ui.feedback_context(1)))
        self.assertEqual(self.db.execute('SELECT count(*) FROM chore_feedback').fetchone()[0],0)

    async def test_chore_lists_do_not_repeat_the_current_list_name_as_a_button(self):
        for mode,current,other in [('mine','My chores','Open chores'),('open','Open chores','My chores')]:
            view=self.ui.PersonalView(10,mode)
            buttons={c.label:c for c in view.children if isinstance(c,discord.ui.Button)}
            self.assertNotIn(current,buttons)
            self.assertIn(other,buttons)
            self.assertIn('Dashboard',buttons)
            self.assertIn('Refresh',buttons)
            self.assertNotIn('Back to list',buttons)

    async def test_selected_chore_back_to_list_stays_in_the_same_list(self):
        event=Interaction()
        view=self.ui.PersonalView(10,'mine',selected=2)
        self.assertNotIn('My chores',[getattr(c,'label',None) for c in view.children])
        await next(c for c in view.children if getattr(c,'label',None)=='Back to list').callback(event)
        self.assertFalse(event.response.acknowledged)
        self.assertIsNone(event.result)
        self.assertEqual(event.response.payload['view'].mode,'mine')
        self.assertIsNone(event.response.payload['view'].selected)
        self.assertNotIn('Back to list',[getattr(c,'label',None) for c in event.response.payload['view'].children])

    async def test_stale_done_click_does_not_claim_another_points_award(self):
        with self.clock('2026-10-20T10:00:00'):
            first=self.ui.PersonalView(10,'mine',selected=2)
            stale=self.ui.PersonalView(10,'mine',selected=2)
            await first.act(Interaction(),'done')
            event=Interaction()
            await stale.act(event,'done')
            self.assertIn('changed',event.response.payload['embed'].description)
            self.assertNotIn('+10 points',event.response.payload['embed'].description)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone()[0],10)

    async def test_weekly_monthly_dots_are_distinct_from_weekday_colors(self):
        from chore_timing import DAY_COLORS,DAY_LEGEND
        for frequency,dot in [('weekly','🤍'),('monthly','🟫')]:
            self.assertNotIn(dot,DAY_COLORS.values())
            self.assertIn(dot,self.ui.timing.compact_label(frequency))
            self.assertIn(dot,self.ui.timing.label(frequency))
            self.assertEqual(self.ui.timing.emoji(frequency),dot)
            self.assertIn(dot,DAY_LEGEND)
        menu=self.ui.AddChoreMenu(10)
        options=menu.children[0].options
        self.assertEqual(str(next(o for o in options if o.value=='weekly').emoji),'🤍')
        self.assertEqual(str(next(o for o in options if o.value=='monthly').emoji),'🟫')

    async def test_feedback_dm_targets_owner_once_and_contains_full_review(self):
        context=self.ui.feedback_context(1)
        self.ui.save_feedback(1,10,'Kas','Needs instructions','Friday','8','dm-once',context)
        await self.ui.notify_feedback('dm-once')
        await self.ui.notify_feedback('dm-once')
        self.app.bot.get_user.assert_called_once_with(301104023405199361)
        self.dm.send.assert_awaited_once()
        embed=self.dm.send.call_args.kwargs['embed']
        text=str(embed.to_dict())
        for value in ['Kas','Needs instructions','Friday','8','Fill dishwasher']:
            self.assertIn(value,text)
        self.assertEqual(self.db.execute('SELECT status FROM feedback_notifications').fetchone(),('sent',))

    async def test_blocked_dm_preserves_inbox_without_retrying(self):
        self.ui.save_feedback(1,10,'Kas','Idea','','','dm-blocked',self.ui.feedback_context(1))
        self.dm.send.side_effect=RuntimeError('blocked')
        await self.ui.notify_feedback('dm-blocked')
        await self.ui.notify_feedback('dm-blocked')
        self.dm.send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT status FROM feedback_notifications').fetchone(),('failed_or_uncertain',))
        view=self.ui.ReviewInbox(301104023405199361)
        self.assertIn('Fill dishwasher',str(view.embed.to_dict()))
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback').fetchone(),(0,))

    async def test_owner_inbox_permissions_pagination_and_reviewed_history(self):
        for i in range(8):
            self.db.execute("INSERT INTO quests(name) VALUES (?)",(f'Review task {i}',))
            qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
            self.ui.save_feedback(qid,10,'Kas','Idea','','','inbox-'+str(i),self.ui.feedback_context(qid))
        view=self.ui.ReviewInbox(301104023405199361)
        self.assertEqual(len(view.embed.fields),5)
        self.assertIn('Next',[getattr(c,'label',None) for c in view.children])
        self.assertFalse(await view.interaction_check(Interaction(10)))
        self.assertTrue(await view.interaction_check(Interaction(301104023405199361)))
        self.assertFalse(self.ui.ReviewInbox(10).children[0].__class__ is discord.ui.Select)
        with self.db:
            self.db.execute('UPDATE chore_feedback SET reviewed=1')
        self.assertIn('All caught up',str(self.ui.ReviewInbox(301104023405199361).embed.to_dict()))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_feedback').fetchone()[0],8)

    async def test_review_inbox_launcher_is_private_and_rejects_other_people(self):
        self.assertNotIn('Review inbox',[c.label for c in self.ui.Launcher().children])
        self.assertFalse(any(c.label.startswith('Review inbox') for c in self.ui.workspace.Dashboard(10).children))
        view=self.ui.workspace.Dashboard(301104023405199361)
        button=next(c for c in view.children if c.label.startswith('Review inbox'))
        event=Interaction(301104023405199361)
        await button.callback(event)
        self.assertIsInstance(event.response.payload['view'],self.ui.workspace.Inbox)
        self.assertFalse(await event.response.payload['view'].interaction_check(Interaction(10)))

    async def test_workspace_personal_upcoming_includes_future_responsibilities(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Friday laundry','friday','5','Bedroom')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Friday laundry'").fetchone()[0]
            self.db.execute('UPDATE quests SET assigned_to=? WHERE id=?',('10',qid));self.db.commit()
            self.assertNotIn(qid,[r[0] for r in self.ui.workspace.Browse(10,'mine').entries])
            self.assertIn(qid,[r[0] for r in self.ui.workspace.Browse(10,'mine',tab='upcoming').entries])
            self.assertIn(qid,[r[0] for r in self.ui.workspace.Browse(10,'mine',tab='week').entries])
            card=self.ui.workspace.Card(10,qid)
            self.assertNotIn('Done',[getattr(c,'label',None) for c in card.children])

    async def test_workspace_next_week_reservations_visible_before_due(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key(1))
            self.assertIn(1,[r[0] for r in self.ui.workspace.Browse(10,'mine',tab='next').entries])
            self.assertIn(1,[r[0] for r in self.ui.workspace.Browse(10,'mine',tab='upcoming').entries])
            self.assertIn('Next week',self.ui.workspace.Browse(10,'mine',tab='next').embed.description)

    async def test_workspace_chore_card_claim_done_and_safe_history(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace
            first=w.Card(10,1);event=Interaction()
            await next(c for c in first.children if getattr(c,'label',None)=='Just this time').callback(event)
            claimed=(event.result or event.response.payload)['view'];self.assertIsInstance(claimed,w.Card)
            second=Interaction();await next(c for c in claimed.children if getattr(c,'label',None)=='Done').callback(second)
            self.assertEqual(self.db.execute('SELECT points FROM users WHERE id=?',('10',)).fetchone(),(5,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            result=self.ui.undo_completion(10,1)
            self.assertIn('undone',result)
            self.assertEqual(self.db.execute('SELECT points FROM users WHERE id=?',('10',)).fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT user_id FROM claims WHERE quest_id=1').fetchone(),('10',))
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(0,))
            self.assertNotIn('undone.',self.ui.undo_completion(10,1))

    async def test_history_undo_rejects_other_user_changed_points_and_rollover(self):
        with self.clock('2026-10-20T10:00:00'):
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            self.assertIn('no longer',self.ui.undo_completion(20,1))
            self.db.execute("UPDATE users SET points=points+10 WHERE id='10'");self.db.commit()
            self.assertIn('changed',self.ui.undo_completion(10,1))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(15,))
        with self.clock('2026-10-21T10:00:00'):
            self.assertIn('changed',self.ui.undo_completion(10,1))

    async def test_history_undo_most_recent_and_streak_preserved(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO users VALUES('10',40,3,'2026-10-19T10:00:00-04:00')");self.db.commit()
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
            self.assertIn('most recent',self.ui.undo_completion(10,1))
            self.assertIn('undone',self.ui.undo_completion(10,2))
            self.assertIn('undone',self.ui.undo_completion(10,1))
            self.assertEqual(self.db.execute("SELECT points,streak,last_completed FROM users WHERE id='10'").fetchone(),(40,3,'2026-10-19T10:00:00-04:00'))

    async def test_history_write_failure_rolls_back_award_and_completion(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO users(id,points) VALUES('10',12)")
            self.db.execute("INSERT INTO claims VALUES(1,'10')")
            self.db.execute("CREATE TRIGGER reject_history BEFORE INSERT ON completion_log BEGIN SELECT RAISE(ABORT,'simulated disk error'); END;");self.db.commit()
            with self.assertRaises(Exception):await self.app.bot.get_command('done').callback(SimpleNamespace(author=SimpleNamespace(id=10,display_name='Kas'),send=AsyncMock()),1)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(12,))
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT user_id FROM claims WHERE quest_id=1').fetchone(),('10',))

    async def test_workspace_search_room_person_and_unclaimed_filters(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Sweep kitchen','daily','5','Under table','Kitchen')
            w=self.ui.workspace
            self.assertEqual([r[1] for r in w.Browse(10,'household',tab='all',query='under table').entries],['Sweep kitchen'])
            self.assertEqual([r[1] for r in w.Browse(10,'household',tab='all',room='Kitchen').entries],['Sweep kitchen'])
            self.assertEqual([r[0] for r in w.Browse(10,'household',tab='all',person_id=10).entries],[2])
            self.assertNotIn(2,[r[0] for r in w.Browse(10,'household',tab='all',unclaimed=True).entries])
            self.assertEqual(self.db.execute('SELECT category FROM quests WHERE id=2').fetchone(),('general',))

    async def test_workspace_household_chore_selection_opens_same_card(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=w.Browse(10,'household',tab='all');event=Interaction()
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['1']
            await picker.callback(event)
            self.assertIsInstance(event.response.payload['view'],w.Card)
            self.assertEqual(event.response.payload['view'].qid,1)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Back').callback(event)
            self.assertIsInstance(event.response.payload['view'],w.Browse)
            self.assertEqual(event.response.payload['view'].state['area'],'household')

    async def test_workspace_browse_preferences_remembered_per_person(self):
        w=self.ui.workspace
        w.Browse(10,'household',tab='all',group='person',query='bath')
        event=Interaction();await next(c for c in w.Dashboard(10).children if c.label=='Household').callback(event)
        self.assertEqual(event.response.payload['view'].state['query'],'bath')
        self.assertNotIn((20,'household'),w.memory)

    async def test_workspace_context_edit_replaces_current_private_message(self):
        view=self.ui.workspace.adapt(self.ui.EditChoreView(10,selected=1),10,lambda:self.ui.workspace.Card(10,1))
        event=Interaction()
        await next(c for c in view.children if getattr(c,'label',None)=='Change schedule').callback(event)
        self.assertIsInstance(event.response.payload,dict)
        self.assertIsInstance(event.response.payload['view'],self.ui.AddChoreMenu)
        self.assertIn('Back',[getattr(c,'label',None) for c in event.response.payload['view'].children])

    async def test_workspace_review_only_owner_can_resolve(self):
        context=self.ui.feedback_context(1);self.ui.save_feedback(1,10,'Kas','Need more time','','8','owner-only',context)
        nonowner=self.ui.FeedbackView(10,1,selected=1)
        self.assertNotIn('Resolve review',[getattr(c,'label',None) for c in nonowner.children])
        self.assertFalse(await self.ui.workspace.Inbox(10).interaction_check(Interaction(10)))
        owner=self.ui.workspace.Inbox(301104023405199361);event=Interaction(301104023405199361)
        await next(c for c in owner.children if getattr(c,'label',None)=='Resolve and next').callback(event)
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback').fetchone(),(1,))
        self.assertIn('All caught up',event.response.payload['embed'].description)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_feedback').fetchone(),(1,))

    async def test_workspace_owner_tools_hidden_from_other_people(self):
        w=self.ui.workspace
        labels=lambda v:[c.label for c in v.children if isinstance(c,discord.ui.Button)]
        self.assertFalse(any(l.startswith('Review inbox') for l in labels(w.Dashboard(10))))
        self.assertTrue(any(l.startswith('Review inbox') for l in labels(w.Dashboard(301104023405199361))))
        self.assertNotIn('Household setup',labels(w.Dashboard(10,Interaction().guild)))

    async def test_workspace_multi_person_trip_preview_and_edit_keeps_history(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;first=w.parse_date('today');last=w.parse_date('tomorrow')
            self.assertIn('Saved',w.save_trip(['10','20'],first,last,'away','Trip'))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM availability_exceptions WHERE active=1').fetchone(),(2,))
            record=self.db.execute('SELECT id,user_id,start_date,end_date,state,note,active FROM availability_exceptions WHERE user_id=?',('10',)).fetchone()
            self.assertIn('Saved',w.save_trip(['10'],first,last+timedelta(days=1),'away','Longer trip',record[0],record))
            self.assertEqual(self.db.execute('SELECT active FROM availability_exceptions WHERE id=?',(record[0],)).fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM availability_exceptions').fetchone(),(3,))
            self.assertIn('changed',w.save_trip(['10'],first,last,'home','stale',record[0],record))

    async def test_workspace_trip_overlap_rolls_back_entire_group(self):
        w=self.ui.workspace;first=w.parse_date('2026-10-24');last=w.parse_date('2026-10-26')
        w.save_trip(['20'],first,last,'away','Existing')
        self.assertIn('overlap',w.save_trip(['10','20'],first,last,'home','New'))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM availability_exceptions WHERE user_id='10'").fetchone(),(0,))
        self.assertIn('already saved',w.save_trip(['20'],first,last,'away','Existing'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM availability_exceptions').fetchone(),(1,))

    async def test_workspace_trip_modal_preview_does_not_save_before_confirmation(self):
        w=self.ui.workspace;modal=w.TripModal(10,['10','20'],'away',lambda:w.Trips(10))
        modal.first._value='2026-10-24';modal.last._value='2026-10-26';modal.note._value='Trip'
        event=Interaction();await modal.on_submit(event)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM availability_exceptions').fetchone(),(0,))
        confirmation=event.response.payload['view']
        await next(c for c in confirmation.children if getattr(c,'label',None)=='Confirm').callback(event)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM availability_exceptions').fetchone(),(2,))

    async def test_workspace_move_only_one_occurrence_retains_frequency(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;modal=w.MoveModal(10,1,self.ui.snapshot(1),lambda:w.Card(10,1))
            modal.day._value='tomorrow';event=Interaction();await modal.on_submit(event)
            self.assertIsNone(self.db.execute('SELECT day FROM occurrence_moves WHERE quest_id=1').fetchone())
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
            self.assertFalse(self.ui.ready(1))
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=1').fetchone(),('daily',))
        with self.clock('2026-10-21T10:00:00'):
            self.assertTrue(self.ui.ready(1))
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            self.assertIsNone(self.db.execute('SELECT day FROM occurrence_moves WHERE quest_id=1').fetchone())

    async def test_workspace_trade_notifications_are_opt_in_and_deduplicated(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'20')");self.db.commit()
            text=self.ui.propose_trade(10,2,1,self.ui.trade_snapshot(2),self.ui.trade_snapshot(1));self.assertIn('proposed',text)
            await self.ui.workspace.notify_trade(1);self.dm.send.assert_not_awaited()
            self.db.execute("INSERT INTO notification_preferences VALUES('20',1)");self.db.commit()
            await self.ui.workspace.notify_trade(1);await self.ui.workspace.notify_trade(1)
            self.dm.send.assert_awaited_once();self.app.bot.get_user.assert_called_once_with(20)

    async def test_workspace_notification_toggle_is_personal_and_opt_in(self):
        w=self.ui.workspace;view=w.Notifications(10)
        self.assertIn('off',view.embed.description)
        self.assertFalse(await view.interaction_check(Interaction(20)))
        event=Interaction();await next(c for c in view.children if getattr(c,'label',None)=='Turn trade DMs on').callback(event)
        self.assertEqual(self.db.execute('SELECT user_id,trade_dm FROM notification_preferences').fetchone(),('10',1))

    async def test_workspace_legacy_delete_archives_and_reset_cannot_duplicate_awards(self):
        context=SimpleNamespace(author=SimpleNamespace(id=10),send=AsyncMock())
        await self.app.bot.get_command('deletequest').callback(context,1)
        self.assertTrue(self.ui.is_archived(1))
        self.assertIsNotNone(self.db.execute('SELECT id FROM quests WHERE id=1').fetchone())
        self.db.execute('UPDATE quests SET completed=1 WHERE id=2');self.db.commit()
        await self.app.bot.get_command('resetquest').callback(context,2)
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(1,))

    async def test_workspace_all_screens_and_large_data_respect_discord_limits(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for n in range(35):self.ui.create_chore(f'Long chore {n:02} '+'x'*65,'daily','5','*'*900,'Kitchen')
            for area in ('mine','pickup','household'):
                for tab in ('due','week','next','all'):
                    for group in ('person','chore','day'):
                        self.assert_screen_limits(w.Browse(10,area,tab=tab,group=group,page=1))
            for view in (w.Dashboard(10),w.Dashboard(301104023405199361),w.Card(10,1),w.Manage(10),w.Trips(10,people=['10','20']),w.Inbox(301104023405199361),w.Guide(10),w.History(10,1,lambda:w.Card(10,1))):
                self.assert_screen_limits(view)


    async def test_workspace_same_card_fast_path_has_one_response(self):
        with self.clock('2026-10-20T10:00:00'):
            card=self.ui.workspace.Card(10,1);event=Interaction()
            await next(c for c in card.children if getattr(c,'label',None)=='Just this time').callback(event)
            self.assertFalse(event.response.acknowledged)
            self.assertIsInstance(event.response.payload['view'],self.ui.workspace.Card)

    async def test_workspace_paired_days_are_both_actionable_and_uniquely_counted(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Morning room trash','days:tuesday,friday','5','')
            view=self.ui.workspace.Browse(10,'household',group='day')
            headings=[f.name for f in view.embed.fields if 'Morning room trash' in f.name]
            self.assertEqual(len(headings),2)
            self.assertTrue(any('🟠 Tue' in h for h in headings))
            self.assertTrue(any('🔵 Fri' in h for h in headings))
            self.assertEqual(len(view.entries),3)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
            self.assertEqual(len({o.value for o in picker.options}),len(picker.options))

    async def test_workspace_exact_date_filter_excludes_flexible_unset_days(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Friday car cleanup','friday','5','')
            view=self.ui.workspace.Browse(10,'household',tab='all',date_filter='2026-10-23')
            self.assertIn('Friday car cleanup',[q[1] for q in view.entries])
            self.assertNotIn(2,[q[0] for q in view.entries])
            self.assertNotIn('Friday car cleanup',[q[1] for q in self.ui.workspace.Browse(10,'household',tab='all',date_filter='2026-10-22').entries])

    async def test_workspace_move_checks_stale_forms_and_restores_on_undo(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;expected=self.ui.snapshot(1)
            first=w.MoveModal(10,1,expected,lambda:w.Card(10,1));first.day._value='today'
            event=Interaction();await first.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
            stale=w.MoveModal(10,1,expected,lambda:w.Card(10,1));stale.day._value='tomorrow'
            event=Interaction();await stale.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
            self.assertEqual(self.db.execute('SELECT day FROM occurrence_moves').fetchone(),('2026-10-20',))
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            self.assertIn('undone',self.ui.undo_completion(10,1))
            self.assertEqual(self.db.execute('SELECT day FROM occurrence_moves').fetchone(),('2026-10-20',))

    async def test_workspace_skip_policy_respects_future_moved_occurrence(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.timing.set_policy(1,'skip')
            w=self.ui.workspace;modal=w.MoveModal(10,1,self.ui.snapshot(1),lambda:w.Card(10,1));modal.day._value='2026-10-23'
            event=Interaction();await modal.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
        with self.clock('2026-10-22T10:00:00'):
            self.app.reset_due_quests()
            self.assertFalse(self.ui.ready(1))
            self.assertEqual(self.db.execute('SELECT day FROM occurrence_moves').fetchone(),('2026-10-23',))

    async def test_workspace_room_field_creates_and_edits_correct_chore(self):
        modal=self.ui.AddChoreModal(10,'daily');modal.name._value='Kitchen counters';modal.notes._value='Wipe';modal.points._value='5';modal.room._value='Kitchen'
        await modal.on_submit(Interaction())
        qid=self.db.execute("SELECT id FROM quests WHERE name='Kitchen counters'").fetchone()[0]
        self.assertEqual(self.db.execute('SELECT category FROM quests WHERE id=?',(qid,)).fetchone(),('Kitchen',))
        edit=self.ui.EditChoreModal(10,qid,'daily',self.ui.snapshot(qid));edit.name._value='Kitchen counters';edit.notes._value='Wipe';edit.points._value='8';edit.room._value='Downstairs'
        await edit.on_submit(Interaction())
        self.assertEqual(self.db.execute('SELECT points,category FROM quests WHERE id=?',(qid,)).fetchone(),(8,'Downstairs'))
        self.assertEqual(self.db.execute('SELECT category FROM quests WHERE id=2').fetchone(),('general',))

    async def test_workspace_legacy_add_and_edit_share_duplicate_and_schedule_guards(self):
        ctx=SimpleNamespace(author=SimpleNamespace(id=10),send=AsyncMock())
        await self.app.bot.get_command('addquest').callback(ctx,'Fill dishwasher','daily',5)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM quests WHERE name='Fill dishwasher'").fetchone(),(1,))
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            await self.app.bot.get_command('editquest').callback(ctx,1,'frequency',value='monthly')
            self.assertEqual(self.db.execute('SELECT frequency FROM quests WHERE id=1').fetchone(),('daily',))

    async def test_workspace_ongoing_assignment_requires_confirmation(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;card=w.Card(10,1);event=Interaction()
            await next(c for c in card.children if getattr(c,'label',None)=='Every week · ongoing').callback(event)
            self.assertIsNone(self.db.execute('SELECT assigned_to FROM quests WHERE id=1').fetchone()[0])
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
            self.assertEqual(self.db.execute('SELECT assigned_to FROM quests WHERE id=1').fetchone(),('10',))

    async def test_workspace_admin_tools_use_interaction_member_when_not_cached(self):
        guild=SimpleNamespace(id=1,get_member=lambda uid:None)
        member=SimpleNamespace(id=10,guild_permissions=SimpleNamespace(manage_guild=True))
        view=self.ui.workspace.Dashboard(10,guild,member)
        self.assertIn('Household setup',[c.label for c in view.children if isinstance(c,discord.ui.Button)])

    async def test_workspace_completion_undo_survives_reopen_and_failed_undo_is_atomic(self):
        with self.clock('2026-10-20T10:00:00'):
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            import sqlite3
            external=sqlite3.connect(Path(self.temp.name)/'sprig.db')
            self.assertEqual(external.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,));external.close()
            self.db.execute("CREATE TRIGGER reject_undo BEFORE UPDATE OF undone_at ON completion_log BEGIN SELECT RAISE(ABORT,'undo disk failure'); END;");self.db.commit()
            with self.assertRaises(Exception):self.ui.undo_completion(10,1)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(5,))
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(1,))


    async def test_workspace_expired_moved_skip_resumes_regular_weekday(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Moved Friday chore','friday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Moved Friday chore'").fetchone()[0]
            self.ui.timing.set_policy(qid,'skip')
            w=self.ui.workspace;modal=w.MoveModal(10,qid,self.ui.snapshot(qid),lambda:w.Card(10,qid));modal.day._value='2026-10-21'
            event=Interaction();await modal.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
        with self.clock('2026-10-22T10:00:00'):
            self.app.reset_due_quests()
            self.assertIsNone(self.db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone())
            self.assertFalse(self.ui.ready(qid))
        with self.clock('2026-10-23T10:00:00'):
            self.assertTrue(self.ui.ready(qid))

    async def test_workspace_next_week_card_cannot_silently_take_others_current_claim(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'20')");self.db.commit()
            card=self.ui.workspace.Card(10,1,offset=1)
            labels=[getattr(c,'label',None) for c in card.children]
            self.assertNotIn('Every week · ongoing',labels)
            self.assertNotIn('Take this week',labels)
            self.assertIn('Take next week',labels)

    async def test_workspace_trade_proposal_uses_saved_id_before_discord_response(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'20')");self.db.execute("INSERT INTO notification_preferences VALUES('20',1)");self.db.commit()
            view=self.ui.TradeOfferView(10,2,requested=1)
            event=Interaction()
            await next(c for c in view.children if getattr(c,'label',None)=='Propose trade').callback(event)
            self.dm.send.assert_awaited_once()
            self.assertEqual(self.db.execute('SELECT trade_id,status FROM trade_notifications').fetchone(),(1,'sent'))
            self.assertIn('preference',event.response.payload['content'])

    async def test_v2_sections_pair_each_due_chore_with_its_done_button(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'10')");self.db.commit()
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            self.assertIsInstance(panel,discord.ui.LayoutView)
            sections=[c for c in panel.children if isinstance(c,discord.ui.Section)]
            self.assertEqual(len(sections),2)
            self.assertTrue(all(c.accessory.label=='Done' for c in sections))
            dishwasher=next(c for c in sections if 'Fill dishwasher' in c.children[0].content)
            self.assertIn('5 points',dishwasher.children[0].content)
            self.assertEqual(dishwasher.to_component_dict()['accessory']['type'],2)

    async def test_v2_inline_done_credits_only_the_matching_chore_once(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'10')");self.db.commit()
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            button=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and 'Fill dishwasher' in c.children[0].content)
            await asyncio.gather(button.callback(Interaction()),button.callback(Interaction()))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(5,))
            self.assertEqual(self.db.execute('SELECT quest_id FROM completion_log').fetchall(),[(1,)])
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))

    async def test_v2_inline_done_rejects_wrong_person_away_and_stale_ownership(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO claims VALUES(1,'10')");self.db.commit()
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            button=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and 'Fill dishwasher' in c.children[0].content)
            wrong=Interaction(20);await button.callback(wrong)
            self.assertIn('your own',wrong.response.wire_payload[0][0])
            self.assertTrue(wrong.response.wire_payload[1]['ephemeral'])
            self.db.execute("UPDATE claims SET user_id='20' WHERE quest_id=1");self.db.commit()
            await button.callback(Interaction())
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))
            self.ui.attendance.add(10,'2026-10-20','2026-10-20','away')
            away=w.render(w.Browse(10,'mine'))
            self.assertTrue(all(c.accessory.disabled for c in away.children if isinstance(c,discord.ui.Section) and c.accessory.label=='Done'))

    async def test_v2_early_and_next_week_rows_offer_details_not_done(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Friday laundry','friday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Friday laundry'").fetchone()[0]
            self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=?",(qid,));self.db.commit()
            w=self.ui.workspace
            for tab in ('upcoming','next'):
                panel=w.render(w.Browse(10,'mine',tab=tab))
                self.assertTrue(all(c.accessory.label=='Details' for c in panel.children if isinstance(c,discord.ui.Section)))

    async def test_v2_stale_done_cannot_complete_the_next_twice_daily_slot(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1");self.db.commit()
            self.ui.signup(10,1,self.ui.week_key())
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            button=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and 'Fill dishwasher' in c.children[0].content)
            await button.callback(Interaction())
        with self.clock('2026-10-20T13:00:00'):
            event=Interaction();await button.callback(event)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=1').fetchone(),(0,))
            self.assertIn('changed',event.response.payload['content'])

    async def test_v2_navigation_clears_embeds_and_retains_layout_for_cards_and_back(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=w.Browse(10,'household');panel=w.render(view)
            details=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section))
            event=Interaction();await details.callback(event)
            wire=event.response.wire_payload
            self.assertIsNone(wire['content']);self.assertEqual(wire['embeds'],[])
            self.assertEqual(wire['attachments'],[])
            self.assertNotIn('embed',wire)
            self.assertIsInstance(wire['view'],w.LayoutPanel)
            card=wire['view'].source
            await next(c for c in card.children if getattr(c,'label',None)=='Back').callback(event)
            self.assertIsInstance(event.response.wire_payload['view'].source,w.Browse)
            await next(c for c in event.response.wire_payload['view'].source.children if getattr(c,'label',None)=='Dashboard').callback(event)
            self.assertIsInstance(event.response.wire_payload['view'].source,w.Dashboard)

    async def test_v2_editors_and_modal_results_stay_on_v2_private_workspace(self):
        w=self.ui.workspace;view=w.adapt(self.ui.EditChoreView(10,selected=1),10,lambda:w.Card(10,1))
        event=Interaction();await next(c for c in view.children if getattr(c,'label',None)=='Change schedule').callback(event)
        self.assertIsInstance(event.response.wire_payload['view'],w.LayoutPanel)
        editor=w.adapt(self.ui.EditChoreView(10,selected=1),10,lambda:w.Card(10,1))
        event=Interaction();await next(c for c in editor.children if getattr(c,'label',None)=='Edit details').callback(event)
        modal=event.response.payload
        modal.name._value='Fill dishwasher';modal.notes._value='Updated';modal.points._value='5';modal.room._value='Kitchen'
        await modal.on_submit(event)
        self.assertIsInstance(event.response.wire_payload['view'],w.LayoutPanel)
        self.assertEqual(event.response.wire_payload['embeds'],[])

    async def test_v2_shared_launcher_sends_only_private_v2_controls(self):
        event=Interaction();await self.ui.Launcher().open_list(event,'mine')
        args,wire=event.response.wire_payload
        self.assertTrue(wire['ephemeral'])
        self.assertIsInstance(wire['view'],discord.ui.LayoutView)
        self.assertNotIn('embed',wire);self.assertNotIn('content',wire)
        self.assertTrue(await wire['view'].interaction_check(event))
        self.assertFalse(await wire['view'].interaction_check(Interaction(20)))

    async def test_v2_limits_paging_and_nested_controls_are_valid(self):
        with self.clock('2026-10-20T10:00:00'):
            for n in range(22):
                self.ui.create_chore(f'Task {n:02} '+'x'*65,'daily','5','notes')
                qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=?",(qid,))
            self.db.commit();w=self.ui.workspace
            def count(items):
                total=0
                for item in items:
                    total+=1
                    total+=count(item.get('components',[]))
                    if item.get('accessory'):total+=count([item['accessory']])
                return total
            def texts(items):
                out=[]
                for item in items:
                    if item['type']==10:out.append(item['content'])
                    out+=texts(item.get('components',[]))
                return out
            for page in (0,1,4):
                panel=w.render(w.Browse(10,'mine',page=page))
                self.assertLessEqual(len([c for c in panel.children if isinstance(c,discord.ui.Section)]),5)
                payload=panel.to_components()
                self.assertLessEqual(count(payload),40)
                self.assertLessEqual(sum(map(len,texts(payload))),4000)
                for item in payload:
                    if item['type']==1:
                        self.assertLessEqual(sum(5 if c['type'] in (3,5,6,7,8) else 1 for c in item['components']),5)
            for source in (w.Dashboard(10),w.Card(10,1),w.Manage(10),w.Trips(10),w.Inbox(301104023405199361),w.Guide(10),self.ui.HouseholdSetup(10),self.ui.FeedbackView(10,1)):
                self.assertLessEqual(count(w.render(source).to_components()),40)


    async def test_v2_serialized_private_message_has_v2_and_ephemeral_flags(self):
        from discord.http import handle_message_parameters
        panel=self.ui.workspace.render(self.ui.workspace.Browse(10,'mine'))
        with handle_message_parameters(view=panel,content=None,embeds=[],attachments=[],flags=discord.MessageFlags(ephemeral=True),allowed_mentions=discord.AllowedMentions.none()) as params:
            self.assertEqual(params.payload['flags'] & (1<<15),1<<15)
            self.assertEqual(params.payload['flags'] & 64,64)
            self.assertIsNone(params.payload['content'])
            self.assertEqual(params.payload['embeds'],[])
            self.assertEqual(params.payload['allowed_mentions']['parse'],[])

    async def test_polished_my_due_list_omits_repeated_name_status_and_keeps_slot(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1")
            self.db.execute("INSERT INTO claims VALUES(1,'10')");self.db.commit()
            view=self.ui.workspace.Browse(10,'mine',guild=Interaction().guild)
            for field in view.embed.fields:
                self.assertNotIn('Person 10',field.value)
                self.assertNotIn('Due now',field.value)
            self.assertIn('AM slot',str(view.embed.to_dict()))
            self.assertIn('Due now',view.embed.description)
            self.assertIn('5 points',str(view.embed.to_dict()))

    async def test_polished_completed_tab_has_distinct_label_from_done_action(self):
        with self.clock('2026-10-20T10:00:00'):
            view=self.ui.workspace.Browse(10,'mine')
            labels=[getattr(c,'label',None) for c in view.children]
            self.assertIn('Completed',labels);self.assertNotIn('Done',labels)
            panel=self.ui.workspace.render(view)
            self.assertTrue(any(isinstance(c,discord.ui.Section) and c.accessory.label=='Done' for c in panel.children))
            event=Interaction();await next(c for c in view.children if getattr(c,'label',None)=='Completed').callback(event)
            self.assertEqual(event.response.payload['view'].state['tab'],'done')

    async def test_polished_personal_total_refreshes_after_inline_done_and_undo(self):
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO users(id,points) VALUES('10',40)");self.db.commit()
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            self.assertIn('40 points',panel.children[0].content)
            event=Interaction();await next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and 'My bathroom' in c.children[0].content).callback(event)
            self.assertIn('50 points',event.response.payload['embed'].description)
            self.assertIn('undone',self.ui.undo_completion(10,1))
            self.assertIn('40 points',w.Browse(10,'mine').embed.description)

    async def test_points_button_is_private_read_only_and_rejects_other_viewers(self):
        self.db.executemany('INSERT INTO users(id,points,streak) VALUES(?,?,?)',[('10',20,3),('20',45,2)]);self.db.commit()
        before=list(self.db.iterdump());w=self.ui.workspace;event=Interaction()
        await next(c for c in w.Dashboard(10,event.guild).children if c.label=='Points & standings').callback(event)
        panel=event.response.wire_payload['view'];self.assertIsInstance(panel,w.LayoutPanel)
        self.assertIn('20 points',panel.source.embed.description)
        self.assertIn('3 day(s)',panel.source.embed.description)
        self.assertTrue(await panel.interaction_check(event))
        other=Interaction(20);self.assertFalse(await panel.interaction_check(other))
        self.assertTrue(other.response.wire_payload[1]['ephemeral'])
        self.assertEqual(before,list(self.db.iterdump()))

    async def test_points_standings_handle_empty_users_ties_and_pagination(self):
        w=self.ui.workspace;before=list(self.db.iterdump());empty=w.Points(10)
        self.assertIn('0 points',empty.embed.description)
        self.assertEqual(before,list(self.db.iterdump()))
        self.db.executemany('INSERT INTO users(id,points) VALUES(?,?)',[(str(n),100 if n<3 else 90-n) for n in range(1,9)]);self.db.commit()
        first=w.Points(10,Interaction().guild)
        self.assertTrue(first.embed.fields[0].name.startswith('1.'))
        self.assertTrue(first.embed.fields[1].name.startswith('1.'))
        self.assertTrue(first.embed.fields[2].name.startswith('3.'))
        event=Interaction();await next(c for c in first.children if getattr(c,'label',None)=='Next').callback(event)
        self.assertEqual(len(event.response.payload['embed'].fields),3)
        self.assertTrue(event.response.payload['embed'].fields[0].name.startswith('6.'))
        self.assertLessEqual(len(event.response.wire_payload['view'].to_components()),40)

    async def test_household_keeps_owner_and_due_status_for_context(self):
        with self.clock('2026-10-20T10:00:00'):
            view=self.ui.workspace.Browse(10,'household',tab='due',guild=Interaction().guild)
            field=next(f for f in view.embed.fields if 'My bathroom' in f.name)
            self.assertIn('Person 10',field.value);self.assertIn('Due now',field.value)


    async def test_paging_buttons_immediately_follow_page_numbers_on_all_list_pages(self):
        with self.clock('2026-10-20T10:00:00'):
            for n in range(12):self.ui.create_chore(f'Paged chore {n}','daily','5','')
            for page,expected in [(0,['Next']),(1,['Previous','Next']),(2,['Previous'])]:
                panel=self.ui.workspace.render(self.ui.workspace.Browse(10,'household',tab='all',page=page))
                footer=next(i for i,c in enumerate(panel.children) if isinstance(c,discord.ui.TextDisplay) and 'Page ' in c.content)
                paging=panel.children[footer+1]
                self.assertIsInstance(paging,discord.ui.ActionRow)
                self.assertEqual([c.label for c in paging.children],expected)
                self.assertIsInstance(panel.children[footer+2],discord.ui.Separator)
                self.assertTrue(all(c.label in ('Previous','Next') for c in paging.children))
                later=[c for row in panel.children[footer+2:] if isinstance(row,discord.ui.ActionRow) for c in row.children]
                self.assertFalse(any(getattr(c,'label',None) in ('Previous','Next') for c in later))
            event=Interaction()
            middle=self.ui.workspace.render(self.ui.workspace.Browse(10,'household',tab='all',page=1))
            paging=next(c for c in middle.children if isinstance(c,discord.ui.ActionRow) and [getattr(b,'label',None) for b in c.children]==['Previous','Next'])
            await paging.children[1].callback(event)
            self.assertEqual(event.response.payload['view'].state['page'],2)
            self.assertEqual(event.response.payload['view'].state['area'],'household')

    async def test_help_button_is_persistent_private_and_changes_no_data(self):
        before = list(self.db.iterdump())
        view = self.ui.Launcher()
        self.assertTrue(view.is_persistent())
        button = next(c for c in view.children if c.label == 'Help')
        event = Interaction(20)
        self.assertTrue(await view.interaction_check(event))
        await button.callback(event)
        options = event.response.payload[1]
        self.assertTrue(options['ephemeral'])
        guide = str(options['embed'].to_dict())
        for phrase in ['My chores','Due now','Upcoming','Completed','Pick up chores','Household','same card']:
            self.assertIn(phrase, guide)
        self.assertEqual(list(self.db.iterdump()), before)

    async def test_refresh_updates_existing_dashboard_help_without_reposting(self):
        message = SimpleNamespace(author=SimpleNamespace(id=77), edit=AsyncMock())
        send = AsyncMock()
        channel = SimpleNamespace(id=2, fetch_message=AsyncMock(return_value=message))
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), channel=channel, send=send)
        with patch.object(self.app.bot, '_connection', SimpleNamespace(user=SimpleNamespace(id=77))):
            await self.app.bot.get_command('refreshchoreboard').callback(ctx)
        channel.fetch_message.assert_awaited_once_with(3)
        options = message.edit.call_args.kwargs
        self.assertIn('Tap **Help**', options['content'])
        self.assertIn('Help', [c.label for c in options['view'].children])
        self.assertEqual(send.await_count, 1)

    async def test_slash_enable_does_not_remove_other_remote_commands(self):
        messages=[]
        async def send(content,**kwargs):
            messages.append(content)
        ctx=SimpleNamespace(guild=SimpleNamespace(id=1),send=send)
        with patch.object(self.app.bot.tree,'fetch_commands',new=AsyncMock(return_value=[SimpleNamespace(name='unrelated')])),patch.object(self.app.bot.tree,'sync',new=AsyncMock()) as sync:
            await self.app.bot.get_command('enableprivatechores').callback(ctx)
            sync.assert_not_awaited()
        with patch.object(self.app.bot.tree,'fetch_commands',new=AsyncMock(return_value=[])),patch.object(self.app.bot.tree,'sync',new=AsyncMock()) as sync:
            await self.app.bot.get_command('enableprivatechores').callback(ctx)
            sync.assert_awaited_once()
        self.assertIsNotNone(self.app.bot.tree.get_command('chores',guild=discord.Object(id=1)))


if __name__ == "__main__":
    unittest.main()
