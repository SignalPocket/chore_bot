"""Offline integration checks using a temporary copy and temporary SQLite DB."""
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
from time import perf_counter
from contextlib import closing
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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._schema_temp = tempfile.TemporaryDirectory()
        cls._schema_path = Path(cls._schema_temp.name) / 'empty-schema.db'

    @classmethod
    def tearDownClass(cls):
        cls._schema_temp.cleanup()
        super().tearDownClass()

    async def asyncSetUp(self):
        setup_started = perf_counter()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        shutil.copyfile(HERE / "sprig_bot.py", root / "sprig_bot.py")
        # Each test still gets a real, private disk DB and a fresh bot. Only
        # the empty schema is reused; no transaction/durability setting changes.
        cached = self._schema_path.exists() and os.getenv('SPRIG_TEST_COLD_START') != '1'
        if cached:
            shutil.copyfile(self._schema_path, root / 'sprig.db')
        env = patch.dict(os.environ, DISCORD_TOKEN='offline-test-placeholder', QUEST_TIMEZONE='America/New_York')
        env.start()
        self.addCleanup(env.stop)
        spec = importlib.util.spec_from_file_location("sprig_offline", root / "sprig_bot.py")
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.db = self.app.db
        if not self._schema_path.exists():
            self.db.commit()
            with closing(sqlite3.connect(self._schema_path)) as template:
                self.db.backup(template)
        self.ui = self.app.chore_ui
        self.dm = SimpleNamespace(send=AsyncMock())
        self.dm_patch = patch.object(self.app.bot, "get_user", return_value=self.dm)
        self.dm_patch.start()
        self.db.execute("INSERT INTO chore_board VALUES (1, '1', '2', '3')")
        self.db.execute("INSERT INTO quests (name, frequency, points) VALUES ('Fill dishwasher', 'daily', 5)")
        self.db.execute("INSERT INTO quests (name, frequency, points, assigned_to) VALUES ('My bathroom', 'weekly', 10, '10')")
        self.db.commit()
        self.setup_seconds = perf_counter() - setup_started

    async def asyncTearDown(self):
        self.dm_patch.stop()
        await self.app.bot.close()
        self.db.close()
        self.temp.cleanup()

    async def test_bootstrap_blank_and_legacy_database_use_real_migrations(self):
        # These paths always start without the cached schema, even in fast runs.
        for legacy in (False, True):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'sprig_bot.py'
                shutil.copyfile(HERE/'sprig_bot.py',path)
                if legacy:
                    with closing(sqlite3.connect(Path(folder)/'sprig.db')) as db:
                        db.executescript("CREATE TABLE users(id TEXT PRIMARY KEY,points INTEGER,streak INTEGER,last_completed TEXT);"
                            "INSERT INTO users VALUES('10',35,2,'2026-10-19');"
                            "CREATE TABLE quests(id INTEGER PRIMARY KEY,name TEXT,type TEXT,points INTEGER,assigned_to TEXT);"
                            "INSERT INTO quests VALUES(7,'Old task','weekly',5,'<@10>');")
                spec=importlib.util.spec_from_file_location('sprig_bootstrap_check',path)
                app=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(app)
                try:
                    self.assertEqual(app.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
                    tables={r[0] for r in app.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertTrue({'quests','users','completion_log','chore_revisions','reminder_deliveries','workspace_sessions'}<=tables)
                    self.assertEqual(app.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'chore_revision_%'").fetchone(),(21,))
                    if legacy:
                        self.assertEqual(app.db.execute('SELECT id,name,frequency,points,assigned_to FROM quests').fetchall(),[(7,'Old task','weekly',5,'10')])
                        self.assertEqual(app.db.execute('SELECT * FROM users').fetchall(),[('10',35,2,'2026-10-19')])
                    else:
                        self.assertEqual(app.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(0,))
                        self.assertEqual(app.db.execute('SELECT COUNT(*) FROM users').fetchone(),(0,))
                finally:
                    await app.bot.close()
                    app.db.close()

    async def test_fixture_template_contains_schema_without_household_state(self):
        with closing(sqlite3.connect(self._schema_path)) as template:
            tables=[r[0] for r in template.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                with self.subTest(table=table):
                    self.assertEqual(template.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone(),(0,))
            self.assertEqual(template.execute('PRAGMA synchronous').fetchone(),self.db.execute('PRAGMA synchronous').fetchone())

    async def test_release_report_gate_rejects_stale_incomplete_and_nonrelease_runs(self):
        import copy
        from run_tests import validate_release
        hashes={'source.py':'abc'};names=['test_one','test_two']
        valid={'suite':'full','success':True,'tests_run':2,'test_names':names,'skipped':0,'source_hashes':hashes}
        validate_release(valid,hashes,names)
        for changes in ({'suite':'focused'},{'suite':'server'},{'success':False},
                {'tests_run':1},{'test_names':['test_one']},{'skipped':1},
                {'source_hashes':{'source.py':'changed'}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_release(dict(copy.deepcopy(valid),**changes),hashes,names)
        for invalid in (None,[],{},'not a report'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                validate_release(invalid,hashes,names)

    async def test_test_inventory_has_no_shadowed_names_or_identical_bodies(self):
        import ast
        from collections import Counter
        tree=ast.parse((HERE/'test_chore_board.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BoardTests')
        methods=[n for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')]
        self.assertEqual(len(methods),len({n.name for n in methods}),'Duplicate names hide tests from discovery')
        bodies=Counter(ast.dump(ast.Module(body=n.body,type_ignores=[]),include_attributes=False) for n in methods)
        self.assertTrue(all(count==1 for count in bodies.values()),'Identical test bodies should be consolidated')

    async def audit9_queue(self,*actions):
        # Queue real callbacks behind the production mutation lock, in each
        # tested order, without wall-clock sleeps or replacing DB operations.
        tasks=[]
        async with self.ui.mutation_lock:
            for action,event in actions:
                tasks.append(asyncio.create_task(action(event)))
                for _ in range(3):await asyncio.sleep(0)
        await asyncio.gather(*tasks)

    async def test_inline_claim_button_claims_matching_chore_without_points_or_checklist_completion(self):
        w=self.ui.workspace;p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            p.save_plan(1,'5','Load cups',p.plan(1))
            panel=w.render(w.Browse(10,'pickup'))
            row=next(c for c in panel.children if isinstance(c,discord.ui.Section) and 'Fill dishwasher' in c.children[0].content)
            self.assertEqual(row.accessory.label,'Claim')
            event=Interaction();await row.accessory.callback(event)
            self.assertEqual(self.ui.owned_scope(1),('10','occurrence'))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone(),(0,))
            self.assertEqual(p.checked(1),set())
            view=event.response.payload['view'];self.assertEqual(view.state['area'],'pickup')
            self.assertNotIn(1,[q[0] for q in view.entries])

    async def test_inline_claim_double_tap_and_competing_people_only_one_owner(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            buttons=[next(c.accessory for c in w.render(w.Browse(uid,'pickup')).children if isinstance(c,discord.ui.Section) and c.accessory.label=='Claim') for uid in (10,20)]
            await asyncio.gather(buttons[0].callback(Interaction()),buttons[0].callback(Interaction()),buttons[1].callback(Interaction(20)))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM claims WHERE quest_id=1').fetchone(),(1,))
            self.assertIn(self.ui.owned_scope(1)[0],('10','20'))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_inline_claim_stale_assignment_wrong_user_and_away_are_safe(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            button=next(c.accessory for c in w.render(w.Browse(10,'pickup')).children if isinstance(c,discord.ui.Section) and c.accessory.label=='Claim')
            event=Interaction(20);await button.callback(event)
            self.assertTrue(event.response.wire_payload[1]['ephemeral']);self.assertIsNone(self.ui.owned_scope(1)[0])
            self.ui.reassign(1,20,'assignment',self.ui.reassign_snapshot(1))
            await button.callback(Interaction());self.assertEqual(self.ui.owned_scope(1)[0],'20')
            self.ui.create_chore('Away claim','daily','5','')
            self.ui.attendance.add(10,'2026-10-20','2026-10-20','away')
            panel=w.render(w.Browse(10,'pickup'))
            buttons=[c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and c.accessory.label=='Claim']
            self.assertTrue(buttons);self.assertTrue(all(b.disabled for b in buttons))
            await buttons[0].callback(Interaction())
            self.assertIsNone(self.ui.owned_scope(self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0])[0])

    async def test_inline_claim_future_chore_and_next_week_keep_details(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Friday task','friday','5','')
            panel=w.render(w.Browse(10,'pickup',tab='week'))
            future=next(c for c in panel.children if isinstance(c,discord.ui.Section) and 'Friday task' in c.children[0].content)
            self.assertEqual(future.accessory.label,'Details')
            panel=w.render(w.Browse(10,'pickup',tab='next'))
            self.assertTrue(all(c.accessory.label=='Details' for c in panel.children if isinstance(c,discord.ui.Section)))

    async def test_inline_claim_keeps_filters_and_clamps_last_page(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for n in range(6):self.ui.create_chore(f'Pickup {n}','one-time','5','')
            panel=w.render(w.Browse(10,'pickup',tab='all',query='Pickup',page=1))
            button=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and c.accessory.label=='Claim')
            event=Interaction();await button.callback(event)
            view=event.response.payload['view']
            self.assertEqual(view.state['query'],'Pickup');self.assertEqual(view.state['tab'],'all');self.assertEqual(view.state['page'],0)
            self.assertEqual(len(view.entries),5)

    async def test_inline_claim_expired_screen_restores_without_claiming(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            panel=w.render(w.Browse(10,'pickup'));token=panel.recovery_token
            button=next(c.accessory for c in panel.children if isinstance(c,discord.ui.Section) and c.accessory.label=='Claim')
            w.recovery.live.clear();event=Interaction();await button.callback(event)
            self.assertIsNone(self.ui.owned_scope(1)[0]);self.assertEqual(event.response.payload['view'].state['area'],'pickup')
            self.assertIn('Nothing was repeated',event.response.payload['content'])

    async def test_audit10_completion_drop_archive_and_move_during_lookup_cancel(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            for index,action in enumerate(('done','drop','archive','move','choose_day','away')):
                with self.subTest(action=action):
                    self.db.execute('UPDATE quests SET completed=1,reset_after=NULL');self.db.commit()
                    self.ui.create_chore('Lookup cancellation '+action,'weekly','5','')
                    qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                    self.ui.reassign(qid,10,'assignment',self.ui.reassign_snapshot(qid))
                    value=f'09:{index:02d}';self.app.now_local.return_value=datetime(2026,10,20,9,index,tzinfo=self.app.QUEST_TIMEZONE)
                    p.save_reminders(10,True,value,p.settings(10));self.dm.send.reset_mock()
                    async def fetch(uid):
                        if action=='done':await self.ui.PersonalView(10,'mine',selected=qid).act(Interaction(),'done')
                        elif action=='drop':self.ui.drop_chore(10,qid,self.ui.snapshot(qid))
                        elif action=='archive':
                            self.db.execute("INSERT INTO archived_chores VALUES(?,'10','test')",(qid,));self.db.commit()
                        elif action=='move':
                            self.db.execute("INSERT INTO occurrence_moves VALUES(?,'2026-10-21')",(qid,));self.db.commit()
                        elif action=='choose_day':self.ui.update_chore(qid,'Lookup cancellation '+action,'wednesday','5','',self.ui.snapshot(qid))
                        else:self.ui.attendance.add(10,'2026-10-20','2026-10-20','away','Trip')
                        return self.dm
                    with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
                    self.dm.send.assert_not_awaited()
                    self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries WHERE user_id=? AND slot=?',('10','2026-10-20 '+value)).fetchone(),('canceled',))
            self.assertEqual(self.db.execute('SELECT points FROM completion_log').fetchall(),[(5,)])

    async def test_audit10_reassignment_during_lookup_follows_recipient_optin(self):
        p=self.ui.planning;dms={uid:SimpleNamespace(send=AsyncMock()) for uid in (10,20)}
        with self.clock('2026-10-20T09:00:00'):
            for uid in (10,20):p.save_reminders(uid,True,'09:00',p.settings(uid))
            async def fetch(uid):
                if uid==10:self.ui.reassign(2,20,'assignment',self.ui.reassign_snapshot(2))
                return dms[uid]
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        dms[10].send.assert_not_awaited();dms[20].send.assert_awaited_once()
        self.assertIn('My bathroom',dms[20].send.call_args.args[0])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_audit10_trade_during_lookup_rebuilds_both_people_lists(self):
        p=self.ui.planning;dms={uid:SimpleNamespace(send=AsyncMock()) for uid in (10,20)}
        with self.clock('2026-10-20T09:00:00'):
            self.ui.reassign(1,20,'assignment',self.ui.reassign_snapshot(1))
            self.ui.propose_trade(10,2,1,self.ui.trade_snapshot(2),self.ui.trade_snapshot(1))
            for uid in (10,20):p.save_reminders(uid,True,'09:00',p.settings(uid))
            async def fetch(uid):
                if uid==10:self.assertIn('accepted',self.ui.respond_trade(20,1,'accept'))
                return dms[uid]
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        for uid,yes,no in ((10,'Fill dishwasher','My bathroom'),(20,'My bathroom','Fill dishwasher')):
            dms[uid].send.assert_awaited_once();text=dms[uid].send.call_args.args[0]
            self.assertIn(yes,text);self.assertNotIn(no,text)

    async def test_audit10_restored_work_during_lookup_is_included(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            self.ui.reassign(1,10,'assignment',self.ui.reassign_snapshot(1))
            self.db.execute("INSERT INTO archived_chores VALUES(2,'10','test')");self.db.commit()
            p.save_reminders(10,True,'09:00',p.settings(10))
            async def fetch(uid):
                self.db.execute('DELETE FROM archived_chores WHERE quest_id=2');self.db.commit()
                return self.dm
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        text=self.dm.send.call_args.args[0];self.assertIn('Fill dishwasher',text);self.assertIn('My bathroom',text)

    async def test_audit10_skip_and_keep_overdue_are_distinguished(self):
        p=self.ui.planning
        with self.clock('2026-10-19T09:00:00'):
            self.db.execute('UPDATE quests SET completed=1,reset_after=NULL');self.db.commit()
            for policy in ('keep','skip'):
                self.ui.create_chore('Monday '+policy,'monday','5','')
                qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                self.ui.reassign(qid,10,'assignment',self.ui.reassign_snapshot(qid));self.ui.timing.set_policy(qid,policy)
            p.save_reminders(10,True,'09:00',p.settings(10))
        with self.clock('2026-10-21T09:00:00'):await p.send_due_reminders()
        text=self.dm.send.call_args.args[0];self.assertIn('Monday keep',text);self.assertNotIn('Monday skip',text)

    async def test_audit10_separate_am_pm_completion_and_owners(self):
        p=self.ui.planning;dms={uid:SimpleNamespace(send=AsyncMock()) for uid in (10,20)}
        with self.clock('2026-10-20T09:00:00'):
            self.db.execute('UPDATE quests SET completed=1,reset_after=NULL');self.db.commit()
            ids={}
            for uid,freq,name in ((10,'daily-am','Morning dishes'),(20,'daily-pm','Evening dishes')):
                self.ui.create_chore(name,freq,'5','');qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0];ids[uid]=qid
                self.ui.reassign(qid,uid,'assignment',self.ui.reassign_snapshot(qid))
                p.save_reminders(uid,True,'09:00,13:00',p.settings(uid))
            with patch.object(self.app.bot,'get_user',side_effect=lambda uid:dms[uid]):await p.send_due_reminders()
            dms[10].send.assert_awaited_once();dms[20].send.assert_not_awaited()
            await self.ui.PersonalView(10,'mine',selected=ids[10]).act(Interaction(),'done')
            dms[10].send.reset_mock()
        with self.clock('2026-10-20T13:00:00'):
            with patch.object(self.app.bot,'get_user',side_effect=lambda uid:dms[uid]):await p.send_due_reminders()
        dms[10].send.assert_not_awaited();dms[20].send.assert_awaited_once()
        self.assertIn('Evening dishes',dms[20].send.call_args.args[0])

    async def test_audit10_week_handoff_uses_new_weekly_owner(self):
        p=self.ui.planning;dms={uid:SimpleNamespace(send=AsyncMock()) for uid in (10,20)}
        with self.clock('2026-10-20T09:00:00'):
            self.db.execute('UPDATE quests SET completed=1,reset_after=NULL WHERE id=2');self.db.commit()
            self.ui.signup(10,1,self.ui.week_key());self.ui.signup(20,1,self.ui.week_key(1))
            for uid in (10,20):p.save_reminders(uid,True,'17:59,18:00',p.settings(uid))
        with patch.object(self.app.bot,'get_user',side_effect=lambda uid:dms[uid]):
            with self.clock('2026-10-25T17:59:00'):await p.send_due_reminders()
            dms[10].send.assert_awaited_once();dms[20].send.assert_not_awaited();dms[10].send.reset_mock()
            with self.clock('2026-10-25T18:00:00'):await p.send_due_reminders()
        dms[10].send.assert_not_awaited();dms[20].send.assert_awaited_once()

    async def test_audit10_rotation_and_trip_exceptions_follow_actual_day(self):
        p=self.ui.planning
        with self.clock('2026-10-21T09:00:00'):
            self.db.execute("UPDATE quests SET assigned_to='20' WHERE id=2")
            self.db.execute("INSERT INTO alternating_members VALUES('20')");self.db.commit()
            p.save_reminders(20,True,'09:00,10:00,11:00',p.settings(20))
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
            self.ui.attendance.add(20,'2026-10-21','2026-10-21','home','Traded day')
        with self.clock('2026-10-21T10:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once();self.dm.send.reset_mock()
            self.db.execute('UPDATE availability_exceptions SET active=0');self.db.commit()
        with self.clock('2026-10-21T11:00:00'):
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
        with self.clock('2026-10-28T09:00:00'):
            self.ui.attendance.add(20,'2026-10-28','2026-10-28','away','Trip')
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
        with self.clock('2026-10-29T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once()

    async def test_audit10_chosen_and_alternating_chore_days_are_respected(self):
        p=self.ui.planning
        with self.clock('2026-10-19T09:00:00'):
            self.db.execute('UPDATE quests SET completed=1,reset_after=NULL');self.db.commit()
            for name,freq in (('Away Monday','away:monday'),('Home Monday','home:monday'),('Wednesday chore','wednesday')):
                self.ui.create_chore(name,freq,'5','');qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                self.ui.reassign(qid,10,'assignment',self.ui.reassign_snapshot(qid));self.ui.timing.set_policy(qid,'skip')
            p.save_reminders(10,True,'09:00',p.settings(10));await p.send_due_reminders()
            text=self.dm.send.call_args.args[0];self.assertIn('Away Monday',text);self.assertNotIn('Home Monday',text);self.assertNotIn('Wednesday chore',text)
            self.dm.send.reset_mock()
        with self.clock('2026-10-21T09:00:00'):
            await p.send_due_reminders();text=self.dm.send.call_args.args[0];self.assertIn('Wednesday chore',text);self.assertNotIn('Away Monday',text)
            self.dm.send.reset_mock()
        with self.clock('2026-10-26T09:00:00'):
            await p.send_due_reminders();text=self.dm.send.call_args.args[0];self.assertIn('Home Monday',text);self.assertNotIn('Away Monday',text)

    async def test_audit10_changed_times_cancel_old_slot_and_new_slot_sends_once(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        async def fetch(uid):
            p.save_reminders(10,True,'09:01',p.settings(10));return self.dm
        with self.clock('2026-10-20T09:00:00'):
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
            self.dm.send.assert_not_awaited()
        with self.clock('2026-10-20T09:01:00'):
            await p.send_due_reminders();await p.send_due_reminders()
        self.dm.send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT slot,status FROM reminder_deliveries ORDER BY slot').fetchall(),[('2026-10-20 09:00','canceled'),('2026-10-20 09:01','sent')])

    async def test_audit10_slow_first_recipient_cannot_send_late_second_reminder(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:14:59'):
            self.ui.reassign(1,20,'assignment',self.ui.reassign_snapshot(1))
            for uid in (10,20):p.save_reminders(uid,True,'09:00',p.settings(uid))
            async def fetch(uid):
                self.app.now_local.return_value=datetime(2026,10,20,9,15,1,tzinfo=self.app.QUEST_TIMEZONE)
                return self.dm
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch) as calls:await p.send_due_reminders()
        self.dm.send.assert_not_awaited();self.assertEqual(calls.await_count,1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reminder_deliveries WHERE user_id='20'").fetchone(),(0,))

    async def test_audit10_concurrent_dispatch_with_transfer_delivers_only_to_new_owner(self):
        p=self.ui.planning;dms={uid:SimpleNamespace(send=AsyncMock()) for uid in (10,20)}
        started=asyncio.Event();release=asyncio.Event()
        async def fetch(uid):
            if uid==10:started.set();await release.wait()
            return dms[uid]
        with self.clock('2026-10-20T09:00:00'):
            for uid in (10,20):p.save_reminders(uid,True,'09:00',p.settings(uid))
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):
                task=asyncio.create_task(p.send_due_reminders())
                try:
                    await asyncio.wait_for(started.wait(),timeout=1)
                    self.ui.reassign(2,20,'assignment',self.ui.reassign_snapshot(2))
                    await p.send_due_reminders()
                finally:release.set();await task
        dms[10].send.assert_not_awaited();dms[20].send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT user_id,status FROM reminder_deliveries ORDER BY user_id').fetchall(),[('10','canceled'),('20','sent')])

    async def test_audit10_empty_slot_is_not_backfilled_after_new_claim(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            self.ui.drop_chore(10,2,self.ui.snapshot(2))
            p.save_reminders(10,True,'09:00,09:01',p.settings(10))
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
            self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchone(),('skipped_empty',))
            self.ui.reassign(1,10,'occurrence',self.ui.reassign_snapshot(1))
        with self.clock('2026-10-20T09:01:00'):
            await p.send_due_reminders();await p.send_due_reminders()
        self.dm.send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries ORDER BY slot').fetchall(),[('skipped_empty',),('sent',)])

    async def test_audit10_first_tick_after_handoff_does_not_send_previous_week_slot(self):
        p=self.ui.planning
        with self.clock('2026-10-25T18:00:00'):
            p.save_reminders(10,True,'17:59,18:00',p.settings(10))
            await p.send_due_reminders()
            self.dm.send.assert_awaited_once()
            self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries ORDER BY slot').fetchall(),[('skipped_week',),('sent',)])

    async def test_audit10_skip_statuses_are_explained_in_private_reminder_controls(self):
        p=self.ui.planning
        for status,text in (('skipped_empty','no due chores'),('skipped_away','away'),('skipped_week','previous household week'),('canceled','changed')):
            self.db.execute("INSERT OR REPLACE INTO reminder_deliveries VALUES('10','2026-10-20 09:00',?)",(status,));self.db.commit()
            self.assertIn(text,p.Reminders(10).embed.fields[0].value)

    async def test_audit10_reassignment_does_not_enable_recipient_reminders(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            p.save_reminders(10,True,'09:00',p.settings(10))
            self.ui.reassign(2,20,'assignment',self.ui.reassign_snapshot(2))
            before={t:self.db.execute('SELECT * FROM '+t).fetchall() for t in ('quests','users','claims','week_signups','completion_log')}
            await p.send_due_reminders()
            self.dm.send.assert_not_awaited();self.assertEqual(p.settings(20)[0],0)
            self.assertEqual(before,{t:self.db.execute('SELECT * FROM '+t).fetchall() for t in before})

    async def test_audit10_moved_skip_occurrence_waits_for_chosen_day(self):
        p=self.ui.planning;w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            p.save_reminders(10,True,'09:00',p.settings(10))
            self.ui.timing.set_policy(2,'skip')
            modal=w.MoveModal(10,2,self.ui.snapshot(2),lambda:w.Card(10,2))
            modal.day._value='2026-10-21';event=Interaction();await modal.on_submit(event)
            confirm=next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm')
            await confirm.callback(event)
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
        with self.clock('2026-10-21T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once()
            self.assertIn('My bathroom',self.dm.send.call_args.args[0]);self.dm.send.reset_mock()
        with self.clock('2026-10-22T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
            self.assertFalse(self.ui.ready(2))
            self.assertTrue(self.ui.timing.state(2)[0].startswith('2026-10-25T18:00:00'))
        with self.clock('2026-10-26T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once()
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_audit10_moved_monthly_skip_waits_until_next_month_and_survives_reload(self):
        from chore_timing import ChoreTiming
        p=self.ui.planning;w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            self.ui.update_chore(2,'My bathroom','monthly','10','',self.ui.snapshot(2))
            self.ui.timing.set_policy(2,'skip')
            p.save_reminders(10,True,'09:00',p.settings(10))
            modal=w.MoveModal(10,2,self.ui.snapshot(2),lambda:w.Card(10,2));modal.day._value='2026-10-21'
            event=Interaction();await modal.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
        with self.clock('2026-10-22T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
            self.assertFalse(self.ui.ready(2))
            self.assertFalse(ChoreTiming(vars(self.app),self.db).ready(2))
            self.ui.timing.set_policy(2,'keep');self.ui.timing.set_policy(2,'skip')
            self.assertTrue(self.ui.timing.policy_state(2)[1].startswith('2026-12-01T00:00:00'))
        with self.clock('2026-11-01T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once()
            self.assertIn('My bathroom',self.dm.send.call_args.args[0])

    async def test_audit10_delayed_skip_check_does_not_skip_current_regular_week(self):
        p=self.ui.planning;w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            self.ui.timing.set_policy(2,'skip');p.save_reminders(10,True,'09:00',p.settings(10))
            modal=w.MoveModal(10,2,self.ui.snapshot(2),lambda:w.Card(10,2));modal.day._value='2026-10-21'
            event=Interaction();await modal.on_submit(event)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Confirm').callback(event)
        with self.clock('2026-10-26T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_awaited_once()
            self.assertTrue(self.ui.ready(2));self.assertIn('My bathroom',self.dm.send.call_args.args[0])
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_audit10_rename_during_recipient_lookup_uses_current_name(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        async def fetch(uid):
            self.ui.update_chore(2,'Renamed bathroom','weekly','10','',self.ui.snapshot(2))
            return self.dm
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):
            with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.assertIn('Renamed bathroom',self.dm.send.call_args.args[0])
        self.assertNotIn('My bathroom',self.dm.send.call_args.args[0])

    async def test_audit10_new_assignment_during_lookup_is_included(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        async def fetch(uid):
            self.ui.reassign(1,10,'occurrence',self.ui.reassign_snapshot(1))
            return self.dm
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):
            with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        text=self.dm.send.call_args.args[0]
        self.assertIn('Fill dishwasher',text);self.assertIn('My bathroom',text)

    async def test_audit10_skip_deadline_crossed_during_lookup_does_not_send_old_work(self):
        p=self.ui.planning;p.save_reminders(10,True,'23:59',p.settings(10))
        with self.clock('2026-10-19T23:59:59'):
            self.db.execute("UPDATE quests SET completed=1,reset_after=NULL");self.db.commit()
            self.ui.create_chore('Monday skip','monday','5','')
            qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
            self.ui.reassign(qid,10,'assignment',self.ui.reassign_snapshot(qid));self.ui.timing.set_policy(qid,'skip')
            later=datetime(2026,10,20,0,0,1,tzinfo=self.app.QUEST_TIMEZONE)
            async def fetch(uid):
                self.app.now_local.return_value=later
                return self.dm
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchone(),('canceled',))

    async def test_audit10_slot_expiring_during_lookup_is_not_sent_late(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        with self.clock('2026-10-20T09:14:59'):
            async def fetch(uid):
                self.app.now_local.return_value=datetime(2026,10,20,9,15,1,tzinfo=self.app.QUEST_TIMEZONE)
                return self.dm
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchone(),('canceled',))

    async def test_audit10_noon_reset_during_lookup_includes_new_due_slot(self):
        p=self.ui.planning;p.save_reminders(10,True,'11:59',p.settings(10))
        with self.clock('2026-10-20T11:59:59'):
            self.db.execute("UPDATE quests SET frequency='twice-daily',assigned_to='10',completed=1,last_completed='2026-10-20T10:00:00-04:00',reset_after='2026-10-20T12:00:00-04:00' WHERE id=1");self.db.commit()
            async def fetch(uid):
                self.app.now_local.return_value=datetime(2026,10,20,12,0,1,tzinfo=self.app.QUEST_TIMEZONE)
                return self.dm
            with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):await p.send_due_reminders()
        self.assertIn('Fill dishwasher',self.dm.send.call_args.args[0])

    async def test_audit10_household_channel_changed_during_lookup_cancels(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        async def fetch(uid):
            self.db.execute("UPDATE chore_board SET channel_id='999'");self.db.commit()
            return self.dm
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):
            with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()

    async def test_audit9_competing_card_claims_in_both_orders(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for first,second in ((10,20),(20,10)):
                self.ui.create_chore(f'Claim race {first}','one-time','5','')
                qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                views=[w.Card(uid,qid) for uid in (first,second)]
                actions=[(next(c for c in v.children if getattr(c,'label',None)=='Just this time').callback,Interaction(uid)) for v,uid in zip(views,(first,second))]
                await self.audit9_queue(*actions)
                self.assertEqual(self.ui.owned_scope(qid),(str(first),'occurrence'))
                self.assertIn('changed',actions[1][1].response.payload['embed'].description)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM claims WHERE quest_id=?',(qid,)).fetchone(),(1,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_audit9_competing_week_reservations_current_and_next(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for offset,label in ((0,'Take this week'),(1,'Take next week')):
                for first,second in ((10,20),(20,10)):
                    self.ui.create_chore(f'Week race {offset} {first}','daily','5','')
                    qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                    actions=[(next(c for c in w.Card(uid,qid).children if getattr(c,'label',None)==label).callback,Interaction(uid)) for uid in (first,second)]
                    await self.audit9_queue(*actions)
                    self.assertEqual(self.ui.weekly_owner(qid,offset),str(first))
                    self.assertIn('changed',actions[1][1].response.payload['embed'].description)

    async def test_audit9_card_and_inline_done_together_award_once(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            card=w.Card(10,2);panel=w.render(w.Browse(10))
            inline=next(c for c in panel.walk_children() if isinstance(c,discord.ui.Button) and c.label=='Done')
            actions=[(next(c for c in card.children if getattr(c,'label',None)=='Done').callback,Interaction()),(inline.callback,Interaction())]
            await self.audit9_queue(*actions)
            self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='10'").fetchone(),(10,1))
            self.assertEqual(self.db.execute('SELECT quest_id,user_id,points FROM completion_log').fetchall(),[(2,'10',10)])
            self.dm.send.assert_not_called()

    async def test_audit9_two_different_completions_keep_both_awards_and_one_streak_day(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=1");self.db.commit()
            actions=[(next(c for c in w.Card(10,qid).children if getattr(c,'label',None)=='Done').callback,Interaction()) for qid in (1,2)]
            await self.audit9_queue(*actions)
            self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='10'").fetchone(),(15,1))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(2,))

    async def test_audit9_done_and_drop_both_orders(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for done_first in (True,False):
                self.ui.create_chore('Drop race '+str(done_first),'weekly','5','')
                qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=?",(qid,));self.db.commit()
                done=(next(c for c in w.Card(10,qid).children if getattr(c,'label',None)=='Done').callback,Interaction())
                drop=(next(c for c in self.ui.DropChoreView(10,qid,self.ui.snapshot(qid)).children if getattr(c,'label',None)=='Confirm drop').callback,Interaction())
                await self.audit9_queue(*( (done,drop) if done_first else (drop,done) ))
                self.assertEqual(self.db.execute('SELECT completed,assigned_to FROM quests WHERE id=?',(qid,)).fetchone(),(1,'10') if done_first else (0,None))
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log WHERE quest_id=?',(qid,)).fetchone(),(int(done_first),))

    async def test_audit9_done_and_reassign_both_orders_preserve_earned_points(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for scope in ('occurrence','week0','assignment'):
                for done_first in (True,False):
                    self.ui.create_chore(f'Reassign race {scope} {done_first}','daily','5','')
                    qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                    self.ui.reassign(qid,10,scope,self.ui.reassign_snapshot(qid))
                    done=(next(c for c in w.Card(10,qid).children if getattr(c,'label',None)=='Done').callback,Interaction())
                    view=self.ui.ReassignView(10,qid=qid,scope=scope,expected=self.ui.reassign_snapshot(qid))
                    view.target=SimpleNamespace(id=20,bot=False,guild=SimpleNamespace(id=1))
                    give=(view.confirm,Interaction())
                    await self.audit9_queue(*( (done,give) if done_first else (give,done) ))
                    self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(qid,)).fetchone(),(int(done_first),))
                    self.assertEqual(self.db.execute('SELECT user_id,points FROM completion_log WHERE quest_id=?',(qid,)).fetchall(),[('10',5)] if done_first else [])
                    if not done_first:self.assertEqual(w.ownership(qid)[0],'20')
                    else:self.assertIn('changed',give[1].result['content'])

    async def test_audit9_done_and_trade_acceptance_both_orders(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for done_first in (True,False):
                ids=[]
                for uid in (10,20):
                    self.ui.create_chore(f'Trade race {done_first} {uid}','daily','5','')
                    qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0];ids.append(qid)
                    self.ui.reassign(qid,uid,'occurrence',self.ui.reassign_snapshot(qid))
                offered,requested=ids
                self.ui.propose_trade(10,offered,requested,self.ui.trade_snapshot(offered),self.ui.trade_snapshot(requested))
                tid=self.db.execute('SELECT MAX(id) FROM chore_trades').fetchone()[0]
                inbox=self.ui.TradeInboxView(20,selected=tid)
                accept=(next(c for c in inbox.children if getattr(c,'label',None)=='Accept trade').callback,Interaction(20))
                done=(next(c for c in w.Card(10,offered).children if getattr(c,'label',None)=='Done').callback,Interaction())
                await self.audit9_queue(*( (done,accept) if done_first else (accept,done) ))
                self.assertEqual(self.db.execute('SELECT status FROM chore_trades WHERE id=?',(tid,)).fetchone(),('expired',) if done_first else ('accepted',))
                self.assertEqual(self.db.execute('SELECT user_id FROM completion_log WHERE quest_id=?',(offered,)).fetchall(),[('10',)] if done_first else [])
                self.assertEqual(self.ui.owned_scope(requested)[0],'20' if done_first else '10')

    async def test_audit9_done_and_schedule_change_both_orders(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            for done_first in (True,False):
                self.ui.create_chore('Schedule race '+str(done_first),'weekly','5','')
                qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0]
                self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=?",(qid,));self.db.commit()
                done=(next(c for c in w.Card(10,qid).children if getattr(c,'label',None)=='Done').callback,Interaction())
                day=self.ui.ChooseDayView(10,qid,self.ui.snapshot(qid),day='wednesday')
                change=(next(c for c in day.children if getattr(c,'label',None)=='Save day').callback,Interaction())
                await self.audit9_queue(*( (done,change) if done_first else (change,done) ))
                self.assertEqual(self.db.execute('SELECT completed,frequency FROM quests WHERE id=?',(qid,)).fetchone(),(1,'weekly') if done_first else (0,'wednesday'))
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log WHERE quest_id=?',(qid,)).fetchone(),(int(done_first),))

    async def test_audit9_completion_failure_rolls_back_points_history_and_revision(self):
        import sqlite3
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',30,2)")
            self.db.execute("CREATE TRIGGER audit9_abort BEFORE INSERT ON completion_log BEGIN SELECT RAISE(ABORT,'audit failure'); END");self.db.commit()
            before={t:self.db.execute('SELECT * FROM '+t).fetchall() for t in ('quests','users','claims','chore_timing','chore_revisions','completion_log')}
            with self.assertRaises(sqlite3.IntegrityError):await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
            self.assertEqual(before,{t:self.db.execute('SELECT * FROM '+t).fetchall() for t in before})

    async def test_audit9_restart_keeps_unchanged_pending_trade_valid(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            before=self.db.execute('SELECT * FROM chore_revisions ORDER BY quest_id').fetchall()
            path=Path(self.app.__file__)
            spec=importlib.util.spec_from_file_location('sprig_audit9_restarted',path)
            restarted=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(restarted)
            try:
                with patch.object(restarted,'now_local',return_value=self.app.now_local()):
                    self.assertEqual(before,restarted.db.execute('SELECT * FROM chore_revisions ORDER BY quest_id').fetchall())
                    self.assertIn('accepted',restarted.chore_ui.respond_trade(20,1,'accept'))
                    self.assertEqual(restarted.chore_ui.owned_scope(1)[0],'20')
                    self.assertEqual(restarted.chore_ui.owned_scope(other)[0],'10')
            finally:
                await restarted.bot.close();restarted.db.close()

    async def test_audit9_revision_persists_and_ignores_noop_updates(self):
        import sqlite3
        from contextlib import closing
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET assigned_to='20' WHERE id=2");self.db.commit()
            revision=self.db.execute('SELECT revision FROM chore_revisions WHERE quest_id=2').fetchone()
            self.db.execute('UPDATE quests SET frequency=LOWER(TRIM(frequency)),assigned_to=assigned_to WHERE id=2');self.db.commit()
            self.assertEqual(revision,self.db.execute('SELECT revision FROM chore_revisions WHERE quest_id=2').fetchone())
            path=self.db.execute('PRAGMA database_list').fetchone()[2]
            with closing(sqlite3.connect(path)) as second:
                self.assertEqual(revision,second.execute('SELECT revision FROM chore_revisions WHERE quest_id=2').fetchone())

    async def test_audit9_lost_completion_reply_retry_does_not_award_again(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T10:00:00'):
            view=w.Card(10,2)
            done=next(c for c in view.children if getattr(c,'label',None)=='Done')
            failed=Interaction();failed.response.edit_message=AsyncMock(side_effect=ConnectionError('reply unavailable'))
            with self.assertRaises(ConnectionError):await done.callback(failed)
            retry=Interaction();await done.callback(retry)
            self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='10'").fetchone(),(10,1))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertIn('changed',retry.response.payload['embed'].description)

    async def test_audit9_trade_accept_and_cancel_compete_without_partial_swap(self):
        with self.clock('2026-10-20T10:00:00'):
            for accept_first in (True,False):
                ids=[]
                for uid in (10,20):
                    self.ui.create_chore(f'Cancel trade {accept_first} {uid}','daily','5','')
                    qid=self.db.execute('SELECT MAX(id) FROM quests').fetchone()[0];ids.append(qid)
                    self.ui.reassign(qid,uid,'occurrence',self.ui.reassign_snapshot(qid))
                offered,requested=ids
                self.ui.propose_trade(10,offered,requested,self.ui.trade_snapshot(offered),self.ui.trade_snapshot(requested))
                tid=self.db.execute('SELECT MAX(id) FROM chore_trades').fetchone()[0]
                accept=(next(c for c in self.ui.TradeInboxView(20,selected=tid).children if getattr(c,'label',None)=='Accept trade').callback,Interaction(20))
                cancel=(next(c for c in self.ui.TradeInboxView(10,selected=tid).children if getattr(c,'label',None)=='Cancel proposal').callback,Interaction())
                await self.audit9_queue(*( (accept,cancel) if accept_first else (cancel,accept) ))
                self.assertEqual(self.db.execute('SELECT status FROM chore_trades WHERE id=?',(tid,)).fetchone(),('accepted',) if accept_first else ('canceled',))
                self.assertEqual([self.ui.owned_scope(qid)[0] for qid in ids],['20','10'] if accept_first else ['10','20'])
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_audit9_trade_rollback_preserves_revision_and_can_retry_freshly(self):
        import sqlite3
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            before=self.db.execute('SELECT * FROM chore_revisions ORDER BY quest_id').fetchall()
            self.db.execute(f"CREATE TRIGGER audit9_swap_abort BEFORE UPDATE ON claims WHEN NEW.quest_id={other} BEGIN SELECT RAISE(ABORT,'swap failure'); END");self.db.commit()
            with self.assertRaises(sqlite3.IntegrityError):self.ui.respond_trade(20,1,'accept')
            self.assertEqual(before,self.db.execute('SELECT * FROM chore_revisions ORDER BY quest_id').fetchall())
            self.assertEqual(self.ui.owned_scope(1)[0],'10');self.assertEqual(self.ui.owned_scope(other)[0],'20')
            self.db.execute('DROP TRIGGER audit9_swap_abort');self.db.commit()
            self.assertIn('accepted',self.ui.respond_trade(20,1,'accept'))

    async def test_audit9_stale_done_after_undo_does_not_recomplete(self):
        with self.clock('2026-10-20T10:00:00'):
            old=self.ui.PersonalView(10,'mine',selected=2)
            await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
            event_id=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
            self.assertIn('undone',self.ui.undo_completion(10,event_id))
            event=Interaction();await old.act(event,'done')
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertIn('changed',event.response.payload['embed'].description)

    async def test_audit9_trade_expires_when_ownership_changes_away_and_back(self):
        with self.clock('2026-10-20T10:00:00'):
            other=self.setup_trade()
            self.ui.propose_trade(10,1,other,self.ui.trade_snapshot(1),self.ui.trade_snapshot(other))
            self.ui.reassign(1,30,'occurrence',self.ui.reassign_snapshot(1))
            self.ui.reassign(1,10,'occurrence',self.ui.reassign_snapshot(1))
            text=self.ui.respond_trade(20,1,'accept')
            self.assertIn('expired',text)
            self.assertEqual(self.ui.owned_scope(1),('10','occurrence'))
            self.assertEqual(self.ui.owned_scope(other),('20','occurrence'))

    async def test_audit9_old_week_release_cannot_remove_fresh_signup(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.signup(10,1,self.ui.week_key())
            old=self.ui.WeeklyView(10,selected=1)
            await old.act(Interaction(),True)
            self.ui.signup(10,1,self.ui.week_key())
            event=Interaction();await old.act(event,True)
            self.assertEqual(self.ui.weekly_owner(1),'10')
            self.assertIn('changed',event.result['embed'].description)

    async def test_audit9_stale_completion_after_schedule_edit_and_revert(self):
        with self.clock('2026-10-20T10:00:00'):
            old=self.ui.PersonalView(10,'mine',selected=2)
            self.ui.update_chore(2,'My bathroom','tuesday','10','',self.ui.snapshot(2))
            self.ui.update_chore(2,'My bathroom','weekly','10','',self.ui.snapshot(2))
            await old.act(Interaction(),'done')
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))

    async def test_attention_combines_reasons_once_and_preserves_household_data(self):
        w=self.ui.workspace;p=self.ui.planning
        with self.clock('2026-10-19T09:00:00'):
            self.ui.create_chore('Monday blocked','monday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Monday blocked'").fetchone()[0]
            self.db.execute('UPDATE quests SET assigned_to=? WHERE id=?',('10',qid));self.db.commit()
            self.assertIn('saved',p.report_help(10,qid,'Need supplies','No cleaner',p.help_snapshot(qid)))
        with self.clock('2026-10-20T09:00:00'):
            self.db.execute('UPDATE quests SET assigned_to=NULL WHERE id=?',(qid,));self.db.commit()
            before={t:self.db.execute('SELECT * FROM '+t).fetchall() for t in ('quests','users','claims','completion_log','chore_help')}
            view=w.Attention(10,Interaction().guild)
            rows=[r for r in view.entries if r[0][0]==qid]
            self.assertEqual(len(rows),1);self.assertEqual(rows[0][1:3],(True,True));self.assertEqual(rows[0][3][4],'Need supplies')
            field=next(f for f in view.embed.fields if f.name=='Monday blocked')
            for text in ('Overdue','Needs someone','Blocked','No cleaner'):self.assertIn(text,field.value)
            self.assertEqual(before,{t:self.db.execute('SELECT * FROM '+t).fetchall() for t in before})

    async def test_attention_today_future_completed_archived_and_no_deadline(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            for name,freq in [('Today','tuesday'),('Future','wednesday'),('One time','one-time'),('Archived','daily')]:self.ui.create_chore(name,freq,'5','')
            ids=dict(self.db.execute('SELECT name,id FROM quests'))
            self.db.execute("UPDATE quests SET assigned_to='10' WHERE name='Today'")
            self.db.execute("INSERT INTO archived_chores VALUES(?,'10','now')",(ids['Archived'],))
            self.db.execute('UPDATE quests SET completed=1 WHERE id=2');self.db.commit()
            rows={r[0][1]:r for r in w.Attention(10).entries}
            self.assertNotIn('Today',rows);self.assertNotIn('Future',rows);self.assertNotIn('Archived',rows);self.assertNotIn('My bathroom',rows)
            self.assertEqual(rows['One time'][1:3],(False,True));self.assertIsNone(rows['One time'][4])

    async def test_attention_am_boundary_and_moved_occurrence_day_end(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            self.ui.create_chore('Morning shift','daily-am','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Morning shift'").fetchone()[0]
            self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=?",(qid,));self.db.commit()
            self.assertNotIn(qid,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-20T12:00:00'):
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==qid)[1])
            self.db.execute("INSERT INTO occurrence_moves VALUES(?,'2026-10-21')",(qid,));self.db.commit()
            self.assertNotIn(qid,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-21T23:59:59'):
            self.assertNotIn(qid,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-22T00:00:00'):
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==qid)[1])

    async def test_attention_flexible_deadline_persists_and_checklist_edit_does_not_erase_overdue(self):
        w=self.ui.workspace;p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            w.Attention(10)
            self.assertNotIn(2,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-25T17:59:59'):
            self.assertNotIn(2,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-25T18:00:00'):
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==2)[1])
            p.save_plan(2,'10','Wipe sink',p.plan(2))
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==2)[1])
            saved=self.db.execute('SELECT * FROM attention_windows WHERE quest_id=2').fetchone()
            w.recovery.live.clear();w.Attention(10)
            self.assertEqual(saved,self.db.execute('SELECT * FROM attention_windows WHERE quest_id=2').fetchone())

    async def test_attention_skip_missed_resolved_help_and_next_week_signup(self):
        w=self.ui.workspace;p=self.ui.planning
        with self.clock('2026-10-19T09:00:00'):
            self.ui.create_chore('Skip Monday','monday','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Skip Monday'").fetchone()[0]
            self.ui.timing.set_policy(qid,'skip')
            self.ui.signup(10,1,self.ui.week_key(1))
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==1)[2])
            self.assertIn('saved',p.report_help(10,2,'Need help','Heavy',p.help_snapshot(2)))
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==2)[3])
            p.resolve_help(20,2,p.help_snapshot(2))
            self.assertNotIn(2,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-20T09:00:00'):
            self.assertNotIn(qid,[r[0][0] for r in w.Attention(10).entries])

    async def test_attention_dashboard_navigation_paging_card_back_and_recovery(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            for n in range(11):self.ui.create_chore(f'Attention {n:02d}','one-time','5','')
            event=Interaction()
            await next(c for c in w.Dashboard(10).children if c.label=='Needs attention').callback(event)
            view=event.response.payload['view'];self.assertIsInstance(view,w.Attention)
            self.assertIn('Page 1 of 3',view.embed.footer.text)
            await next(c for c in view.children if getattr(c,'label',None)=='Next').callback(event)
            view=event.response.payload['view'];self.assertEqual(view.page,1)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=[picker.options[0].value]
            await picker.callback(event);card=event.response.payload['view']
            await next(c for c in card.children if getattr(c,'label',None)=='Back').callback(event)
            self.assertEqual(event.response.payload['view'].page,1)
            panel=w.render(w.Attention(10,page=1));token=panel.recovery_token;w.recovery.live.clear()
            await w.recovery.route(event,token,'r')
            self.assertIsInstance(event.response.payload['view'],w.Attention);self.assertEqual(event.response.payload['view'].page,1)
            self.assertFalse(await view.interaction_check(Interaction(20)))
            self.assert_screen_limits(w.Dashboard(301104023405199361));self.assert_screen_limits(view)
            self.assertTrue(panel.has_components_v2())

    async def test_attention_monthly_and_daily_boundaries_with_fall_dst(self):
        w=self.ui.workspace
        with self.clock('2026-10-31T09:00:00'):
            self.ui.create_chore('Monthly check','monthly','5','')
            self.db.execute("UPDATE quests SET assigned_to='10'");self.db.commit()
            self.assertEqual(w.Attention(10).entries,[])
        with self.clock('2026-11-01T00:00:00'):
            rows={r[0][1]:r for r in w.Attention(10).entries}
            self.assertTrue(rows['Monthly check'][1]);self.assertTrue(rows['Fill dishwasher'][1])
            self.assertEqual(rows['Monthly check'][4].hour,0)
        with self.clock('2026-11-01T03:00:00'):
            rows={r[0][1]:r for r in w.Attention(10).entries}
            self.assertTrue(rows['Monthly check'][1]);self.assertTrue(rows['Fill dishwasher'][1])

    async def test_attention_completed_occurrence_gets_new_flexible_window(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=1");self.db.commit()
            w.Attention(10)
        with self.clock('2026-10-21T09:00:00'):
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==1)[1])
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            self.assertNotIn(1,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-22T09:00:00'):
            self.assertNotIn(1,[r[0][0] for r in w.Attention(10).entries])
        with self.clock('2026-10-23T00:00:00'):
            self.assertTrue(next(r for r in w.Attention(10).entries if r[0][0]==1)[1])

    async def test_attention_empty_and_shorter_page_clamps(self):
        w=self.ui.workspace
        with self.clock('2026-10-20T09:00:00'):
            self.db.execute("UPDATE quests SET completed=1");self.db.commit()
            view=w.Attention(10,page=99)
            self.assertEqual(view.entries,[]);self.assertEqual(view.page,0)
            self.assertIn('Nothing needs attention',[f.name for f in view.embed.fields])
            self.assertIn('Page 1 of 1',view.embed.footer.text)

    async def test_points_reset_owner_only_button_and_forged_confirmation(self):
        w=self.ui.workspace;owner=301104023405199361
        self.assertNotIn('Reset points',[getattr(c,'label',None) for c in w.Points(10).children])
        self.assertIn('Reset points',[getattr(c,'label',None) for c in w.Points(owner).children])
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',25,3)");self.db.commit()
        view=w.ResetPoints(owner,target='10',confirm=True)
        await view.apply(Interaction(20))
        await w.ResetPoints(10,target='10',confirm=True).apply(Interaction(10))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(25,))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM points_reset_log').fetchone(),(0,))

    async def test_points_reset_one_keeps_streak_history_and_other_accounts(self):
        w=self.ui.workspace;owner=301104023405199361
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('20',40,8)");self.db.commit()
        before=self.db.execute("SELECT streak,last_completed FROM users WHERE id='10'").fetchone()
        history=self.db.execute('SELECT * FROM completion_log').fetchall()
        quests=self.db.execute('SELECT * FROM quests').fetchall()
        view=w.ResetPoints(owner,target='10',confirm=True)
        self.assertIn('keep unchanged',view.embed.description)
        await view.apply(Interaction(owner))
        self.assertEqual(self.db.execute("SELECT points,streak,last_completed FROM users WHERE id='10'").fetchone(),(0,*before))
        self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='20'").fetchone(),(40,8))
        self.assertEqual(self.db.execute('SELECT * FROM completion_log').fetchall(),history)
        self.assertEqual(self.db.execute('SELECT * FROM quests').fetchall(),quests)
        self.assertEqual(self.db.execute('SELECT actor,user_id FROM points_reset_log').fetchall(),[(str(owner),'10')])

    async def test_points_reset_everyone_optional_streaks_and_duplicate_click(self):
        owner=301104023405199361;w=self.ui.workspace
        self.db.executemany('INSERT INTO users(id,points,streak,last_completed) VALUES(?,?,?,?)',[('10',25,3,'2026-10-20'),('20',40,8,'2026-10-19')]);self.db.commit()
        view=w.ResetPoints(owner,reset_streaks=True,confirm=True)
        self.assertIn('2 account(s), 65 points',view.embed.description)
        self.assertIn('reset to zero',view.embed.description)
        await asyncio.gather(view.apply(Interaction(owner)),view.apply(Interaction(owner)))
        self.assertEqual(self.db.execute('SELECT points,streak,last_completed FROM users').fetchall(),[(0,0,None),(0,0,None)])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM points_reset_log').fetchone(),(2,))

    async def test_points_reset_stale_confirmation_and_cancel_are_read_only(self):
        w=self.ui.workspace;owner=301104023405199361
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',25,3)");self.db.commit()
        view=w.ResetPoints(owner,confirm=True)
        cancel=next(c for c in view.children if getattr(c,'label',None)=='Cancel')
        await cancel.callback(Interaction(owner))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(25,))
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('20',5,1)");self.db.commit()
        await view.apply(Interaction(owner))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM points_reset_log').fetchone(),(0,))
        self.assertEqual(self.db.execute('SELECT SUM(points) FROM users').fetchone(),(30,))

    async def test_points_reset_atomic_rollback_and_epoch_blocks_old_undo(self):
        owner=301104023405199361;w=self.ui.workspace
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
        self.db.execute("CREATE TRIGGER fail_reset BEFORE INSERT ON points_reset_log BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        self.db.execute('DROP TRIGGER fail_reset');self.db.commit()
        await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        self.db.execute("UPDATE users SET points=10 WHERE id='10'");self.db.commit()
        result=self.ui.undo_completion(10,event)
        self.assertIn('cannot safely',result)
        self.assertEqual(self.db.execute('SELECT undone_at FROM completion_log WHERE id=?',(event,)).fetchone(),(None,))

    async def test_points_reset_selector_and_v2_confirmation_limits(self):
        owner=301104023405199361;w=self.ui.workspace
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',25,3)");self.db.commit()
        view=w.ResetPoints(owner)
        picker=next(c for c in view.children if isinstance(c,discord.ui.UserSelect))
        picker._values=[SimpleNamespace(id=10,bot=False)]
        interaction=Interaction(owner)
        await picker.callback(interaction)
        confirm=interaction.response.payload['view']
        self.assertEqual(confirm.target,'10')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM points_reset_log').fetchone(),(0,))
        self.assert_screen_limits(confirm)
        self.assertTrue(w.render(confirm).to_components())


    def reset_batch(self):
        return self.db.execute('SELECT id,actor,details,created_at,undone_at FROM points_reset_batches ORDER BY id DESC LIMIT 1').fetchone()

    async def test_owner_recovery_reset_undo_preserves_or_restores_streaks(self):
        owner=301104023405199361;w=self.ui.workspace
        for reset_streaks in (False,True):
            self.db.execute("INSERT OR REPLACE INTO users(id,points,streak,last_completed) VALUES('10',35,4,'2026-10-20')");self.db.commit()
            await w.ResetPoints(owner,target='10',reset_streaks=reset_streaks,confirm=True).apply(Interaction(owner))
            batch=self.reset_batch()
            self.assertIn('undone',w.undo_points_reset(owner,batch[0],batch))
            self.assertEqual(self.db.execute("SELECT points,streak,last_completed FROM users WHERE id='10'").fetchone(),(35,4,'2026-10-20'))
            self.assertIsNotNone(self.reset_batch()[4])
            self.assertIn('already undone',w.undo_points_reset(owner,batch[0],batch))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM owner_action_log WHERE action='undo_points_reset'").fetchone(),(2,))

    async def test_owner_recovery_reset_undo_everyone_is_atomic_and_rejects_new_activity(self):
        owner=301104023405199361;w=self.ui.workspace
        self.db.executemany('INSERT INTO users(id,points,streak) VALUES(?,?,?)',[('10',15,2),('20',20,3)]);self.db.commit()
        await w.ResetPoints(owner,confirm=True).apply(Interaction(owner))
        batch=self.reset_batch()
        self.db.execute("UPDATE users SET points=5 WHERE id='20'");self.db.commit()
        self.assertIn('Nothing restored',w.undo_points_reset(owner,batch[0],batch))
        self.assertEqual(self.db.execute('SELECT points FROM users ORDER BY id').fetchall(),[(0,),(5,)])
        self.db.execute("UPDATE users SET points=0 WHERE id='20'");self.db.commit()
        self.db.execute("CREATE TRIGGER fail_recovery BEFORE INSERT ON owner_action_log BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):w.undo_points_reset(owner,batch[0],batch)
        self.assertEqual(self.db.execute('SELECT points FROM users ORDER BY id').fetchall(),[(0,),(0,)])
        self.assertIsNone(self.reset_batch()[4])
        self.db.execute('DROP TRIGGER fail_recovery');self.db.commit()
        self.assertIn('undone',w.undo_points_reset(owner,batch[0],batch))
        self.assertEqual(self.db.execute('SELECT points FROM users ORDER BY id').fetchall(),[(15,),(20,)])

    async def test_owner_recovery_reset_undo_checks_completion_watermark_and_later_resets(self):
        owner=301104023405199361;w=self.ui.workspace
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',10,2)");self.db.commit()
        await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        batch=self.reset_batch()
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        self.db.execute("UPDATE users SET points=0,streak=2,last_completed=NULL WHERE id='10'");self.db.commit()
        self.assertIn('Nothing restored',w.undo_points_reset(owner,batch[0],batch))
        await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        self.assertIn('Nothing restored',w.undo_points_reset(owner,batch[0],batch))

    async def test_owner_recovery_reset_undo_private_confirmation_permissions_and_cancel(self):
        owner=301104023405199361;w=self.ui.workspace
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',10,2)");self.db.commit()
        await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        batch=self.reset_batch()
        self.assertIn('Only ginaria',w.undo_points_reset(10,batch[0],batch))
        self.assertNotIn('Reset history / Undo',[getattr(c,'label',None) for c in w.Points(10).children])
        history=w.ResetHistory(owner)
        self.assertFalse(await history.interaction_check(Interaction(10)))
        button=next(c for c in history.children if getattr(c,'label',None)=='Undo points reset')
        bad=Interaction(10);await button.callback(bad)
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(0,))
        good=Interaction(owner);await button.callback(good)
        confirmation=good.response.payload['view']
        self.assertIn('Undo this points reset',confirmation.embed.title)
        cancel=next(c for c in confirmation.children if getattr(c,'label',None)=='Cancel')
        await cancel.callback(Interaction(owner))
        self.assertIsNone(self.reset_batch()[4])
        confirm=next(c for c in confirmation.children if getattr(c,'label',None)=='Confirm')
        await asyncio.gather(confirm.callback(Interaction(owner)),confirm.callback(Interaction(owner)))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM owner_action_log WHERE action='undo_points_reset'").fetchone(),(1,))

    async def test_owner_recovery_completion_correction_preserves_audit_and_original_user(self):
        owner=301104023405199361
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
        self.assertIn('Only ginaria',self.ui.owner_undo_completion(20,event))
        self.assertIn('restored',self.ui.owner_undo_completion(owner,event))
        self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='10'").fetchone(),(0,0))
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
        self.assertIsNotNone(self.db.execute('SELECT undone_at FROM completion_log').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT actor,action,target FROM owner_action_log').fetchall(),[(str(owner),'correct_completion',str(event))])
        self.assertIn('no longer available',self.ui.owner_undo_completion(owner,event))

    async def test_owner_recovery_completion_correction_confirmation_and_guardrails(self):
        owner=301104023405199361;w=self.ui.workspace
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
        ordinary=w.History(20,2,lambda:w.Dashboard(20))
        self.assertFalse(any(isinstance(c,discord.ui.Select) for c in ordinary.children))
        history=w.History(owner,2,lambda:w.Dashboard(owner))
        picker=next(c for c in history.children if isinstance(c,discord.ui.Select));picker._values=[str(event)]
        interaction=Interaction(owner);await picker.callback(interaction)
        confirmation=interaction.response.payload['view']
        self.assertEqual(confirmation.embed.title,'Correct completion?')
        self.assertIn('10 points',confirmation.embed.description)
        confirm=next(c for c in confirmation.children if getattr(c,'label',None)=='Confirm')
        await confirm.callback(Interaction(20))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        self.db.execute("UPDATE users SET points=15 WHERE id='10'");self.db.commit()
        await confirm.callback(Interaction(owner))
        self.assertIsNone(self.db.execute('SELECT undone_at FROM completion_log').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM owner_action_log').fetchone(),(0,))

    async def test_owner_recovery_completion_correction_transaction_rolls_back(self):
        owner=301104023405199361
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
        self.db.execute("CREATE TRIGGER fail_correction BEFORE INSERT ON owner_action_log BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):self.ui.owner_undo_completion(owner,event)
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(1,))
        self.assertIsNone(self.db.execute('SELECT undone_at FROM completion_log').fetchone()[0])

    async def resolved_review_fixture(self):
        result=self.ui.save_feedback(1,10,'Kid','Too hard','afternoon','8','recovery-review',self.ui.feedback_context(1))
        review=self.db.execute('SELECT MAX(id) FROM chore_feedback').fetchone()[0]
        self.db.execute('UPDATE chore_feedback SET reviewed=1 WHERE id=?',(review,));self.db.commit()
        return review

    async def test_owner_recovery_review_reopen_confirmation_permissions_and_no_dm(self):
        owner=301104023405199361;w=self.ui.workspace
        review=await self.resolved_review_fixture()
        view=w.Inbox(owner,resolved=True)
        self.assertFalse(await view.interaction_check(Interaction(10)))
        self.assertFalse(any(getattr(c,'label',None)=='Reopen review' for c in w.Inbox(10,resolved=True).children))
        reopen=next(c for c in view.children if getattr(c,'label',None)=='Reopen review')
        bad=Interaction(10);await reopen.callback(bad)
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback WHERE id=?',(review,)).fetchone(),(1,))
        good=Interaction(owner);await reopen.callback(good)
        confirmation=good.response.payload['view']
        self.assertIn('Reopen this review',confirmation.embed.title)
        confirm=next(c for c in confirmation.children if getattr(c,'label',None)=='Confirm')
        await confirm.callback(Interaction(20))
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback WHERE id=?',(review,)).fetchone(),(1,))
        await asyncio.gather(confirm.callback(Interaction(owner)),confirm.callback(Interaction(owner)))
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback WHERE id=?',(review,)).fetchone(),(0,))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM owner_action_log WHERE action='reopen_review'").fetchone(),(1,))
        self.dm.send.assert_not_awaited()
        self.assertIn('1 of 1 open reviews',w.Inbox(owner).embed.description)

    async def test_owner_recovery_review_reopen_rolls_back_if_audit_fails(self):
        owner=301104023405199361;w=self.ui.workspace
        review=await self.resolved_review_fixture()
        view=w.Inbox(owner,resolved=True)
        button=next(c for c in view.children if getattr(c,'label',None)=='Reopen review')
        i=Interaction(owner);await button.callback(i)
        confirm=next(c for c in i.response.payload['view'].children if getattr(c,'label',None)=='Confirm')
        self.db.execute("CREATE TRIGGER fail_reopen BEFORE INSERT ON owner_action_log BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):await confirm.callback(Interaction(owner))
        self.assertEqual(self.db.execute('SELECT reviewed FROM chore_feedback WHERE id=?',(review,)).fetchone(),(1,))

    async def test_owner_recovery_views_fit_discord_and_empty_history(self):
        owner=301104023405199361;w=self.ui.workspace
        self.assertIn('No recorded',w.ResetHistory(owner).embed.description)
        await self.resolved_review_fixture()
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',25,3)");self.db.commit()
        await w.ResetPoints(owner,target='10',confirm=True).apply(Interaction(owner))
        for view in (w.Points(owner),w.ResetHistory(owner),w.Inbox(owner,resolved=True)):
            self.assert_screen_limits(view)
            self.assertTrue(w.render(view).to_components())


    async def test_planning_estimate_validation_and_stale_edit(self):
        p=self.ui.planning
        self.assertIn('saved',p.save_plan(1,'15','Load cups\nLoad plates',p.plan(1)))
        saved=p.plan(1)
        for minutes,text in [('-1','A'),('1.5','A'),('1441','A'),('10','A\na'),('10','x'*81),('10','\n'.join(str(i) for i in range(13)))]:
            self.assertNotIn('saved',p.save_plan(1,minutes,text,saved))
            self.assertEqual(p.plan(1),saved)
        self.assertIn('changed',p.save_plan(1,'20','A',(None,'[]',0)))
        self.assertIn('saved',p.save_plan(1,'','',saved))
        self.assertEqual(p.plan(1)[:2],(None,'[]'))

    async def test_planning_checklist_required_done_and_undo_restores_progress(self):
        p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            p.save_plan(2,'20','Sink\nFloor',p.plan(2))
            await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))
            view=p.Checklist(10,2);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0','1']
            await picker.callback(Interaction())
            self.assertTrue(p.complete(2))
            await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
            event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
            self.assertIn('restored',self.ui.undo_completion(10,event))
            self.assertEqual(p.checked(2),{0,1})

    async def test_planning_checklist_uncheck_reassign_stale_and_next_occurrence(self):
        p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            p.save_plan(2,5,'One\nTwo',p.plan(2))
            view=p.Checklist(10,2);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0']
            await picker.callback(Interaction())
            await picker.callback(Interaction())
            self.assertEqual(p.checked(2),{0})
            self.assertFalse(any(isinstance(c,discord.ui.Select) for c in p.Checklist(20,2).children))
            self.db.execute("UPDATE quests SET assigned_to='20' WHERE id=2");self.db.commit()
            view=p.Checklist(20,2);select=next(c for c in view.children if isinstance(c,discord.ui.Select));select._values=[]
            await select.callback(Interaction(10));self.assertEqual(p.checked(2),{0})
            await select.callback(Interaction(20));self.assertEqual(p.checked(2),set())
            select._values=['0'];await p.Checklist(20,2).interaction_check(Interaction(20))
        with self.clock('2026-10-26T10:00:00'):self.assertEqual(p.checked(2),set())

    async def test_planning_checklist_edits_reset_steps_not_estimate_progress(self):
        p=self.ui.planning
        p.save_plan(2,5,'One',p.plan(2))
        view=p.Checklist(10,2);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
        p.save_plan(2,10,'One',p.plan(2));self.assertEqual(p.checked(2),{0})
        p.save_plan(2,10,'Different',p.plan(2));self.assertEqual(p.checked(2),set())
        old=p.PlanModal(10,2,lambda:self.ui.workspace.Card(10,2))
        self.assertFalse(await self.ui.workspace.View(10).interaction_check(Interaction(20)))

    async def test_planning_inline_checklist_button_and_estimate(self):
        p=self.ui.planning;w=self.ui.workspace
        p.save_plan(2,15,'Sink',p.plan(2))
        browse=w.Browse(10,'mine')
        self.assertIn('~15 min',str(browse.embed.to_dict()))
        wire=w.render(browse)
        section=next(item for item in wire.children if isinstance(item,discord.ui.Section))
        self.assertEqual(section.accessory.label,'Checklist')
        i=Interaction();await section.accessory.callback(i)
        self.assertIsInstance(i.response.payload['view'],p.Checklist)

    async def test_planning_split_copies_estimates_and_checklist(self):
        p=self.ui.planning;w=self.ui.workspace
        self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1");self.db.commit()
        p.save_plan(1,7,'Put dishes away',p.plan(1))
        w.split_daily_shifts(1,self.ui.reassign_snapshot(1))
        pm=self.db.execute('SELECT pm_id FROM chore_shift_splits WHERE original_id=1').fetchone()[0]
        self.assertEqual(p.plan(pm),p.plan(1))

    async def test_planning_reminders_default_off_and_personal_permissions(self):
        p=self.ui.planning
        with self.clock('2026-10-20T09:00:00'):
            await p.send_due_reminders();self.dm.send.assert_not_awaited()
            view=p.Reminders(10);toggle=next(c for c in view.children if getattr(c,'label',None)=='Turn on')
            await toggle.callback(Interaction(20));self.assertEqual(p.settings(10)[0],0)
            await toggle.callback(Interaction(10));self.assertEqual(p.settings(10)[0],1)
            self.assertEqual(p.settings(20)[0],0)
            await p.send_due_reminders();self.dm.send.assert_awaited_once()
            self.assertIn('My bathroom',self.dm.send.call_args.args[0])
            self.assertEqual(p.settings(20)[0],0)

    async def test_planning_reminder_time_validation_and_toggle_off(self):
        p=self.ui.planning;expected=p.settings(10)
        for value in ('','9:00','25:00','09:60',','.join(f'{h:02}:00' for h in range(11))):
            self.assertIn('Use one',p.save_reminders(10,True,value,expected))
        self.assertIn('on',p.save_reminders(10,True,'17:00,09:00',expected))
        self.assertIn('changed',p.save_reminders(10,False,'09:00',expected))
        view=p.Reminders(10);toggle=next(c for c in view.children if getattr(c,'label',None)=='Turn off');await toggle.callback(Interaction())
        with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()

    async def test_planning_reminder_ten_times_modal_and_eleventh_rejected(self):
        import json
        p=self.ui.planning
        times=[f'{h:02}:00' for h in range(10)]
        modal=p.ReminderTimes(10)
        text=', '.join(reversed(times))
        self.assertLessEqual(len(text),modal.times.max_length)
        self.assertIn('10',modal.times.label)
        modal.times._value=text
        await modal.on_submit(Interaction(10))
        saved=p.settings(10)
        self.assertEqual(saved[0],0)
        self.assertEqual(json.loads(saved[1]),times)
        self.assertEqual(p.ReminderTimes(10).times.default,', '.join(times))
        self.assertIn('one to ten',p.save_reminders(10,True,','.join(times+['10:00']),saved))
        self.assertEqual(p.settings(10),saved)
        self.assertIn('on',p.save_reminders(10,True,','.join(times),saved))
        with self.clock('2026-10-20T09:00:00'):
            await p.send_due_reminders()
            await p.send_due_reminders()
        self.dm.send.assert_awaited_once()

    async def test_planning_reminders_deduplicate_concurrent_and_restart(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        with self.clock('2026-10-20T09:01:00'):
            await asyncio.gather(p.send_due_reminders(),p.send_due_reminders())
            await p.send_due_reminders()
        self.dm.send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchall(),[('sent',)])

    async def test_planning_reminders_skip_away_unowned_archived_and_downtime(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        with self.clock('2026-10-20T09:16:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        self.ui.attendance.add('10','2026-10-20','2026-10-20','away')
        with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        self.db.execute('UPDATE availability_exceptions SET active=0');self.db.execute("INSERT INTO archived_chores VALUES(2,'10','now')");self.db.commit()
        with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()

    async def test_planning_reminder_failed_send_not_retried(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10));self.dm.send.side_effect=TimeoutError()
        with self.clock('2026-10-20T09:00:00'):
            await p.send_due_reminders();await p.send_due_reminders()
        self.dm.send.assert_awaited_once()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchone(),('failed_uncertain',))

    async def test_planning_reminder_optout_during_name_fetch_cancels(self):
        p=self.ui.planning;p.save_reminders(10,True,'09:00',p.settings(10))
        async def fetch(uid):
            p.save_reminders(10,False,'09:00',p.settings(10));return self.dm
        with patch.object(self.app.bot,'get_user',return_value=None),patch.object(self.app.bot,'fetch_user',side_effect=fetch):
            with self.clock('2026-10-20T09:00:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        self.assertEqual(self.db.execute('SELECT status FROM reminder_deliveries').fetchone(),('canceled',))

    async def test_planning_calendar_week_month_day_private_and_no_mutation(self):
        p=self.ui.planning;w=self.ui.workspace
        before=self.db.execute('SELECT * FROM quests').fetchall()
        day=datetime(2026,10,20).date()
        for view in (p.Calendar(10,day=day),p.Calendar(10,day=day,mode='month'),p.Day(10,day),p.Day(10,day,flexible=True)):
            self.assert_screen_limits(view);self.assertTrue(w.render(view).to_components())
            self.assertFalse(await view.interaction_check(Interaction(20)))
        self.assertEqual(self.db.execute('SELECT * FROM quests').fetchall(),before)
        month=p.Calendar(10,day=day,mode='month')
        self.assertIn('Mo Tu We Th Fr Sa Su',str(month.embed.to_dict()))
        self.assertEqual(sum(len(c.options) for c in month.children if isinstance(c,discord.ui.Select)),31)

    async def test_planning_calendar_flexible_and_fixed_day_separation(self):
        p=self.ui.planning;day=datetime(2026,10,20).date()
        self.assertNotIn(2,[q[0] for q,uid in p.project(day)])
        self.assertIn(2,[q[0] for q,uid in p.project(day,flexible=True)])
        self.db.execute("UPDATE quests SET frequency='tuesday' WHERE id=2");self.db.commit()
        self.assertIn(2,[q[0] for q,uid in p.project(day)])
        self.assertNotIn(2,[q[0] for q,uid in p.project(day+timedelta(days=1))])

    async def test_planning_calendar_reservations_ongoing_claims_and_handoff(self):
        p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            self.db.executemany('INSERT INTO week_signups VALUES(?,?,?)',[(1,'2026-10-18','10'),(1,'2026-10-25','20')]);self.db.commit()
            self.assertEqual(p.owner_on(self.db.execute('SELECT * FROM quests WHERE id=1').fetchone(),datetime(2026,10,25).date()),'10')
            self.assertEqual(p.project(datetime(2026,10,26).date(),20)[0][1],'20')
            self.assertFalse(p.project(datetime(2026,10,26).date(),10))
            self.db.execute("UPDATE quests SET assigned_to='30' WHERE id=1");self.db.commit()
            self.assertEqual(p.project(datetime(2026,10,26).date(),30)[0][1],'30')

    async def test_planning_calendar_moved_occurrence_and_future_details_are_read_only(self):
        p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("INSERT INTO occurrence_moves VALUES(2,'2026-10-23')");self.db.commit()
            day=datetime(2026,10,23).date()
            self.assertIn(2,[q[0] for q,uid in p.project(day)])
            self.assertNotIn(2,[q[0] for q,uid in p.project(day,flexible=True)])
            view=p.Day(10,day,True);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['2'];i=Interaction();await picker.callback(i)
            result=i.response.payload['view']
            self.assertNotIn('Done',[getattr(c,'label',None) for c in result.children])
            self.assertIn('Open current chore',[getattr(c,'label',None) for c in result.children])

    async def test_planning_dashboard_entries_and_large_checklist_limits(self):
        p=self.ui.planning;w=self.ui.workspace
        labels=[getattr(c,'label',None) for c in w.Dashboard(10).children]
        self.assertIn('Calendar',labels);self.assertIn('Reminders',labels)
        p.save_plan(2,1440,'\n'.join(f'{i}: '+'x'*70 for i in range(12)),p.plan(2))
        for view in (p.Checklist(10,2),p.Reminders(10),w.Card(10,2),w.Dashboard(301104023405199361)):
            self.assert_screen_limits(view);wire=w.render(view);self.assertTrue(wire.to_components())


    async def test_planning_overdue_checklist_carries_but_skipped_cycle_starts_fresh(self):
        p=self.ui.planning
        self.db.execute("UPDATE quests SET frequency='daily',assigned_to='10' WHERE id=1");self.db.commit()
        with self.clock('2026-10-20T10:00:00'):
            p.save_plan(1,5,'One',p.plan(1));view=p.Checklist(10,1)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
        with self.clock('2026-10-21T10:00:00'):
            self.assertEqual(p.checked(1),{0})
            self.ui.timing.set_policy(1,'skip')
            view=p.Checklist(10,1);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
            self.assertEqual(p.checked(1),{0})
        with self.clock('2026-10-22T10:00:00'):
            self.app.reset_due_quests();self.assertEqual(p.checked(1),set())

    async def test_planning_old_checklist_wording_does_not_restore_old_checks(self):
        p=self.ui.planning
        p.save_plan(2,5,'One',p.plan(2));view=p.Checklist(10,2)
        picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
        p.save_plan(2,5,'Two',p.plan(2));p.save_plan(2,5,'One',p.plan(2))
        self.assertEqual(p.checked(2),set())

    async def test_planning_checklist_save_rolls_back_on_database_failure(self):
        p=self.ui.planning;p.save_plan(2,5,'One\nTwo',p.plan(2))
        first=p.Checklist(10,2);picker=next(c for c in first.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
        self.db.execute("CREATE TRIGGER fail_check BEFORE INSERT ON checklist_checks WHEN NEW.item=1 BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        view=p.Checklist(10,2);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0','1']
        with self.assertRaises(Exception):await picker.callback(Interaction())
        self.assertEqual(p.checked(2),{0})

    async def test_planning_reminder_dst_missing_hour_skipped_repeated_hour_once(self):
        p=self.ui.planning;p.save_reminders(10,True,'02:30',p.settings(10))
        with self.clock('2026-03-08T03:30:00'):await p.send_due_reminders()
        self.dm.send.assert_not_awaited()
        p.save_reminders(10,True,'01:00',p.settings(10))
        for fold in (0,1):
            when=datetime(2026,11,1,1,1,tzinfo=self.app.QUEST_TIMEZONE,fold=fold)
            with patch.object(self.app,'now_local',return_value=when):await p.send_due_reminders()
        self.dm.send.assert_awaited_once()

    async def test_planning_checklist_new_completion_cycle_is_fresh(self):
        p=self.ui.planning
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET frequency='daily' WHERE id=2");self.db.commit()
            p.save_plan(2,5,'One',p.plan(2));view=p.Checklist(10,2)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
            await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        with self.clock('2026-10-21T10:00:00'):
            self.app.reset_due_quests();self.assertEqual(p.checked(2),set())
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))


    async def test_planning_old_checklist_button_never_completes_and_done_awards_once(self):
        p=self.ui.planning;w=self.ui.workspace
        p.save_plan(2,5,'One',p.plan(2))
        old=w.render(w.Browse(10,'mine'))
        section=next(item for item in old.children if isinstance(item,discord.ui.Section))
        view=p.Checklist(10,2);picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=['0'];await picker.callback(Interaction())
        i=Interaction();await section.accessory.callback(i)
        self.assertIsInstance(i.response.payload['view'],p.Checklist)
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
        view=p.Checklist(10,2);done=next(c for c in view.children if getattr(c,'label',None)=='Done')
        await asyncio.gather(done.callback(Interaction()),done.callback(Interaction()))
        self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))

    async def test_planning_metadata_modal_checks_person_and_stale_settings(self):
        p=self.ui.planning;w=self.ui.workspace
        modal=p.PlanModal(10,2,lambda:w.Card(10,2));modal.minutes._value='12';modal.items._value='One\nTwo'
        await modal.on_submit(Interaction(20));self.assertEqual(p.plan(2),(None,'[]',0))
        await modal.on_submit(Interaction());self.assertEqual(p.plan(2)[0],12)
        modal.minutes._value='20';await modal.on_submit(Interaction());self.assertEqual(p.plan(2)[0],12)
        bad=p.PlanModal(10,2,lambda:w.Card(10,2));i=Interaction();i.guild_id=999
        bad.minutes._value='40';await bad.on_submit(i);self.assertEqual(p.plan(2)[0],12)

    async def test_planning_reminder_modal_changes_times_without_opting_in(self):
        p=self.ui.planning
        modal=p.ReminderTimes(10);modal.times._value='10:00, 19:00'
        await modal.on_submit(Interaction(20));self.assertEqual(p.settings(10)[2],0)
        await modal.on_submit(Interaction())
        self.assertEqual(p.settings(10)[:2],(0,'["10:00", "19:00"]'))
        modal.times._value='11:00';await modal.on_submit(Interaction())
        self.assertEqual(p.settings(10)[1],'["10:00", "19:00"]')


    async def test_support_status_preserves_ownership_completion_points_and_history(self):
        p=self.ui.planning
        before=self.db.execute('SELECT * FROM quests').fetchall()
        expected=p.help_snapshot(2)
        self.assertIn('saved',p.report_help(10,2,'Need supplies','Out of cleaner',expected))
        self.assertEqual(self.db.execute('SELECT * FROM quests').fetchall(),before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone(),(0,))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))
        self.assertIn('Need supplies',p.help_summary(2))
        self.assertIn('Need supplies',str(self.ui.workspace.Browse(10,'mine').embed.to_dict()))
        self.dm.send.assert_not_awaited()

    async def test_support_reports_permissions_validation_and_stale_updates(self):
        p=self.ui.planning;expected=p.help_snapshot(2)
        self.assertIn('Only the person',p.report_help(20,2,'Stuck','Cannot reach',expected))
        for kind,note in [('Other','Text'),('Stuck',''),('Stuck','x'*501)]:
            self.assertNotIn('saved',p.report_help(10,2,kind,note,expected))
        p.report_help(10,2,'Stuck','Cannot reach',expected)
        self.assertIn('changed',p.report_help(10,2,'Need help','Move furniture',expected))
        self.assertEqual(p.help_record(2)[5],'Cannot reach')
        p.report_help(10,2,'Need help','Move furniture',p.help_snapshot(2))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_help').fetchone(),(2,))
        self.assertIsNotNone(self.db.execute('SELECT resolved_at FROM chore_help WHERE id=1').fetchone()[0])

    async def test_support_status_survives_reassign_and_definition_edits(self):
        p=self.ui.planning;p.report_help(10,2,'Need help','Heavy basket',p.help_snapshot(2))
        record=p.help_record(2)
        p.save_plan(2,10,'Lift basket',p.plan(2));self.assertEqual(p.help_record(2),record)
        self.db.execute("UPDATE quests SET assigned_to='20' WHERE id=2");self.db.commit()
        self.assertEqual(p.help_record(2),record)
        self.assertIn('Only the person',p.report_help(10,2,'Stuck','Old owner',p.help_snapshot(2)))
        self.assertIn('saved',p.report_help(20,2,'Need supplies','New owner needs gloves',p.help_snapshot(2)))
        self.assertEqual(p.help_record(2)[3],'20')

    async def test_support_completion_hides_status_undo_restores_it(self):
        p=self.ui.planning
        p.report_help(10,2,'Need help','Heavy',p.help_snapshot(2))
        before=p.help_record(2)
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        self.assertEqual(p.help_summary(2),'')
        event=self.db.execute('SELECT MAX(id) FROM completion_log').fetchone()[0]
        self.ui.undo_completion(10,event)
        self.assertEqual(p.help_record(2),before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_help').fetchone(),(1,))

    async def test_support_resolve_is_confirmed_shared_and_private_permissions_hold(self):
        p=self.ui.planning;p.report_help(10,2,'Need supplies','Soap',p.help_snapshot(2))
        view=p.HelpStatus(20,2);button=next(c for c in view.children if getattr(c,'label',None)=='Mark resolved')
        self.assertNotIn('Stuck',[getattr(c,'label',None) for c in view.children])
        wrong=Interaction(10);await button.callback(wrong);self.assertIsNotNone(p.help_record(2))
        i=Interaction(20);await button.callback(i)
        confirm=i.response.payload['view']
        cancel=next(c for c in confirm.children if getattr(c,'label',None)=='Cancel');await cancel.callback(Interaction(20));self.assertIsNotNone(p.help_record(2))
        save=next(c for c in confirm.children if getattr(c,'label',None)=='Confirm')
        await asyncio.gather(save.callback(Interaction(20)),save.callback(Interaction(20)))
        self.assertIsNone(p.help_record(2))
        self.assertEqual(self.db.execute('SELECT resolved_by,resolution FROM chore_help').fetchone(),('20','Marked resolved'))
        self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
        self.dm.send.assert_not_awaited()

    async def test_support_note_modal_checks_context_and_preserves_notes_on_failure(self):
        p=self.ui.planning
        modal=p.HelpNote(10,2,'Stuck');modal.note._value='Need a hand'
        wrong=Interaction();wrong.guild_id=999;await modal.on_submit(wrong);self.assertIsNone(p.help_record(2))
        await modal.on_submit(Interaction(20));self.assertIsNone(p.help_record(2))
        await modal.on_submit(Interaction());self.assertEqual(p.help_record(2)[5],'Need a hand')
        self.db.execute("CREATE TRIGGER fail_help BEFORE INSERT ON chore_help BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):p.report_help(10,2,'Need help','Updated',p.help_snapshot(2))
        self.assertEqual(p.help_record(2)[5],'Need a hand')

    async def test_support_resolve_rejects_old_cycle_and_archived_issues_hide(self):
        p=self.ui.planning;p.report_help(10,2,'Stuck','Note',p.help_snapshot(2));expected=p.help_snapshot(2)
        self.db.execute("UPDATE quests SET last_completed='2026-10-20T10:00:00-04:00' WHERE id=2");self.db.commit()
        self.assertIn('changed',p.resolve_help(20,2,expected));self.assertIsNone(p.help_record(2))
        self.assertEqual(self.db.execute('SELECT resolved_at FROM chore_help').fetchone(),(None,))
        p.report_help(10,2,'Need help','Current',p.help_snapshot(2))
        self.db.execute("INSERT INTO archived_chores VALUES(2,'10','now')");self.db.commit()
        self.assertEqual(p.help_summary(2),'')
        self.assertIn('0 active',p.NeedsHelp(10).embed.description)

    async def test_support_duplicate_copies_definition_not_history_or_responsibility(self):
        p=self.ui.planning
        await self.ui.PersonalView(10,'mine',selected=2).act(Interaction(),'done')
        p.save_plan(2,12,'Sink\nFloor',p.plan(2))
        self.db.execute("UPDATE quests SET notes='Use gloves',category='bathroom',difficulty='hard' WHERE id=2");self.db.commit()
        self.ui.timing.set_policy(2,'skip')
        history=self.db.execute('SELECT * FROM completion_log').fetchall();users=self.db.execute('SELECT * FROM users').fetchall()
        qid,text=p.duplicate(2,'Guest bathroom',p.duplicate_snapshot(2),'copy-1',20)
        self.assertIsNotNone(qid)
        self.assertEqual(self.db.execute('SELECT name,frequency,points,notes,category,difficulty,assigned_to,completed,last_completed,reset_after FROM quests WHERE id=?',(qid,)).fetchone(),('Guest bathroom','weekly',10,'Use gloves','bathroom','hard',None,0,None,None))
        self.assertEqual(p.plan(qid),p.plan(2));self.assertEqual(self.ui.timing.policy(qid),'skip')
        for table in ('claims','week_signups','completion_log','chore_help','checklist_checks','occurrence_moves'):
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM '+table+' WHERE quest_id=?',(qid,)).fetchone(),(0,))
        self.assertEqual(self.db.execute('SELECT * FROM completion_log').fetchall(),history)
        self.assertEqual(self.db.execute('SELECT * FROM users').fetchall(),users)

    async def test_support_duplicate_idempotent_names_archives_and_stale_source(self):
        p=self.ui.planning;expected=p.duplicate_snapshot(2)
        qid,_=p.duplicate(2,'Copy bathroom',expected,'copy-once',10)
        self.assertEqual(p.duplicate(2,'Other name',expected,'copy-once',10)[0],qid)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(3,))
        self.db.execute("INSERT INTO archived_chores VALUES(?,'10','now')",(qid,));self.db.commit()
        for name in ('  COPY    bathroom  ','','x'*101):
            self.assertIsNone(p.duplicate(2,name,expected,'new-'+name,10)[0])
        p.save_plan(2,15,'Step',p.plan(2))
        self.assertIn('changed',p.duplicate(2,'Another',expected,'stale',10)[1])

    async def test_support_duplicate_transaction_rolls_back_all_tables(self):
        p=self.ui.planning;p.save_plan(2,5,'One',p.plan(2));self.ui.timing.set_policy(2,'skip')
        before={t:self.db.execute('SELECT * FROM '+t).fetchall() for t in ('quests','chore_plans','chore_checklist_revisions','chore_timing','missed_chore_policy','chore_copies')}
        self.db.execute("CREATE TRIGGER fail_copy BEFORE INSERT ON chore_copies BEGIN SELECT RAISE(ABORT,'fail'); END");self.db.commit()
        with self.assertRaises(Exception):p.duplicate(2,'Copy',p.duplicate_snapshot(2),'failure',10)
        for table,rows in before.items():self.assertEqual(self.db.execute('SELECT * FROM '+table).fetchall(),rows)

    async def test_support_duplicate_modal_review_cancel_permissions_and_repeat_confirm(self):
        p=self.ui.planning
        modal=p.DuplicateModal(20,2);modal.name._value='Guest bath'
        wrong=Interaction(10);await modal.on_submit(wrong);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(2,))
        i=Interaction(20);await modal.on_submit(i)
        review=i.response.payload['view'];self.assertEqual(review.embed.title,'Create this chore copy?')
        self.assertIn('Guest bath',review.embed.description)
        cancel=next(c for c in review.children if getattr(c,'label',None)=='Cancel');await cancel.callback(Interaction(20))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(2,))
        confirm=next(c for c in review.children if getattr(c,'label',None)=='Confirm');await confirm.callback(Interaction(10))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(2,))
        await asyncio.gather(confirm.callback(Interaction(20)),confirm.callback(Interaction(20)))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone(),(3,))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_copies').fetchone(),(1,))

    async def test_support_help_and_duplicate_entries_and_discord_limits(self):
        p=self.ui.planning;w=self.ui.workspace
        self.assertIn('Needs attention',[getattr(c,'label',None) for c in w.Dashboard(10).children])
        p.report_help(10,2,'Need help','x'*500,p.help_snapshot(2))
        card=w.Card(10,2);picker=next(c for c in card.children if isinstance(c,discord.ui.Select));self.assertIn('Duplicate chore',[o.label for o in picker.options])
        for view in (p.HelpStatus(10,2),p.HelpStatus(20,2),p.NeedsHelp(10),p.HelpHistory(10,2),card,w.Dashboard(301104023405199361)):
            self.assert_screen_limits(view);self.assertTrue(w.render(view).to_components())


    def calendar_navigation_rows(self):
        self.db.execute("UPDATE quests SET assigned_to='10' WHERE id=1")
        self.db.executemany("INSERT INTO quests(name,frequency,points,assigned_to) VALUES(?,'daily',5,'10')",[(f'Daily {i:02}',) for i in range(10)])
        self.db.commit()

    async def test_calendar_navigation_dashboard_defaults_to_today_at_click_time(self):
        w=self.ui.workspace;p=self.ui.planning
        with self.clock('2026-10-20T23:59:00'):
            dashboard=w.Dashboard(10)
        with self.clock('2026-10-21T00:01:00'):
            i=Interaction()
            await next(c for c in dashboard.children if getattr(c,'label',None)=='Calendar').callback(i)
            view=i.response.payload['view']
            self.assertIsInstance(view,p.Day)
            self.assertEqual(view.day,datetime(2026,10,21).date())
            self.assertEqual(view.page,0)
            self.assertFalse(view.mine)
            self.assertFalse(view.flexible)
            self.assert_screen_limits(view)
            self.assertTrue(w.render(view).to_components())

    async def test_calendar_navigation_day_week_month_keep_selected_date_and_scope(self):
        p=self.ui.planning;day=datetime(2026,10,21).date()
        for mode in ('week','month'):
            view=p.Day(10,day,mine=True)
            i=Interaction()
            await next(c for c in view.children if getattr(c,'label',None)==mode.title()).callback(i)
            result=i.response.payload['view']
            self.assertEqual(result.recovery_context['day'],day.isoformat())
            self.assertEqual(result.recovery_context['mode'],mode)
            self.assertTrue(result.recovery_context['mine'])
            self.assert_screen_limits(result)

    async def test_calendar_navigation_day_paging_counts_and_boundaries(self):
        p=self.ui.planning;self.calendar_navigation_rows();day=datetime(2026,10,20).date()
        first=p.Day(10,day,True,mode='month')
        self.assertIn('Page 1 of 3',first.embed.footer.text)
        self.assertIn('Chores 1–5 of 11',first.embed.footer.text)
        next_page=next(c for c in first.children if getattr(c,'label',None)=='Next page')
        i=Interaction();await next_page.callback(i);second=i.response.payload['view']
        self.assertEqual((second.day,second.page,second.mine,second.mode),(day,1,True,'month'))
        i=Interaction();await next(c for c in second.children if getattr(c,'label',None)=='Next page').callback(i)
        last=i.response.payload['view'];self.assertIn('Page 3 of 3',last.embed.footer.text)
        self.assertNotIn('Next page',[getattr(c,'label',None) for c in last.children])
        self.assertIn('Chores 11–11 of 11',last.embed.footer.text)
        i=Interaction();await next(c for c in last.children if getattr(c,'label',None)=='Previous page').callback(i)
        self.assertEqual(i.response.payload['view'].page,1)

    async def test_calendar_navigation_next_previous_today_preserve_scope_reset_page(self):
        p=self.ui.planning;self.calendar_navigation_rows();day=datetime(2026,10,31).date()
        view=p.Day(10,day,True,page=2,mode='month')
        i=Interaction();await next(c for c in view.children if getattr(c,'label',None)=='Next day').callback(i)
        tomorrow=i.response.payload['view'];self.assertEqual((tomorrow.day,tomorrow.page,tomorrow.mine,tomorrow.mode),(datetime(2026,11,1).date(),0,True,'month'))
        i=Interaction();await next(c for c in tomorrow.children if getattr(c,'label',None)=='Previous day').callback(i)
        self.assertEqual(i.response.payload['view'].day,day)
        with self.clock('2026-10-20T10:00:00'):
            i=Interaction();await next(c for c in tomorrow.children if getattr(c,'label',None)=='Today').callback(i)
            self.assertEqual(i.response.payload['view'].day,datetime(2026,10,20).date())

    async def test_calendar_navigation_month_and_chore_back_preserve_mode_page(self):
        p=self.ui.planning;day=datetime(2026,10,20).date();self.calendar_navigation_rows()
        month=p.Calendar(10,day=day,mode='month',mine=True)
        picker=next(c for c in month.children if isinstance(c,discord.ui.Select));picker._values=['20']
        # Month has two pickers: use the second range for the 20th.
        picker=[c for c in month.children if isinstance(c,discord.ui.Select)][1];picker._values=['20']
        i=Interaction();await picker.callback(i);self.assertEqual(i.response.payload['view'].mode,'month')
        with self.clock('2026-10-20T10:00:00'):
            view=p.Day(10,day,True,page=1,mode='month');picker=next(c for c in view.children if isinstance(c,discord.ui.Select));picker._values=[picker.options[0].value]
            i=Interaction();await picker.callback(i);card=i.response.payload['view']
            i=Interaction();await next(c for c in card.children if getattr(c,'label',None)=='Back').callback(i)
            restored=i.response.payload['view'];self.assertEqual((restored.page,restored.mine,restored.mode),(1,True,'month'))
            i=Interaction();await next(c for c in restored.children if getattr(c,'label',None)=='Back').callback(i)
            self.assertIn('My calendar',i.response.payload['view'].embed.title)
            self.assertTrue(next(c for c in i.response.payload['view'].children if getattr(c,'label',None)=='Month').style==discord.ButtonStyle.primary)

    async def test_calendar_navigation_page_buttons_below_count_and_empty_limits(self):
        p=self.ui.planning;w=self.ui.workspace;self.calendar_navigation_rows();day=datetime(2026,10,20).date()
        view=p.Day(10,day,page=1);wire=w.render(view)
        footer=next(i for i,c in enumerate(wire.children) if isinstance(c,discord.ui.TextDisplay) and 'Page 2 of 3' in c.content)
        paging=next(i for i,c in enumerate(wire.children) if isinstance(c,discord.ui.ActionRow) and any(getattr(b,'label',None)=='Next page' for b in c.children))
        separator=next(i for i,c in enumerate(wire.children) if isinstance(c,discord.ui.Separator))
        self.assertEqual(paging,footer+1);self.assertLess(paging,separator)
        empty=p.Day(20,day,mine=True);self.assertIn('Page 1 of 1',empty.embed.footer.text);self.assertIn('0 chores',empty.embed.footer.text)
        for screen in (view,empty,p.Day(10,day,flexible=True,mode='month')):
            self.assert_screen_limits(screen);self.assertTrue(w.render(screen).to_components())
            self.assertFalse(await screen.interaction_check(Interaction(99)))


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
        async def send(content=None,**kwargs):
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
        self.assertIsNone(options['view'].timeout)

    async def test_slash_chores_is_private_and_actions_stay_private(self):
        messages=[]
        async def send(content=None,**kwargs):
            messages.append((content,kwargs))
        ctx=SimpleNamespace(interaction=object(),guild=SimpleNamespace(id=1),channel=SimpleNamespace(id=2),author=SimpleNamespace(id=10),send=send)
        await self.app.bot.get_command('chores').callback(ctx)
        self.assertTrue(messages[0][1]['ephemeral'])
        event=Interaction()
        await next(c for c in messages[0][1]['view'].source.children if getattr(c,'label',None)=='Pick up chores').callback(event)
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
        before=[line for line in self.db.iterdump() if 'workspace_' not in line]
        await next(c for c in view.children if getattr(c,'label',None)=='Dashboard').callback(event)
        self.assertIsInstance(event.response.payload['view'],self.ui.workspace.Dashboard)
        self.assertEqual(event.response.payload['embed'].title,'🌱 Your chore workspace')
        self.assertEqual(before,[line for line in self.db.iterdump() if 'workspace_' not in line])

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
        before=[line for line in self.db.iterdump() if 'workspace_' not in line];w=self.ui.workspace;event=Interaction()
        await next(c for c in w.Dashboard(10,event.guild).children if c.label=='Points & standings').callback(event)
        panel=event.response.wire_payload['view'];self.assertIsInstance(panel,w.LayoutPanel)
        self.assertIn('20 points',panel.source.embed.description)
        self.assertIn('3 day(s)',panel.source.embed.description)
        self.assertTrue(await panel.interaction_check(event))
        other=Interaction(20);self.assertFalse(await panel.interaction_check(other))
        self.assertTrue(other.response.wire_payload[1]['ephemeral'])
        self.assertEqual(before,[line for line in self.db.iterdump() if 'workspace_' not in line])

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

    async def test_daily_am_pm_have_independent_weekly_owners_and_completions(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Empty dishwasher AM','daily-am','5','')
            self.ui.create_chore('Empty dishwasher PM','daily-pm','5','')
            am,pm=[r[0] for r in self.db.execute("SELECT id FROM quests WHERE name LIKE 'Empty dishwasher %' ORDER BY id")]
            self.assertIn('signed up',self.ui.signup(10,am,self.ui.week_key()))
            self.assertIn('signed up',self.ui.signup(20,pm,self.ui.week_key()))
            self.assertTrue(self.ui.ready(am));self.assertFalse(self.ui.ready(pm))
            await self.ui.PersonalView(10,'mine',selected=am).act(Interaction(10),'done')
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(pm,)).fetchone(),(0,))
        with self.clock('2026-10-20T13:00:00'):
            self.assertTrue(self.ui.ready(pm))
            await self.ui.PersonalView(20,'mine',selected=pm).act(Interaction(20),'done')
            self.assertEqual(self.db.execute('SELECT id,points FROM users ORDER BY id').fetchall(),[('10',5),('20',5)])
            self.assertEqual(self.ui.weekly_owner(am),'10');self.assertEqual(self.ui.weekly_owner(pm),'20')
        with self.clock('2026-10-21T08:00:00'):
            self.app.reset_due_quests()
            self.assertIn(am,[r[0] for r in self.ui.rows(10,'mine')]);self.assertNotIn(pm,[r[0] for r in self.ui.rows(20,'mine')])
        with self.clock('2026-10-21T12:00:00'):
            self.app.reset_due_quests()
            self.assertIn(pm,[r[0] for r in self.ui.rows(20,'mine')])

    async def test_daily_shift_split_is_idempotent_keeps_points_reservations_and_fill_chore(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Empty dishwasher','twice-daily','5','Put dishes away','Kitchen')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Empty dishwasher'").fetchone()[0]
            self.ui.signup(10,qid,self.ui.week_key());self.ui.signup(20,qid,self.ui.week_key(1))
            self.db.execute("INSERT INTO users(id,points) VALUES('10',55)");self.db.commit()
            fill=self.db.execute('SELECT * FROM quests WHERE id=1').fetchone()
            expected=self.ui.reassign_snapshot(qid)
            result=self.ui.workspace.split_daily_shifts(qid,expected);self.assertIn('Split into',result)
            pm=self.db.execute('SELECT pm_id FROM chore_shift_splits WHERE original_id=?',(qid,)).fetchone()[0]
            self.assertEqual(self.ui.weekly_owner(qid),'10');self.assertEqual(self.ui.weekly_owner(qid,1),'20')
            self.assertIsNone(self.ui.weekly_owner(pm));self.assertIsNone(self.ui.weekly_owner(pm,1))
            self.assertEqual(self.db.execute('SELECT frequency,name FROM quests WHERE id=?',(qid,)).fetchone(),('daily-am','Empty dishwasher · AM'))
            self.assertEqual(self.db.execute('SELECT frequency,points,notes,category,assigned_to FROM quests WHERE id=?',(pm,)).fetchone(),('daily-pm',5,'Put dishes away','Kitchen',None))
            self.assertEqual(self.db.execute('SELECT * FROM quests WHERE id=1').fetchone(),fill)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(55,))
            count=self.db.execute('SELECT COUNT(*) FROM quests').fetchone()[0]
            self.assertIn('Already split',self.ui.workspace.split_daily_shifts(qid,expected))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quests').fetchone()[0],count)

    async def test_split_retains_already_completed_pm_without_another_award(self):
        with self.clock('2026-10-20T13:00:00'):
            self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1");self.db.commit()
            await self.ui.PersonalView(10,selected=1).act(Interaction(),'claim')
            await self.ui.PersonalView(10,'mine',selected=1).act(Interaction(),'done')
            history=self.db.execute('SELECT * FROM completion_log').fetchall()
            self.ui.workspace.split_daily_shifts(1,self.ui.reassign_snapshot(1))
            pm=self.db.execute('SELECT pm_id FROM chore_shift_splits WHERE original_id=1').fetchone()[0]
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=?',(pm,)).fetchone(),(1,))
            self.assertEqual(self.db.execute('SELECT * FROM completion_log').fetchall(),history)
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(5,))
            self.assertFalse(self.ui.ready(1))

    async def test_split_moves_only_current_pm_single_claim_and_rolls_back_on_failure(self):
        with self.clock('2026-10-20T13:00:00'):
            self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1")
            self.db.execute("INSERT INTO claims VALUES(1,'10')");self.db.commit()
            self.ui.workspace.split_daily_shifts(1,self.ui.reassign_snapshot(1))
            pm=self.db.execute('SELECT pm_id FROM chore_shift_splits WHERE original_id=1').fetchone()[0]
            self.assertEqual(self.db.execute('SELECT quest_id,user_id FROM claims').fetchall(),[(pm,'10')])
            self.ui.create_chore('Split failure','twice-daily','5','')
            qid=self.db.execute("SELECT id FROM quests WHERE name='Split failure'").fetchone()[0]
            before=self.db.execute('SELECT * FROM quests').fetchall()
            self.db.execute("CREATE TRIGGER reject_split BEFORE INSERT ON chore_shift_splits BEGIN SELECT RAISE(ABORT,'split failed'); END;");self.db.commit()
            with self.assertRaises(Exception):self.ui.workspace.split_daily_shifts(qid,self.ui.reassign_snapshot(qid))
            self.assertEqual(self.db.execute('SELECT * FROM quests').fetchall(),before)

    async def test_daily_shift_skip_and_overdue_reset_behave_at_boundaries(self):
        with self.clock('2026-10-20T10:00:00'):
            self.ui.create_chore('Morning shift','daily-am','5','')
            am=self.db.execute("SELECT id FROM quests WHERE name='Morning shift'").fetchone()[0]
            self.ui.timing.set_policy(am,'skip')
            self.ui.create_chore('Evening shift','daily-pm','5','')
            pm=self.db.execute("SELECT id FROM quests WHERE name='Evening shift'").fetchone()[0]
        with self.clock('2026-10-20T12:00:00'):
            self.app.reset_due_quests();self.assertFalse(self.ui.ready(am));self.assertTrue(self.ui.ready(pm))
        with self.clock('2026-10-21T08:00:00'):
            self.app.reset_due_quests();self.assertTrue(self.ui.ready(am));self.assertTrue(self.ui.ready(pm))
            await self.ui.PersonalView(20,selected=pm).act(Interaction(20),'claim')
            await self.ui.PersonalView(20,'mine',selected=pm).act(Interaction(20),'done')
            self.assertIn('2026-10-21T12:00',self.db.execute('SELECT reset_after FROM quests WHERE id=?',(pm,)).fetchone()[0])

    async def test_shift_labels_picker_and_split_confirmation_are_clear(self):
        options=self.ui.AddChoreMenu(10).children[0].options
        self.assertIn('daily-am',[o.value for o in options]);self.assertIn('daily-pm',[o.value for o in options])
        self.assertIn('AM',self.ui.timing.label('daily-am'));self.assertIn('PM',self.ui.timing.label('daily-pm'))
        with self.clock('2026-10-20T10:00:00'):
            self.db.execute("UPDATE quests SET frequency='twice-daily' WHERE id=1");self.db.commit()
            view=self.ui.workspace.Card(10,1);picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
            picker._values=['split'];event=Interaction();await picker.callback(event)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM chore_shift_splits').fetchone(),(0,))
            self.assertIn('Existing weekly/ongoing ownership stays on AM',event.response.payload['embed'].description)
            self.assertTrue(await event.response.wire_payload['view'].interaction_check(event))
            self.assertFalse(await event.response.wire_payload['view'].interaction_check(Interaction(20)))


    async def test_help_button_is_persistent_private_and_changes_no_data(self):
        before = [line for line in self.db.iterdump() if 'workspace_' not in line]
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
        self.assertEqual([line for line in self.db.iterdump() if 'workspace_' not in line], before)

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


    def recovery_button(self, panel, label):
        return next(c for c in panel.walk_children() if isinstance(c,discord.ui.Button) and c.label==label)

    def recovery_list(self):
        for index in range(12):
            self.ui.create_chore(f'Task {index:02}','daily','5','Instructions','Kitchen')
        self.db.execute("UPDATE quests SET assigned_to='10' WHERE name LIKE 'Task %'")
        self.db.commit()
        return self.ui.workspace.Browse(10,'household',tab='all',page=1,query='Task',person_id=10,room='Kitchen',group='chore',date_filter='2026-10-20')

    async def test_recovery_expired_control_preserves_filters_page_and_no_action(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=self.recovery_list();panel=w.render(view)
            before=self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone()
            panel.stop();event=Interaction()
            await self.recovery_button(panel,'Next').callback(event)
            self.assertEqual(event.response.payload['view'].state,view.state)
            self.assertIn('expired',event.response.payload['content'])
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),before)

    async def test_recovery_restart_routes_from_durable_record_without_live_callbacks(self):
        with self.clock('2026-10-20T10:00:00'):
            import re,sqlite3
            from contextlib import closing
            w=self.ui.workspace;view=self.recovery_list();panel=w.render(view)
            old=self.recovery_button(panel,'Next');custom_id=old.custom_id
            with closing(sqlite3.connect(self.temp.name+'/sprig.db')) as other:
                self.assertIsNotNone(other.execute('SELECT bookmark FROM workspace_sessions WHERE token=?',(panel.recovery_token,)).fetchone())
            w.recovery.live.clear()
            event=Interaction();factory=w.recovery.RecoveryControl
            fresh=await factory.from_custom_id(event,discord.ui.Button(label='Next',custom_id=custom_id),factory.__discord_ui_compiled_template__.fullmatch(custom_id))
            await fresh.callback(event)
            self.assertEqual(event.response.payload['view'].state,view.state)
            self.assertIn('restarted',event.response.payload['content'])

    async def test_recovery_expired_done_only_refreshes_then_fresh_done_works(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'));button=self.recovery_button(panel,'Done')
            w.recovery.live[panel.recovery_token]['created']-=601
            event=Interaction();await button.callback(event)
            self.assertEqual(self.db.execute('SELECT completed FROM quests WHERE id=2').fetchone(),(0,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))
            fresh=event.response.wire_payload['view']
            await self.recovery_button(fresh,'Done').callback(Interaction())
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))

    async def test_recovery_stale_done_refreshes_without_overwriting_shared_change(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'))
            self.db.execute("UPDATE quests SET assigned_to='20' WHERE id=2");self.db.commit()
            event=Interaction();await self.recovery_button(panel,'Done').callback(event)
            self.assertIn('no action was taken',event.response.payload['content'])
            self.assertEqual(event.response.payload['view'].entries,[])
            self.assertEqual(self.db.execute('SELECT completed,assigned_to FROM quests WHERE id=2').fetchone(),(0,'20'))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_recovery_rejects_wrong_person_guild_and_lost_channel_access(self):
        w=self.ui.workspace;panel=w.render(w.Browse(10,'household',query='private search'))
        button=self.recovery_button(panel,'Refresh / Resume');w.recovery.live.clear()
        events=[Interaction(20),Interaction(),Interaction()]
        events[1].guild_id=2
        events[2].channel_id=99
        events[2].guild.get_channel=lambda cid:SimpleNamespace(permissions_for=lambda user:SimpleNamespace(view_channel=False,read_message_history=False))
        for event in events:
            await button.callback(event)
            args,wire=event.response.wire_payload
            self.assertTrue(wire['ephemeral']);self.assertNotIn('private search',args[0])
            self.assertNotIn('view',wire)

    async def test_recovery_live_and_dynamic_dispatch_do_not_double_complete(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'));button=self.recovery_button(panel,'Done')
            event=Interaction();event.id=123456789
            factory=w.recovery.RecoveryControl
            dynamic=await factory.from_custom_id(event,discord.ui.Button(label='Done',custom_id=button.custom_id),factory.__discord_ui_compiled_template__.fullmatch(button.custom_id))
            command=self.app.bot.get_command('done')
            with patch.object(command,'_callback',new=AsyncMock(wraps=command.callback)) as complete:
                await asyncio.gather(button.callback(event),dynamic.callback(event))
                complete.assert_awaited_once()
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))

    async def test_recovery_select_uses_current_interaction_values(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=w.Browse(10,'household',tab='all');panel=w.render(view)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select))
            event=Interaction();event.data={'component_type':3,'values':['1']}
            await picker.callback(event)
            self.assertEqual(event.response.payload['view'].qid,1)

    async def test_recovery_nearest_page_after_other_person_archives_items(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=self.recovery_list();view=w.Browse(10,**dict(view.state,page=2));panel=w.render(view)
            self.db.execute("DELETE FROM quests WHERE name LIKE 'Task %' AND name!='Task 00'");self.db.commit()
            event=Interaction();await self.recovery_button(panel,'Refresh / Resume').callback(event)
            actual=event.response.payload['view']
            self.assertEqual(actual.state['page'],0);self.assertEqual(actual.state['query'],'Task')
            self.assertIn('nearest available page',event.response.payload['content'])

    async def test_recovery_card_back_preserves_parent_list_after_restart(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=self.recovery_list();qid=view.entries[5][0]
            panel=w.render(w.Card(10,qid,lambda:w.Browse(10,**view.state),offset=1))
            w.recovery.live.clear();event=Interaction();await self.recovery_button(panel,'Refresh / Resume').callback(event)
            self.assertEqual(event.response.payload['view'].qid,qid)
            self.assertEqual(event.response.payload['view'].recovery_context['offset'],1)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Back').callback(event)
            self.assertEqual(event.response.payload['view'].state,view.state)

    async def test_recovery_calendar_day_preserves_date_scope_mode_and_page(self):
        with self.clock('2026-10-20T10:00:00'):
            from datetime import date
            w=self.ui.workspace;self.recovery_list();day=date(2026,10,20)
            panel=w.render(self.ui.planning.Day(10,day,True,page=1,mode='month'))
            w.recovery.live.clear();event=Interaction();await self.recovery_button(panel,'Next day').callback(event)
            result=event.response.payload['view']
            self.assertEqual((result.day,result.page,result.mine,result.mode),(day,1,True,'month'))
            self.assertIn('Nothing was repeated',event.response.payload['content'])

    async def test_recovery_expired_confirmation_returns_to_card_without_replaying(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;save=AsyncMock();panel=w.render(w.Confirm(10,'Drop?','Confirm ownership change',save,lambda:w.Card(10,2)))
            panel.stop();event=Interaction();await self.recovery_button(panel,'Confirm').callback(event)
            save.assert_not_awaited();self.assertIsInstance(event.response.payload['view'],w.Card)
            self.assertEqual(event.response.payload['view'].qid,2)

    async def test_recovery_expired_points_reset_returns_to_scores_and_preserves_history(self):
        w=self.ui.workspace;owner=301104023405199361
        self.db.execute("INSERT INTO users(id,points,streak) VALUES('10',30,4)");self.db.commit()
        panel=w.render(w.ResetPoints(owner,target='10',confirm=True));panel.stop();event=Interaction(owner)
        await self.recovery_button(panel,'Confirm reset').callback(event)
        self.assertIsInstance(event.response.payload['view'],w.Points)
        self.assertEqual(self.db.execute("SELECT points,streak FROM users WHERE id='10'").fetchone(),(30,4))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM points_reset_batches').fetchone(),(0,))

    async def test_recovery_dashboard_continue_survives_reopen_and_is_per_person(self):
        w=self.ui.workspace;view=w.Browse(10,'household',tab='next',query='bath',group='person');w.render(view)
        self.assertIsNone(w.recovery.latest(20))
        w.recovery.live.clear();dashboard=w.render(w.Dashboard(10));event=Interaction()
        await self.recovery_button(dashboard,'Continue where I left off').callback(event)
        self.assertEqual(event.response.payload['view'].state,view.state)
        self.assertEqual(w.recovery.latest(10)['state'],view.state)
        self.assertNotIn('Continue where I left off',[getattr(c,'label',None) for c in w.Dashboard(20).children])

    async def test_recovery_unknown_token_fails_privately_without_mutation(self):
        w=self.ui.workspace;event=Interaction();before=self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone()
        await w.recovery.route(event,'0'*32,'0')
        self.assertTrue(event.response.wire_payload[1]['ephemeral'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),before)

    async def test_recovery_saved_view_not_supported_falls_back_safely(self):
        w=self.ui.workspace;event=Interaction()
        await w.recovery.open_saved(event,{'screen':'browse','state':{'removed_option':'old'}})
        self.assertIsInstance(event.response.payload['view'],w.Dashboard)
        self.assertIn('no action was taken',event.response.payload['content'])

    async def test_recovery_rerendered_source_and_explicit_refresh_still_work(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;source=w.Browse(10,'mine');w.render(source);panel=w.render(source)
            event=Interaction();await self.recovery_button(panel,'Done').callback(event)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))


    def recovery_message(self,panel):
        return discord.Message(state=self.app.bot._connection,channel=SimpleNamespace(id=2,guild=None),data={
            'id':'123456789012345678','channel_id':'2','type':0,'content':'',
            'author':{'id':'99','username':'ChoreSprite','discriminator':'0','avatar':None,'bot':True},
            'attachments':[],'embeds':[],'flags':(1<<15)|64,'components':panel.to_components()})

    async def test_recovery_real_view_store_dispatch_handles_dynamic_and_static_once(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;panel=w.render(w.Browse(10,'mine'));button=self.recovery_button(panel,'Done')
            message=self.recovery_message(panel);self.app.bot._connection._view_store.add_view(panel,message_id=message.id)
            event=Interaction();event.id=987654321;event.message=message
            event.data={'component_type':2,'custom_id':button.custom_id};event._state=self.app.bot._connection
            store=self.app.bot._connection._view_store
            store.dispatch_view(2,button.custom_id,event)
            await asyncio.gather(*list(store._ViewStore__tasks))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(1,))
            self.assertEqual(self.db.execute("SELECT points FROM users WHERE id='10'").fetchone(),(10,))
            self.assertIsNotNone(event.response.wire_payload)

    async def test_recovery_real_view_store_recovers_without_registered_old_view(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=self.recovery_list();panel=w.render(view)
            button=self.recovery_button(panel,'Next');message=self.recovery_message(panel)
            # Match a new bot process: persistent factory exists, source view/callbacks do not.
            w.recovery.live.clear();event=Interaction();event.id=987654322
            event.message=message;event.data={'component_type':2,'custom_id':button.custom_id};event._state=self.app.bot._connection
            store=self.app.bot._connection._view_store
            store.dispatch_view(2,button.custom_id,event)
            await asyncio.gather(*list(store._ViewStore__tasks))
            self.assertIsNotNone(event.response.wire_payload)
            self.assertEqual(event.response.payload['view'].state,view.state)
            self.assertIn('restarted',event.response.payload['content'])


    async def test_recovery_public_launcher_destinations_open_private_recoverable_views(self):
        for label in ('Help','Who’s home?','Manage chores'):
            event=Interaction();launcher=self.ui.Launcher()
            await next(c for c in launcher.children if getattr(c,'label',None)==label).callback(event)
            args,wire=event.response.wire_payload
            self.assertTrue(wire['ephemeral'])
            self.assertIsInstance(wire['view'],self.ui.workspace.LayoutPanel)
            self.assertIsNotNone(self.recovery_button(wire['view'],'Refresh / Resume'))


    async def test_recovery_checklist_restores_its_card_and_original_filtered_page(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=self.recovery_list();qid=view.entries[5][0];p=self.ui.planning
            p.save_plan(qid,'5','One step',p.plan(qid))
            back=lambda:w.Card(10,qid,lambda:w.Browse(10,**view.state))
            panel=w.render(p.Checklist(10,qid,back=back));w.recovery.live.clear()
            event=Interaction();await self.recovery_button(panel,'Refresh / Resume').callback(event)
            self.assertIsInstance(event.response.payload['view'],p.Checklist)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Open chore').callback(event)
            self.assertEqual(event.response.payload['view'].qid,qid)
            await next(c for c in event.response.payload['view'].children if getattr(c,'label',None)=='Back').callback(event)
            self.assertEqual(event.response.payload['view'].state,view.state)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))

    async def test_recovery_real_view_store_select_opens_selected_chore_privately(self):
        with self.clock('2026-10-20T10:00:00'):
            w=self.ui.workspace;view=w.Browse(10,'household',tab='all');panel=w.render(view)
            picker=next(c for c in view.children if isinstance(c,discord.ui.Select));message=self.recovery_message(panel)
            store=self.app.bot._connection._view_store;store.add_view(panel,message_id=message.id)
            event=Interaction();event.id=987654323;event.message=message
            event.data={'component_type':3,'custom_id':picker.custom_id,'values':['1']};event._state=self.app.bot._connection
            store.dispatch_view(3,picker.custom_id,event)
            await asyncio.gather(*list(store._ViewStore__tasks))
            self.assertIsNotNone(event.response.wire_payload)
            self.assertEqual(event.response.payload['view'].qid,1)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM completion_log').fetchone(),(0,))


if __name__ == "__main__":
    unittest.main()
