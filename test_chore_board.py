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

    async def send_modal(self, modal):
        self.payload = modal


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

    async def test_add_form_preserves_existing_and_blocks_duplicate(self):
        before = self.db.execute('SELECT * FROM quests ORDER BY id').fetchall()
        message = self.ui.create_chore('  Sweep   kitchen ', 'daily', '', 'Afternoon')
        self.assertIn('Added', message)
        self.assertEqual(self.db.execute("SELECT frequency, points, notes, assigned_to FROM quests WHERE name = 'Sweep kitchen'").fetchone(), ('daily', 0, 'Afternoon', None))
        self.assertIn('already exists', self.ui.create_chore('sweep kitchen', 'daily', '5', ''))
        self.assertEqual(self.db.execute('SELECT * FROM quests ORDER BY id LIMIT 2').fetchall(), before)
        self.assertIn('already exists', self.ui.create_chore('Fill dishwasher', 'daily', '5', ''))

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


if __name__ == "__main__":
    unittest.main()
