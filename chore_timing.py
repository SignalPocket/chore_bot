"""Local wall-clock recurrence for weekday and twice-daily chores."""
from datetime import timedelta

WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
WEEKLY_FREQUENCIES = frozenset(('daily', 'twice-daily', 'weekly', *WEEKDAYS))


class ChoreTiming:
    def __init__(self, namespace, db):
        self.ns, self.db = namespace, db
        self.original_reset = namespace['calculate_reset_after']
        self.db.execute('CREATE TABLE IF NOT EXISTS chore_timing (quest_id INTEGER PRIMARY KEY, ready_from TEXT NOT NULL)')
        self.db.commit()
        namespace['VALID_FREQUENCIES'].update(('twice-daily', *WEEKDAYS))
        namespace['FREQUENCY_ALIASES'].update({value: value for value in ('twice-daily', *WEEKDAYS)})
        namespace['calculate_reset_after'] = self.calculate_reset

    def now(self):
        return self.ns['now_local']().astimezone(self.ns['QUEST_TIMEZONE'])

    def next_weekday(self, when, weekday, strictly_after=False):
        start=when.astimezone(self.ns['QUEST_TIMEZONE']).replace(hour=0,minute=0,second=0,microsecond=0)
        start += timedelta(days=(weekday-start.weekday()) % 7)
        if strictly_after and start <= when:
            start += timedelta(days=7)
        return start

    def calculate_reset(self, when, frequency):
        local=when.astimezone(self.ns['QUEST_TIMEZONE'])
        if frequency == 'twice-daily':
            if local.hour < 12:
                return local.replace(hour=12,minute=0,second=0,microsecond=0).isoformat()
            return (local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        if frequency in WEEKDAYS:
            return self.next_weekday(local,WEEKDAYS.index(frequency),True).isoformat()
        return self.original_reset(when,frequency)

    def initialize(self, quest_id, frequency):
        if frequency in WEEKDAYS:
            ready=self.next_weekday(self.now(),WEEKDAYS.index(frequency))
            self.db.execute('INSERT OR REPLACE INTO chore_timing VALUES (?,?)',(quest_id,ready.isoformat()))
        else:
            self.db.execute('DELETE FROM chore_timing WHERE quest_id=?',(quest_id,))

    def state(self, quest_id):
        return self.db.execute('SELECT ready_from FROM chore_timing WHERE quest_id=?',(quest_id,)).fetchone()

    def ready(self, quest_id):
        from datetime import datetime
        row=self.db.execute('SELECT frequency FROM quests WHERE id=?',(quest_id,)).fetchone()
        if not row or row[0] not in WEEKDAYS:
            return True
        state=self.state(quest_id)
        if not state:
            with self.db:
                self.initialize(quest_id,row[0])
            state=self.state(quest_id)
        return self.now() >= datetime.fromisoformat(state[0])

    def completion_reset(self, quest_id, when, frequency):
        reset=self.calculate_reset(when,frequency)
        if frequency in WEEKDAYS:
            self.db.execute('INSERT OR REPLACE INTO chore_timing VALUES (?,?)',(quest_id,reset))
        return reset

    def label(self, frequency):
        if frequency == 'twice-daily':
            return 'Twice daily · morning (before noon) / afternoon-evening (after noon)'
        if frequency in WEEKDAYS:
            return f'Every {frequency.capitalize()} · stays due until done'
        return frequency.capitalize()
