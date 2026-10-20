"""Full-day Eastern availability overrides over the household rotation."""
from datetime import datetime, timedelta


class HouseholdAvailability:
    def __init__(self, db, timezone):
        self.db,self.timezone=db,timezone
        db.execute("""CREATE TABLE IF NOT EXISTS availability_exceptions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,
            start_date TEXT NOT NULL,end_date TEXT NOT NULL,state TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_availability_person_dates ON availability_exceptions(user_id,active,start_date,end_date)")
        db.commit()

    def at(self,user_id,when):
        local=when.astimezone(self.timezone)
        key=local.date().isoformat()
        row=self.db.execute('SELECT state FROM availability_exceptions WHERE user_id=? AND active=1 AND start_date<=? AND end_date>=?',(str(user_id),key,key)).fetchone()
        if row:
            return row[0]=='home'
        if not self.db.execute('SELECT 1 FROM alternating_members WHERE user_id=?',(str(user_id),)).fetchone():
            return True
        start=(local-timedelta(days=(local.weekday()+1)%7)).replace(hour=18,minute=0,second=0,microsecond=0)
        if local<start:
            start-=timedelta(days=7)
        return ((start.date()-datetime(2026,10,18).date()).days//7)%2==1

    def week(self,user_id,start):
        result=[]
        for offset in range(8):
            when=start if offset==0 else (start+timedelta(days=offset)).replace(hour=12)
            result.append((when,self.at(user_id,when)))
        return result

    def status(self,user_id,start):
        states=[value for _,value in self.week(user_id,start)]
        return 'home' if all(states) else ('away' if not any(states) else 'partial')

    def add(self,user_id,start,end,state,note=''):
        try:
            first,last=datetime.strptime(start,'%Y-%m-%d').date(),datetime.strptime(end,'%Y-%m-%d').date()
        except ValueError:
            return 'Use dates like 2026-10-24 (YYYY-MM-DD).'
        if first.isoformat()!=start or last.isoformat()!=end or last<first or (last-first).days>365 or state not in ('home','away'):
            return 'Choose Home or Away and a date range of at most 366 days, ending on or after its start.'
        existing=self.db.execute('SELECT id,start_date,end_date,state FROM availability_exceptions WHERE user_id=? AND active=1 AND start_date<=? AND end_date>=?',(str(user_id),end,start)).fetchall()
        if any(row[1:]==(start,end,state) for row in existing):
            return 'That exception is already saved. Nothing duplicated.'
        if existing:
            return 'Those dates overlap an existing exception. Cancel that exception first, then add the replacement.'
        with self.db:
            self.db.execute('INSERT INTO availability_exceptions(user_id,start_date,end_date,state,note) VALUES(?,?,?,?,?)',(str(user_id),start,end,state,note.strip()[:300]))
        return 'Saved. Full calendar days are '+state+' in Eastern time; the normal rotation resumes afterward. Existing responsibilities were kept—review any coverage warnings.'
