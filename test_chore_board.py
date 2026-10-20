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
from datetime import datetime

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "test-deps"))
import discord


class Response:
    def __init__(self):
        self.payload = None
        self.acknowledged = False

    async def defer(self, **kwargs):
        self.acknowledged = True

    async def send_message(self, *args, **kwargs):
        self.payload = (args, kwargs)

    async def edit_message(self, **kwargs):
        self.payload = kwargs

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
        self.assertIn('Add chore', [c.label for c in edits[0]['view'].children])
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
        self.assertIn('Open chores',[c.label for c in options['view'].children])
        self.assertEqual(options['view'].timeout,600)

    async def test_slash_chores_is_private_and_actions_stay_private(self):
        messages=[]
        async def send(content,**kwargs):
            messages.append((content,kwargs))
        ctx=SimpleNamespace(interaction=object(),guild=SimpleNamespace(id=1),channel=SimpleNamespace(id=2),author=SimpleNamespace(id=10),send=send)
        await self.app.bot.get_command('chores').callback(ctx)
        self.assertTrue(messages[0][1]['ephemeral'])
        event=Interaction()
        await messages[0][1]['view'].open_list(event,'open')
        self.assertTrue(event.response.payload[1]['ephemeral'])

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
            button=next(c for c in self.ui.Launcher().children if c.label=='Who’s doing what?')
            await button.callback(event)
            options=event.response.payload[1]
            self.assertTrue(options['ephemeral'])
            view=options['view']
            self.assertTrue(await view.interaction_check(event))
            self.assertFalse(await view.interaction_check(Interaction(20)))
            await next(c for c in view.children if c.label=='Next week').callback(event)
            self.assertEqual(event.result['view'].offset,1)
            self.assertIn('Next week',event.result['embed'].description)

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
        expected=[('My chores',0),('Open chores',0),('Weekly sign-ups',0),('Who’s doing what?',1),('Reassign',1),('Help',1),('Add chore',2),('Edit chore',2),('Remove chore',2),('Household setup',2)]
        for timeout in [None,600]:
            view=self.ui.Launcher(timeout=timeout)
            self.assertEqual([(c.label,c.row) for c in view.children],expected)
            self.assertEqual([c.label for c in view.children if c.style==discord.ButtonStyle.primary],['My chores'])
            self.assertTrue(all(c.style==discord.ButtonStyle.secondary for c in view.children if c.label!='My chores'))
            self.assertEqual(len({c.custom_id for c in view.children}),10)

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
            self.assertIsNone(event.result['view'])

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
        button=next(c for c in self.ui.Launcher().children if c.label=='Reassign')
        await button.callback(event)
        self.assertTrue(event.response.payload[1]['ephemeral'])
        view=event.response.payload[1]['view']
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
            self.assertIn('Tuesday',self.ui.AddChoreModal(10,'tuesday').name.placeholder)
            self.assertIn('🟠',self.ui.AddChoreModal(10,'tuesday').title)
            daily_option=next(o for o in personal.children[0].options if o.value=='1')
            self.assertEqual(str(daily_option.emoji),'🟠')
            self.assertIsNone(self.ui.timing.emoji('weekly'))

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
            self.assertIn('Any day this week',headings)
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
            await next(c for c in day_view.children if c.label=='Next week').callback(event)
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
                await next(c for c in view.children if getattr(c,'label',None)=='Choose day').callback(event)
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
        for phrase in ['Claim', 'Done', 'Release week', 'Sunday at 6 p.m.', 'Restore', '/chores', '!help']:
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
