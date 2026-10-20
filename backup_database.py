"""Daily, verified SQLite snapshots; independent of the Discord bot process."""
import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from zoneinfo import ZoneInfo


def backup_daily(source, root, now=None):
    import fcntl
    source, root = Path(source).resolve(), Path(root).resolve()
    local = (now or datetime.now(ZoneInfo('America/New_York'))).astimezone(ZoneInfo('America/New_York'))
    if local.hour * 60 + local.minute < 195:
        return None
    if not source.is_file():
        raise FileNotFoundError(f'Database not found: {source}')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / '.backup.lock').open('a') as guard:
        try:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        folder = root / local.date().isoformat()
        folder.mkdir(mode=0o700, exist_ok=True)
        final = folder / 'sprig.db'
        manifest = folder / 'manifest.json'
        if final.exists():
            # A prior interrupted run may have published the DB but not its manifest.
            details = inspect_backup(final, source, local)
            if not manifest.exists():
                write_manifest(manifest, details)
            elif json.loads(manifest.read_text(encoding='utf-8'))['sha256'] != details['sha256']:
                raise RuntimeError('Existing backup no longer matches its manifest; files preserved.')
            return None
        partial = folder / ('.sprig-' + uuid.uuid4().hex + '.partial')
        descriptor = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as original:
            with closing(sqlite3.connect(partial)) as target:
                original.backup(target, pages=128, sleep=0.1)
                target.execute('PRAGMA journal_mode=DELETE')
                target.commit()
        details = inspect_backup(partial, source, local)
        with partial.open('rb') as handle:
            os.fsync(handle.fileno())
        # Atomic no-overwrite publication. Only this run's temporary link is removed.
        os.link(partial, final)
        partial.unlink()
        write_manifest(manifest, details)
        print(f'{local.isoformat()} Backup verified: {final}', flush=True)
        return final


def inspect_backup(path, source, local):
    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed; existing files preserved.')
        counts = {name: db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                  for name in ('quests', 'users')}
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return dict(date=local.date().isoformat(), checked_at=local.isoformat(),
                source=str(source), integrity_check='ok', sha256=digest.hexdigest(),
                bytes=Path(path).stat().st_size, rows=counts)


def write_manifest(path, details):
    path = Path(path)
    temporary = path.with_name('.manifest-' + uuid.uuid4().hex + '.partial')
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(details, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.link(temporary, path)
    temporary.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='/home/discordbot/chore_bot/sprig.db')
    parser.add_argument('--root', default='/home/discordbot/sprig-backups/daily')
    args = parser.parse_args()
    os.umask(0o077)
    backup_daily(args.source, args.root)
