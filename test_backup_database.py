"""Linux integration checks for the server's standalone daily backup tool."""
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo
import backup_database


@unittest.skipUnless(os.name == 'posix', 'Server backup locking requires Linux')
class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'live.db'
        self.dest = self.root / 'daily'
        with closing(sqlite3.connect(self.source)) as db:
            db.executescript('CREATE TABLE quests(id INTEGER PRIMARY KEY,name TEXT);CREATE TABLE users(id TEXT,points INTEGER);INSERT INTO quests VALUES(1,"Dishes");INSERT INTO users VALUES("10",25);')
            db.commit()
        self.now = datetime(2026,10,20,4,tzinfo=ZoneInfo('America/New_York'))
    def tearDown(self):self.temp.cleanup()
    def test_readable_snapshot_and_manifest_preserve_original(self):
        before=self.source.read_bytes()
        result=backup_database.backup_daily(self.source,self.dest,self.now)
        with closing(sqlite3.connect(result)) as restored:
            self.assertEqual(restored.execute('SELECT points FROM users').fetchone(),(25,))
            self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone(),('ok',))
        manifest=json.loads(result.with_name('manifest.json').read_text())
        self.assertEqual(manifest['rows'],{'quests':1,'users':1})
        self.assertEqual(manifest['integrity_check'],'ok')
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(result.stat().st_mode & 0o777,0o600)
    def test_once_per_day_new_day_gets_another_snapshot(self):
        result=backup_database.backup_daily(self.source,self.dest,self.now)
        before=result.read_bytes()
        with closing(sqlite3.connect(self.source)) as db:db.execute('UPDATE users SET points=30');db.commit()
        self.assertIsNone(backup_database.backup_daily(self.source,self.dest,self.now))
        self.assertEqual(result.read_bytes(),before)
        later=self.now.replace(day=21)
        result2=backup_database.backup_daily(self.source,self.dest,later)
        with closing(sqlite3.connect(result2)) as db:self.assertEqual(db.execute('SELECT points FROM users').fetchone(),(30,))
        self.assertTrue(result.exists())
    def test_wal_commits_included_without_stopping_writer(self):
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('UPDATE users SET points=45');writer.commit()
            result=backup_database.backup_daily(self.source,self.dest,self.now)
            with closing(sqlite3.connect(result)) as db:
                self.assertEqual(db.execute('SELECT points FROM users').fetchone(),(45,))
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone(),('delete',))
    def test_before_time_skips_and_eastern_dates_follow_dst(self):
        self.assertIsNone(backup_database.backup_daily(self.source,self.dest,self.now.replace(hour=3,minute=14)))
        self.assertFalse(self.dest.exists())
        summer=datetime(2026,10,21,7,15,tzinfo=ZoneInfo('UTC'))
        winter=datetime(2026,11,2,8,15,tzinfo=ZoneInfo('UTC'))
        self.assertEqual(backup_database.backup_daily(self.source,self.dest,summer).parent.name,'2026-10-21')
        self.assertEqual(backup_database.backup_daily(self.source,self.dest,winter).parent.name,'2026-11-02')
    def test_missing_or_corrupt_source_never_publishes_success(self):
        with self.assertRaises(FileNotFoundError):backup_database.backup_daily(self.root/'missing.db',self.dest,self.now)
        bad=self.root/'bad.db';bad.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):backup_database.backup_daily(bad,self.dest,self.now)
        self.assertFalse((self.dest/'2026-10-20'/'sprig.db').exists())
        self.assertFalse((self.dest/'2026-10-20'/'manifest.json').exists())
    def test_existing_backup_is_not_overwritten_and_missing_manifest_recovers(self):
        result=backup_database.backup_daily(self.source,self.dest,self.now)
        result.with_name('manifest.json').unlink()
        self.assertIsNone(backup_database.backup_daily(self.source,self.dest,self.now))
        self.assertTrue(result.with_name('manifest.json').exists())
        with closing(sqlite3.connect(result)) as db:db.execute('UPDATE users SET points=99');db.commit()
        with self.assertRaises(RuntimeError):backup_database.backup_daily(self.source,self.dest,self.now)
        with closing(sqlite3.connect(result)) as db:self.assertEqual(db.execute('SELECT points FROM users').fetchone(),(99,))
    def test_lock_prevents_overlapping_jobs(self):
        import fcntl
        self.dest.mkdir()
        with (self.dest/'.backup.lock').open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertIsNone(backup_database.backup_daily(self.source,self.dest,self.now))
        self.assertFalse((self.dest/'2026-10-20').exists())


if __name__=='__main__':unittest.main()
