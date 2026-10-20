"""Independent server backup check, laptop receipts, and owner-only Discord alerts."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shlex
import sys
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from backup_database import backup_daily, inspect_backup

EASTERN = ZoneInfo('America/New_York')
OWNER = '301104023405199361'
HOME = Path.home()
ROOT = HOME / 'sprig-backups/daily'
STATE = HOME / 'sprig-backups/monitor'
SOURCE = HOME / 'chore_bot/sprig.db'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    with temp.open('x', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


@contextmanager
def lock(state):
    import fcntl
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / '.monitor.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def index(root=ROOT, now=None):
    now = now or datetime.now(EASTERN)
    items = []
    for folder in sorted(root.iterdir(), reverse=True) if root.exists() else []:
        if not folder.is_dir() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', folder.name):
            continue
        datetime.strptime(folder.name, '%Y-%m-%d')
        manifest = read_json(folder / 'manifest.json', {})
        actual = inspect_backup(folder / 'sprig.db', SOURCE, now)
        if (manifest.get('date') != folder.name or
                manifest.get('sha256') != actual['sha256'] or
                manifest.get('rows') != actual['rows'] or
                manifest.get('bytes') != actual['bytes']):
            raise ValueError('Snapshot manifest mismatch')
        items.append(manifest)
        if len(items) == 30:
            break
    return items


def receipt(payload, root=ROOT, state=STATE, now=None):
    now = now or datetime.now(EASTERN)
    if payload.get('status') == 'failed':
        value = {'status': 'failed', 'at': now.isoformat(), 'reason': 'Laptop copy failed'}
    else:
        items = index(root, now)
        match = next((m for m in items if m['date'] == payload.get('date') and m['sha256'] == payload.get('sha256')), None)
        if not match or payload.get('status') != 'verified':
            raise ValueError('Receipt does not match a verified server snapshot')
        value = {'status': 'verified', 'at': now.isoformat(), 'date': match['date'], 'sha256': match['sha256']}
    with lock(state):
        write_json(state / 'laptop.json', value)
    return value


def problems(items, laptop, started, now, backup_error=False):
    result = []
    if backup_error:
        result.append('Server backup failed verification or creation.')
    # Allow the 03:15 job one hour; before 04:15 yesterday is still acceptable.
    expected = (now - timedelta(days=int(now.hour * 60 + now.minute < 255))).date().isoformat()
    if not items or items[0]['date'] < expected:
        result.append('The expected daily server snapshot is missing.')
    if laptop.get('status') == 'failed':
        result.append('The laptop reported a failed backup download or verification.')
    last = datetime.fromisoformat(laptop.get('at', started))
    if now - last > timedelta(hours=48) or (laptop.get('date') and
            (now.date() - datetime.strptime(laptop['date'], '%Y-%m-%d').date()).days > 2):
        result.append('No current laptop backup has been verified within 48 hours.')
    return result


def token_from_env(path):
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].strip()
        if line.startswith('DISCORD_TOKEN='):
            values = shlex.split(line.split('=', 1)[1], comments=True)
            if len(values) == 1 and values[0]:
                return values[0]
    raise ValueError('Bot token unavailable')


def send_dm(message):
    token = token_from_env(HOME / 'chore_bot/.env')
    def post(endpoint, value):
        req = urllib.request.Request('https://discord.com/api/v10/' + endpoint,
            data=json.dumps(value).encode(), headers={'Authorization': 'Bot ' + token,
            'Content-Type': 'application/json', 'User-Agent': 'SprigBackupMonitor/1.0'}, method='POST')
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    channel = post('users/@me/channels', {'recipient_id': OWNER})
    return post('channels/' + channel['id'] + '/messages',
        {'content': message, 'allowed_mentions': {'parse': []}})['id']


def notify_transition(path, current, now, send=send_dm):
    state = read_json(path, {'problems': [], 'started': now.isoformat()})
    if state.get('problems') == current:
        return state
    old = state.get('problems', [])
    state.update(problems=current, changed_at=now.isoformat(), delivery='sending')
    # Commit before network I/O. Ambiguous Discord sends must never be replayed.
    write_json(path, state)
    message = ('Sprig backup alert:\n' + '\n'.join('• ' + p for p in current) +
        '\nCheck the Sprig backup instructions in How I Do Things.') if current else (
        'Sprig backups recovered: the server snapshot and laptop-copy checks are healthy again.')
    if current or old:
        try:
            state['message_id'] = send(message)
            state['delivery'] = 'sent'
        except Exception:
            state['delivery'] = 'failed_uncertain'
    write_json(path, state)
    return state


def check(root=ROOT, source=SOURCE, state=STATE, now=None, send=send_dm):
    now = now or datetime.now(EASTERN)
    with lock(state):
        health = read_json(state / 'health.json', {'problems': [], 'started': now.isoformat()})
        if not (state / 'health.json').exists():
            write_json(state / 'health.json', health)
        failed = False
        try:
            backup_daily(source, root, now)
            items = index(root, now)
        except Exception:
            failed, items = True, []
        laptop = read_json(state / 'laptop.json', {})
        current = problems(items, laptop, health['started'], now, failed)
        result = notify_transition(state / 'health.json', current, now, send)
        result['checked_at'] = now.isoformat()
        write_json(state / 'health.json', result)
        print(json.dumps({'checked_at': now.isoformat(), 'problems': current,
            'delivery': result.get('delivery', 'not_needed')}), flush=True)
        return 1 if current or result.get('delivery') == 'failed_uncertain' else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'index', 'receipt', 'status'])
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action == 'check':
            return check()
        if args.action == 'index':
            print(json.dumps(index()))
        elif args.action == 'receipt':
            receipt(json.loads(sys.stdin.read(4096)))
            print('Laptop receipt verified')
        else:
            print(json.dumps({'health': read_json(STATE / 'health.json', {}),
                'laptop': read_json(STATE / 'laptop.json', {})}))
    except Exception as exc:
        print('Backup monitor failed: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
