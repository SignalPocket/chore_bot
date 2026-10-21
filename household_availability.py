"""Full-day Eastern availability overrides over the household rotation."""
from datetime import datetime, timedelta
import json


class HouseholdAvailability:
    def __init__(self, db, timezone):
        self.db,self.timezone=db,timezone
        db.execute("""CREATE TABLE IF NOT EXISTS availability_exceptions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,
            start_date TEXT NOT NULL,end_date TEXT NOT NULL,state TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_availability_person_dates ON availability_exceptions(user_id,active,start_date,end_date)")
        db.execute('''CREATE TABLE IF NOT EXISTS availability_defaults(
            user_id TEXT PRIMARY KEY,mode TEXT NOT NULL,weekdays TEXT NOT NULL,
            revision INTEGER NOT NULL,updated_by TEXT NOT NULL,updated_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS availability_default_changes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,people TEXT NOT NULL,
            before_state TEXT NOT NULL,after_state TEXT NOT NULL,created_at TEXT NOT NULL)''')
        db.commit()

    def profile(self,user_id):
        return self.db.execute('SELECT mode,weekdays,revision FROM availability_defaults WHERE user_id=?',(str(user_id),)).fetchone() or ('household','[]',0)

    def defaults_snapshot(self,people):
        return [(str(uid),self.profile(uid),bool(self.db.execute('SELECT 1 FROM alternating_members WHERE user_id=?',(str(uid),)).fetchone())) for uid in sorted(set(str(uid) for uid in people))]

    def describe(self,user_id,mode=None,weekdays=None):
        saved=self.profile(user_id)
        mode=mode or saved[0]
        days=json.loads(saved[1]) if weekdays is None else list(weekdays)
        if mode=='household':
            rotating=self.db.execute('SELECT 1 FROM alternating_members WHERE user_id=?',(str(user_id),)).fetchone()
            return 'Household default: alternating Kas/Zel weeks' if rotating else 'Household default: home every day'
        if mode=='home':return 'Home every day'
        if mode=='away':return 'Away every day'
        if mode=='same':return 'Alternating weeks: home on Kas/Zel home weeks'
        if mode=='opposite':return 'Alternating weeks: home on opposite weeks'
        labels=('Mon','Tue','Wed','Thu','Fri','Sat','Sun')
        return 'Home: '+(', '.join(labels[d] for d in sorted(days)) if days else 'no regular days')+'; away on other weekdays'

    def set_defaults(self,actor,people,mode,weekdays,expected,when):
        people=sorted(set(str(uid) for uid in people))
        if not 1<=len(people)<=10 or any(not uid.isdecimal() for uid in people):return 'Choose one to ten household people.'
        if mode not in ('household','home','away','weekly','same','opposite'):return 'Choose a usual schedule.'
        try:days=sorted(set(int(day) for day in weekdays)) if mode=='weekly' else []
        except (ValueError,TypeError):return 'Choose valid weekdays.'
        if any(day<0 or day>6 for day in days):return 'Choose valid weekdays.'
        if mode=='weekly' and not days:return 'Choose at least one home weekday, or use Away every day.'
        current=self.defaults_snapshot(people)
        if current!=expected:return 'A usual schedule changed. Review the current defaults before saving.'
        encoded=json.dumps(days)
        if all(row[1][:2]==(mode,encoded) for row in current):return 'Usual schedules already match. Nothing changed.'
        stamp=when.astimezone(self.timezone).isoformat()
        with self.db:
            for uid,profile,rotating in current:
                self.db.execute('INSERT OR REPLACE INTO availability_defaults VALUES(?,?,?,?,?,?)',(uid,mode,encoded,profile[2]+1,str(actor),stamp))
            self.db.execute('INSERT INTO availability_default_changes(actor,people,before_state,after_state,created_at) VALUES(?,?,?,?,?)',
                (str(actor),json.dumps(people),json.dumps(current),json.dumps(self.defaults_snapshot(people)),stamp))
        return 'Usual schedule saved. Date overrides still take priority. Chore responsibilities and points are unchanged.'

    def at(self,user_id,when):
        local=when.astimezone(self.timezone)
        key=local.date().isoformat()
        row=self.db.execute('SELECT state FROM availability_exceptions WHERE user_id=? AND active=1 AND start_date<=? AND end_date>=?',(str(user_id),key,key)).fetchone()
        if row:
            return row[0]=='home'
        mode,encoded,revision=self.profile(user_id)
        if mode=='home':return True
        if mode=='away':return False
        if mode=='weekly':return local.weekday() in json.loads(encoded)
        if mode=='household' and not self.db.execute('SELECT 1 FROM alternating_members WHERE user_id=?',(str(user_id),)).fetchone():
            return True
        start=(local-timedelta(days=(local.weekday()+1)%7)).replace(hour=18,minute=0,second=0,microsecond=0)
        if local<start:
            start-=timedelta(days=7)
        home=((start.date()-datetime(2026,10,18).date()).days//7)%2==1
        return not home if mode=='opposite' else home

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
        return 'Saved. Full calendar days are '+state+' in Eastern time; the usual schedule resumes afterward. Existing responsibilities were kept—review any coverage warnings.'
