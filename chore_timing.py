"""Local wall-clock recurrence for weekday and twice-daily chores."""
from datetime import datetime, timedelta
from itertools import combinations

WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
DAY_COLORS = dict(zip(WEEKDAYS, ('🔴','🟠','🟡','🟢','🔵','🟣','🩷')))
DAY_LEGEND = ' · '.join(f'{DAY_COLORS[day]} {day[:3].capitalize()}' for day in WEEKDAYS)


def day_badge(day, full=False):
    return f"{DAY_COLORS[day]} {day.capitalize() if full else day[:3].capitalize()}"


PAIRED_DAYS = tuple('days:' + ','.join(pair) for pair in combinations(WEEKDAYS, 2))
ALTERNATING_DAYS = tuple(f'{phase}:{day}' for phase in ('away', 'home') for day in WEEKDAYS)
SCHEDULED = frozenset((*WEEKDAYS, *PAIRED_DAYS, *ALTERNATING_DAYS))
WEEKLY_FREQUENCIES = frozenset(('daily', 'twice-daily', 'weekly', *SCHEDULED))


class ChoreTiming:
    def __init__(self, namespace, db):
        self.ns, self.db = namespace, db
        self.original_reset = namespace['calculate_reset_after']
        self.db.execute('CREATE TABLE IF NOT EXISTS chore_timing (quest_id INTEGER PRIMARY KEY, ready_from TEXT NOT NULL)')
        self.db.execute("CREATE TABLE IF NOT EXISTS missed_chore_policy (quest_id INTEGER PRIMARY KEY, policy TEXT NOT NULL CHECK(policy IN ('keep','skip')), deadline TEXT)")
        self.db.commit()
        namespace['VALID_FREQUENCIES'].update(('twice-daily', *SCHEDULED))
        namespace['FREQUENCY_ALIASES'].update({value: value for value in ('twice-daily', *SCHEDULED)})
        namespace['calculate_reset_after'] = self.calculate_reset

    def now(self):
        return self.ns['now_local']().astimezone(self.ns['QUEST_TIMEZONE'])

    def next_weekday(self, when, weekday, strictly_after=False):
        start=when.astimezone(self.ns['QUEST_TIMEZONE']).replace(hour=0,minute=0,second=0,microsecond=0)
        start += timedelta(days=(weekday-start.weekday()) % 7)
        if strictly_after and start <= when:
            start += timedelta(days=7)
        return start

    def matches(self, day, frequency):
        if frequency in WEEKDAYS:
            return day.weekday() == WEEKDAYS.index(frequency)
        kind, value = frequency.split(':', 1)
        if kind == 'days':
            return WEEKDAYS[day.weekday()] in value.split(',')
        # Midnight occurrences belong to the week that began Sunday at 6 p.m.
        start = day - timedelta(days=(day.weekday() + 1) % 7 or 7)
        parity = ((start - datetime(2026, 10, 18).date()).days // 7) % 2
        return day.weekday() == WEEKDAYS.index(value) and parity == (kind == 'home')

    def next_due(self, when, frequency, strictly_after=False):
        local = when.astimezone(self.ns['QUEST_TIMEZONE'])
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        for offset in range(15):
            candidate = start + timedelta(days=offset)
            if self.matches(candidate.date(), frequency) and (not strictly_after or candidate > local):
                return candidate
        raise ValueError('No occurrence found for schedule')

    def in_week(self, frequency, start):
        if frequency not in SCHEDULED:
            return True
        return any(self.matches((start + timedelta(days=offset)).date(), frequency) for offset in range(1, 8))

    def calculate_reset(self, when, frequency):
        local=when.astimezone(self.ns['QUEST_TIMEZONE'])
        if frequency == 'twice-daily':
            if local.hour < 12:
                return local.replace(hour=12,minute=0,second=0,microsecond=0).isoformat()
            return (local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        if frequency in SCHEDULED:
            return self.next_due(local,frequency,True).isoformat()
        return self.original_reset(when,frequency)

    def initialize(self, quest_id, frequency):
        if frequency in SCHEDULED:
            ready=self.next_due(self.now(),frequency)
            self.db.execute('INSERT OR REPLACE INTO chore_timing VALUES (?,?)',(quest_id,ready.isoformat()))
        else:
            self.db.execute('DELETE FROM chore_timing WHERE quest_id=?',(quest_id,))
        if self.policy(quest_id)=='skip':
            self.db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(self.deadline(quest_id,frequency),quest_id))

    def policy(self, quest_id):
        row=self.db.execute('SELECT policy FROM missed_chore_policy WHERE quest_id=?',(quest_id,)).fetchone()
        return row[0] if row else 'keep'

    def policy_state(self, quest_id):
        return self.db.execute('SELECT policy,deadline FROM missed_chore_policy WHERE quest_id=?',(quest_id,)).fetchone()

    def deadline(self, quest_id, frequency):
        if frequency in SCHEDULED:
            state=self.state(quest_id)
            ready=datetime.fromisoformat(state[0]) if state else self.next_due(self.now(),frequency)
            return (ready+timedelta(days=1)).isoformat()
        return self.calculate_reset(self.now(),frequency)

    def set_policy(self, quest_id, policy):
        row=self.db.execute('SELECT frequency FROM quests WHERE id=?',(quest_id,)).fetchone()
        if not row or policy not in ('keep','skip'):
            return 'Choose a valid missed-chore setting.'
        if row[0]=='one-time' and policy=='skip':
            return 'One-time chores have no deadline to skip. Keep overdue, or choose a repeating schedule first.'
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO missed_chore_policy VALUES(?,?,?)',(quest_id,policy,self.deadline(quest_id,row[0]) if policy=='skip' else None))
        self.skip_missed()
        return 'Saved: '+('Skip if missed. Missed occurrences earn no points.' if policy=='skip' else 'Keep overdue. It remains due until completed.')

    def skip_missed(self):
        now=self.now()
        rows=self.db.execute("SELECT q.id,q.frequency,q.completed,p.deadline FROM quests q JOIN missed_chore_policy p ON p.quest_id=q.id WHERE p.policy='skip'").fetchall()
        with self.db:
            for qid,frequency,completed,deadline in rows:
                if frequency=='one-time':
                    continue
                if not deadline:
                    self.db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(self.deadline(qid,frequency),qid))
                    continue
                if now < datetime.fromisoformat(deadline):
                    continue
                if not completed:
                    self.db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
                if frequency in SCHEDULED:
                    self.db.execute('INSERT OR REPLACE INTO chore_timing VALUES(?,?)',(qid,self.next_due(now,frequency).isoformat()))
                self.db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(self.deadline(qid,frequency),qid))

    def state(self, quest_id):
        return self.db.execute('SELECT ready_from FROM chore_timing WHERE quest_id=?',(quest_id,)).fetchone()

    def ready(self, quest_id):
        from datetime import datetime
        row=self.db.execute('SELECT frequency FROM quests WHERE id=?',(quest_id,)).fetchone()
        if not row or row[0] not in SCHEDULED:
            return True
        state=self.state(quest_id)
        if not state:
            with self.db:
                self.initialize(quest_id,row[0])
            state=self.state(quest_id)
        return self.now() >= datetime.fromisoformat(state[0])

    def completion_reset(self, quest_id, when, frequency):
        reset=self.calculate_reset(when,frequency)
        if frequency in SCHEDULED:
            self.db.execute('INSERT OR REPLACE INTO chore_timing VALUES (?,?)',(quest_id,reset))
        if self.policy(quest_id)=='skip':
            self.db.execute('UPDATE missed_chore_policy SET deadline=? WHERE quest_id=?',(self.deadline(quest_id,frequency),quest_id))
        return reset

    def schedule_label(self, frequency):
        if frequency == 'twice-daily':
            return 'Twice daily · morning (before noon) / afternoon-evening (after noon)'
        if frequency in WEEKDAYS:
            return f'Every {day_badge(frequency,True)}'
        if frequency in PAIRED_DAYS:
            return 'Every ' + ' and '.join(day_badge(d,True) for d in frequency[5:].split(',')) + ''
        if frequency in ALTERNATING_DAYS:
            phase, day = frequency.split(':')
            return f'Every other {day_badge(day,True)} · Kas/Z {phase} weeks'
        return frequency.capitalize()

    def label(self, frequency, quest_id=None):
        text=self.schedule_label(frequency)
        if quest_id is not None:
            text+=' · '+('Skip if missed' if self.policy(quest_id)=='skip' else 'Keep overdue')
        return text
