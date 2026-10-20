"""Offline backup/restore and alert checks. All Discord and SSH calls are mocked."""
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import backup_monitor as monitor
import laptop_backup as laptop


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path = self.root / 'fixture.db'
        with closing(sqlite3.connect(path)) as db:
            db.executescript('CREATE TABLE quests(id INTEGER);CREATE TABLE users(id TEXT,points INTEGER);INSERT INTO quests VALUES(1);INSERT INTO users VALUES("owner",5);')
            db.commit()
        self.data = path.read_bytes()
        self.manifest = dict(date='2026-10-20', bytes=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(), rows={'quests': 1, 'users': 1}, integrity_check='ok')
        self.now = datetime(2026, 10, 20, 16, tzinfo=ZoneInfo('America/New_York'))
        self.encrypt = lambda b: b'ENC' + b
        self.decrypt = lambda b: b[3:]

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, data=None, manifest=None):
        return laptop.publish(data or self.data, manifest or self.manifest,
            self.root / 'copies', self.encrypt, self.decrypt)

    def test_encrypted_publish_independent_restore_and_idempotent(self):
        result = self.publish()
        self.assertNotEqual(result.read_bytes(), self.data)
        laptop.verify(self.decrypt(result.read_bytes()), self.manifest, self.root)
        stamp = result.stat().st_mtime_ns
        self.assertEqual(self.publish(), result)
        self.assertEqual(result.stat().st_mtime_ns, stamp)
        self.assertEqual(len(list((self.root / 'copies').glob('*/sprig.db.dpapi'))), 1)

    def test_bad_hash_or_row_counts_never_publishes(self):
        with self.assertRaises(ValueError):
            self.publish(b'bad download')
        wrong = dict(self.manifest, rows={'quests': 99, 'users': 1})
        with self.assertRaises(ValueError):
            self.publish(manifest=wrong)
        self.assertFalse(list((self.root / 'copies').glob('*/sprig.db.dpapi')))

    def test_existing_corrupt_copy_preserved_not_overwritten(self):
        result = self.publish()
        result.write_bytes(b'broken')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(result.read_bytes(), b'broken')

    def test_wrong_account_decryption_does_not_publish(self):
        with self.assertRaises(ValueError):
            laptop.publish(self.data, self.manifest, self.root / 'copies', self.encrypt, lambda b: b'wrong')
        self.assertFalse(list((self.root / 'copies').glob('*/sprig.db.dpapi')))

    def test_manifest_paths_and_hash_rejected_before_transfer(self):
        for change in ({'date': '../../elsewhere'}, {'date': '2026-99-50'},
                {'sha256': 'not a checksum'}, {'bytes': -1}, {'rows': {'secret_table': 1}}):
            with self.assertRaises(ValueError):
                laptop.validate_manifest(dict(self.manifest, **change))

    def test_healthy_has_no_alert_and_missed_snapshot_is_detected(self):
        receipt = {'status': 'verified', 'at': self.now.isoformat(), 'date': '2026-10-20'}
        self.assertEqual(monitor.problems([self.manifest], receipt, self.now.isoformat(), self.now), [])
        self.assertTrue(monitor.problems([], receipt, self.now.isoformat(), self.now))
        tomorrow = self.now + timedelta(days=1)
        self.assertIn('The expected daily server snapshot is missing.',
            monitor.problems([self.manifest], receipt, self.now.isoformat(), tomorrow))

    def test_laptop_stale_after_48_hours_and_bootstrap_grace(self):
        receipt = {'status': 'verified', 'at': self.now.isoformat(), 'date': '2026-10-20'}
        later = self.now + timedelta(hours=49)
        items = [dict(self.manifest, date=later.date().isoformat())]
        self.assertTrue(any('48 hours' in p for p in monitor.problems(items, receipt, self.now.isoformat(), later)))
        self.assertEqual(monitor.problems([self.manifest], {}, self.now.isoformat(), self.now), [])
        self.assertTrue(any('48 hours' in p for p in monitor.problems(items, {}, self.now.isoformat(), later)))

    def test_backup_retry_grace_and_laptop_explicit_failure(self):
        before = self.now.replace(day=21, hour=4, minute=14)
        receipt = {'status': 'verified', 'at': self.now.isoformat(), 'date': '2026-10-20'}
        self.assertEqual(monitor.problems([self.manifest], receipt, self.now.isoformat(), before), [])
        failed = monitor.problems([self.manifest], dict(receipt, status='failed'), self.now.isoformat(), self.now)
        self.assertTrue(any('failed backup download' in p for p in failed))

    def test_failure_once_recovery_once_no_healthy_spam(self):
        path = self.root / 'health.json'
        send = Mock(return_value='message')
        monitor.notify_transition(path, [], self.now, send)
        send.assert_not_called()
        monitor.notify_transition(path, ['Backup failed'], self.now, send)
        monitor.notify_transition(path, ['Backup failed'], self.now, send)
        self.assertEqual(send.call_count, 1)
        monitor.notify_transition(path, [], self.now, send)
        monitor.notify_transition(path, [], self.now, send)
        self.assertEqual(send.call_count, 2)
        self.assertIn('recovered', send.call_args.args[0])

    def test_uncertain_notification_is_not_repeated(self):
        path = self.root / 'health.json'
        send = Mock(side_effect=TimeoutError)
        first = monitor.notify_transition(path, ['Backup failed'], self.now, send)
        self.assertEqual(first['delivery'], 'failed_uncertain')
        monitor.notify_transition(path, ['Backup failed'], self.now, send)
        send.assert_called_once()

    def test_receipt_not_sent_until_copy_verifies_and_failure_is_reported(self):
        remote = Mock(return_value=json.dumps([self.manifest]).encode())
        with patch.object(laptop, 'lock'), patch.object(laptop, 'remote', remote), patch.object(laptop, 'command', side_effect=RuntimeError('network unavailable')):
            with self.assertRaises(RuntimeError):
                laptop.sync(self.root / 'laptop')
        self.assertEqual(remote.call_args.args, ('receipt', {'status': 'failed'}))
        self.assertEqual(json.loads((self.root / 'laptop/status.json').read_text())['status'], 'failed')

    def test_sync_verifies_before_receipt_and_repeat_uses_encrypted_copy(self):
        calls = []
        def remote(action, payload=None):
            calls.append((action, payload))
            if action == 'index':
                return json.dumps([self.manifest]).encode()
            self.assertTrue((self.root / 'laptop/backups/2026-10-20/sprig.db.dpapi').exists())
            self.assertEqual(payload['status'], 'verified')
            return b'ok'
        def download(args):
            Path(args[-1]).write_bytes(self.data)
            return b''
        def crypt(data, decrypt=False):
            return self.decrypt(data) if decrypt else self.encrypt(data)
        with patch.object(laptop, 'lock'), patch.object(laptop, 'remote', side_effect=remote), patch.object(laptop, 'command', side_effect=download) as transfer, patch.object(laptop, 'dpapi', side_effect=crypt):
            # publish's injected default is bound at definition; replace it here as well.
            original = laptop.publish
            with patch.object(laptop, 'publish', side_effect=lambda data,m,root: original(data,m,root,self.encrypt,self.decrypt)):
                laptop.sync(self.root / 'laptop')
                laptop.sync(self.root / 'laptop')
            transfer.assert_called_once()
        self.assertEqual(len([c for c in calls if c[0] == 'receipt']), 2)

    @unittest.skipUnless(os.name == 'nt', 'Real CurrentUser encryption requires Windows')
    def test_real_windows_encryption_restore_and_no_overwrite(self):
        result = laptop.publish(self.data, self.manifest, self.root / 'windows')
        self.assertNotEqual(result.read_bytes(), self.data)
        output = self.root / 'restored.db'
        laptop.restore(result, output)
        self.assertEqual(output.read_bytes(), self.data)
        with self.assertRaises(FileExistsError):
            laptop.restore(result, output)

    @unittest.skipUnless(os.name == 'posix', 'Server locking and daily snapshots require Linux')
    def test_server_index_receipt_and_health_without_real_notifications(self):
        import backup_database
        root, state = self.root / 'daily', self.root / 'monitor'
        source = self.root / 'fixture.db'
        backup_database.backup_daily(source, root, self.now)
        items = monitor.index(root, self.now)
        self.assertEqual(len(items), 1)
        payload = dict(status='verified', date=items[0]['date'], sha256=items[0]['sha256'])
        monitor.receipt(payload, root, state, self.now)
        send = Mock(return_value='mock-message')
        self.assertEqual(monitor.check(root, source, state, self.now, send), 0)
        send.assert_not_called()
        with self.assertRaises(ValueError):
            monitor.receipt(dict(payload, sha256='0'*64), root, state, self.now)
        (root / '2026-10-20/sprig.db').write_bytes(b'corrupt')
        with self.assertRaises(sqlite3.DatabaseError):
            monitor.index(root, self.now)
        self.assertEqual(monitor.check(root, source, state, self.now, send), 1)
        send.assert_called_once()


if __name__ == '__main__':
    unittest.main()
