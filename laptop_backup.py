"""Pull verified Sprig snapshots over SSH and encrypt with Windows CurrentUser DPAPI."""
import argparse
from contextlib import closing, contextmanager
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

HOST = 'discordbot@24.144.97.41'
REMOTE = '/home/discordbot/sprig-backups/daily'
MONITOR = '/home/discordbot/sprig-backup-tools/backup_monitor.py'
BASE = Path.home() / 'SprigBackups'
SSH = r'C:\Windows\System32\OpenSSH\ssh.exe'
SCP = r'C:\Windows\System32\OpenSSH\scp.exe'
OPTIONS = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15']


def dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Windows account encryption requires Windows')
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.restype = wintypes.BOOL
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    # CRYPTPROTECT_UI_FORBIDDEN: scheduled tasks must never prompt for secrets.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        free = ctypes.WinDLL('kernel32', use_last_error=True).LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(target.pbData, ctypes.c_void_p))


def validate_manifest(m):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', m.get('date', '')):
        raise ValueError('Invalid snapshot date')
    datetime.strptime(m['date'], '%Y-%m-%d')
    if not re.fullmatch(r'[a-f0-9]{64}', m.get('sha256', '')) or m.get('integrity_check') != 'ok':
        raise ValueError('Invalid snapshot manifest')
    if not isinstance(m.get('bytes'), int) or not 0 < m['bytes'] <= 1024**3:
        raise ValueError('Invalid snapshot size')
    if not isinstance(m.get('rows'), dict) or set(m['rows']) != {'quests', 'users'}:
        raise ValueError('Invalid row counts')
    return m


def verify(data, manifest, staging):
    if len(data) != manifest['bytes'] or hashlib.sha256(data).hexdigest() != manifest['sha256']:
        raise ValueError('Downloaded snapshot checksum mismatch')
    with tempfile.TemporaryDirectory(dir=staging, prefix='verify-') as temp:
        path = Path(temp) / 'restore.db'
        path.write_bytes(data)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Restored snapshot integrity check failed')
            counts = {name: db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                for name in ('quests', 'users')}
            if counts != manifest['rows']:
                raise ValueError('Restored snapshot counts mismatch')


def publish(data, manifest, root, encrypt=dpapi, decrypt=None):
    validate_manifest(manifest)
    decrypt = decrypt or (lambda b: dpapi(b, True))
    folder = root / manifest['date']
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / 'sprig.db.dpapi'
    meta = folder / 'manifest.json'
    verify(data, manifest, root)
    if final.exists():
        # Do not overwrite a corrupt, changed, or different-account copy.
        verify(decrypt(final.read_bytes()), manifest, root)
    else:
        encrypted = encrypt(data)
        verify(decrypt(encrypted), manifest, root)
        with tempfile.NamedTemporaryFile(dir=folder, prefix='encrypted-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, final)
        finally:
            temporary.unlink()
    if meta.exists():
        saved = json.loads(meta.read_text(encoding='utf-8'))
        if saved != manifest:
            raise ValueError('Existing local manifest differs; copy preserved')
    else:
        with meta.open('x', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2)
    return final


def command(args, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('SSH transfer failed; check connectivity and ssh-agent')
    return result.stdout


def remote(action, payload=None):
    return command([SSH, *OPTIONS, HOST, '/usr/bin/python3 ' + MONITOR + ' ' + action],
        json.dumps(payload).encode() if payload is not None else None)


@contextmanager
def lock(base):
    import msvcrt
    with (base / '.laptop-backup.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def sync(base=BASE):
    root = base / 'backups'
    root.mkdir(parents=True, exist_ok=True)
    with lock(base):
        try:
            items = json.loads(remote('index'))
            if not items or len(items) > 30:
                raise ValueError('No verified server snapshots available')
            for m in items:
                validate_manifest(m)
            for m in sorted(items, key=lambda m: m['date']):
                final = root / m['date'] / 'sprig.db.dpapi'
                if final.exists():
                    data = dpapi(final.read_bytes(), True)
                else:
                    with tempfile.TemporaryDirectory(dir=base, prefix='download-') as temp:
                        path = Path(temp) / 'sprig.db'
                        command([SCP, *OPTIONS, HOST + ':' + REMOTE + '/' + m['date'] + '/sprig.db', str(path)])
                        data = path.read_bytes()
                publish(data, m, root)
            newest = max(items, key=lambda m: m['date'])
            remote('receipt', {'status': 'verified', 'date': newest['date'], 'sha256': newest['sha256']})
            status = {'status': 'verified', 'at': datetime.now(timezone.utc).isoformat(),
                'date': newest['date'], 'snapshots_checked': len(items)}
        except Exception as exc:
            # No bot token resides on the laptop. Report through the existing SSH identity.
            try:
                remote('receipt', {'status': 'failed'})
            except Exception:
                pass
            status = {'status': 'failed', 'at': datetime.now(timezone.utc).isoformat(),
                'error': type(exc).__name__, 'message': str(exc)}
            (base / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
            raise
        (base / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
        print(json.dumps(status))


def restore(snapshot, output):
    snapshot, output = Path(snapshot), Path(output)
    m = validate_manifest(json.loads(snapshot.with_name('manifest.json').read_text(encoding='utf-8')))
    data = dpapi(snapshot.read_bytes(), True)
    verify(data, m, snapshot.parent)
    # Never overwrite a live DB or any existing file.
    with output.open('xb') as handle:
        handle.write(data)
    print('Verified restore written: ' + str(output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.restore:
            if not args.output:
                parser.error('--restore requires --output')
            restore(args.restore, args.output)
        else:
            sync()
    except Exception as exc:
        print('Laptop backup failed: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
