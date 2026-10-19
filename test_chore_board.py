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
from unittest.mock import patch
from datetime import datetime

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "test-deps"))
import discord


class Response:
    def __init__(self):
        self.payload = None
        self.acknowledged = False

    async def defer(self):
        self.acknowledged = True

    async def send_message(self, *args, **kwargs):
        self.payload = (args, kwargs)

    async def edit_message(self, **kwargs):
        self.payload = kwargs


class Interaction:
    def __init__(self, user_id=10):
        self.user = SimpleNamespace(id=user_id, display_name=f"Person {user_id}")
        self.guild_id, self.channel_id = 1, 2
        self.guild = SimpleNamespace(get_member=lambda uid: SimpleNamespace(display_name=f"Person {uid}"))
        self.response = Response()
        self.result = None

    async def edit_original_response(self, **kwargs):
        self.result = kwargs


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
        self.db.execute("INSERT INTO chore_board VALUES (1, '1', '2', '3')")
        self.db.execute("INSERT INTO quests (name, frequency, points) VALUES ('Fill dishwasher', 'daily', 5)")
        self.db.execute("INSERT INTO quests (name, frequency, points, assigned_to) VALUES ('My bathroom', 'weekly', 10, '10')")
        self.db.commit()

    async def asyncTearDown(self):
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


if __name__ == "__main__":
    unittest.main()
