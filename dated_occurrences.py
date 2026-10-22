"""One-off reservations and skips keyed by local date and AM/PM slot."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from chore_timing import SCHEDULED


def install(ns, ui):
    db,timing=ns['db'],ui.timing
    db.executescript('''CREATE TABLE IF NOT EXISTS dated_occurrences(
        quest_id INTEGER NOT NULL, day TEXT NOT NULL, slot TEXT NOT NULL,
        frequency TEXT NOT NULL, state TEXT NOT NULL, actor TEXT NOT NULL,
        revision INTEGER NOT NULL, PRIMARY KEY(quest_id,day,slot));
    CREATE TABLE IF NOT EXISTS dated_occurrence_changes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL,
        day TEXT NOT NULL,slot TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,
        changed_at TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,
        undone_at TEXT);''')
    db.commit()

    def frequency(qid):
        row=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()
        return row[0] if row else None

    def slots(qid):
        f=frequency(qid)
        return ('am','pm') if f=='twice-daily' else ('am',) if f=='daily-am' else ('pm',) if f=='daily-pm' else ('day',) if f=='daily' or f in SCHEDULED else ()

    def when(day,slot):
        return datetime.combine(day,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).replace(hour=12 if slot=='pm' else 0)

    def key(qid,at=None):
        at=at or timing.now();offered=slots(qid)
        slot=('am' if at.hour<12 else 'pm') if offered==('am','pm') else offered[0] if offered else 'day'
        return at.date().isoformat(),slot

    def valid(qid,day,slot):
        f=frequency(qid)
        if ui.is_archived(qid) or slot not in slots(qid):return False
        if f in SCHEDULED and not timing.matches(day,f):return False
        moved=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone()
        return not moved or day.isoformat()>=moved[0]

    def record(qid,day,slot):
        return db.execute('SELECT frequency,state,actor,revision FROM dated_occurrences WHERE quest_id=? AND day=? AND slot=?',(qid,str(day),slot)).fetchone()

    def active(qid,at=None):
        at=at or timing.now()
        rows=db.execute("SELECT frequency,state,actor,revision,slot FROM dated_occurrences WHERE quest_id=? AND day=? AND state!='released'",(qid,at.date().isoformat())).fetchall()
        if not rows:return None
        _,slot=key(qid,at)
        row=next((row[:4] for row in rows if row[4]==slot),None)
        return row if row and row[0]==frequency(qid) and valid(qid,at.date(),slot) else None

    def skipped(qid,at=None):
        row=active(qid,at)
        return bool(row and row[1]=='skip')

    def owner(qid,at=None):
        at=at or timing.now();row=active(qid,at)
        return row[2] if row and row[1]=='claim' and ui.attendance.at(row[2],at) else None

    def base_owner(qid,at):
        q=db.execute('SELECT assigned_to FROM quests WHERE id=?',(qid,)).fetchone()
        # Resolve the exact Sunday 18:00 household week for this occurrence.
        start=at.replace(hour=18,minute=0,second=0,microsecond=0)-timedelta(days=(at.weekday()+1)%7)
        if at<start:start-=timedelta(days=7)
        weekly=db.execute('SELECT user_id FROM week_signups WHERE quest_id=? AND week_start=?',(qid,start.date().isoformat())).fetchone()
        uid=str(q[0]) if q and q[0] else weekly[0] if weekly else ui.repeating.owner(qid,at)
        return uid if uid and ui.attendance.at(uid,at) else None

    def snapshot(qid,day,slot):
        at=when(day,slot)
        return (ui.reassign_snapshot(qid),record(qid,day,slot),base_owner(qid,at))

    def change(actor,qid,day,slot,action,expected):
        at=when(day,slot)
        end=at+timedelta(hours=12 if slot in ('am','pm') else 24)
        if not valid(qid,day,slot) or (at<=timing.now() and action!='drop') or timing.now()>=end:return 'Choose a future scheduled date and slot. Nothing changed.'
        if snapshot(qid,day,slot)!=expected:return 'This occurrence or household schedule changed. Review it again.'
        if action not in ('claim','skip','drop'):return 'Choose a valid occurrence action.'
        before=record(qid,day,slot)
        if action=='claim':
            if before and before[1]=='skip':return 'Undo the skip before claiming this occurrence.'
            if not ui.attendance.at(actor,at):return 'You are away for this occurrence. Choose a day you are home.'
            uid=(before[2] if before and before[1]=='claim' and ui.attendance.at(before[2],at) else None) or base_owner(qid,at)
            if uid and uid!=str(actor):return 'Someone already has this occurrence. Nothing changed.'
        if action=='drop' and (not before or before[1]!='claim' or before[2]!=str(actor)):
            return 'Only the person with this dated claim can release it.'
        state='released' if action=='drop' else action
        if before and before[:3]==(frequency(qid),state,str(actor)):return 'This occurrence is already saved that way.'
        revision=(before[3] if before else 0)+1
        after=(frequency(qid),state,str(actor),revision)
        with db:
            db.execute('INSERT OR REPLACE INTO dated_occurrences VALUES(?,?,?,?,?,?,?)',(qid,day.isoformat(),slot,*after))
            db.execute('INSERT INTO dated_occurrence_changes(quest_id,day,slot,actor,action,changed_at,before_state,after_state) VALUES(?,?,?,?,?,?,?,?)',(qid,day.isoformat(),slot,str(actor),action,timing.now().isoformat(),json.dumps(before),json.dumps(after)))
            db.execute('INSERT INTO chore_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))
        return ('Claimed just this time.' if action=='claim' else 'Skipped just this time. Undo is below.' if action=='skip' else 'Dated claim released.')+' Later repeats, signups, and points are unchanged.'

    def transfer_current(actor,qid,target):
        day,slot=key(qid);before=record(qid,day,slot)
        if not before or before[1]!='claim':raise ValueError('Dated claim changed')
        after=(frequency(qid),'claim' if target else 'released',str(target or actor),before[3]+1)
        db.execute('INSERT OR REPLACE INTO dated_occurrences VALUES(?,?,?,?,?,?,?)',(qid,day,slot,*after))
        db.execute('INSERT INTO dated_occurrence_changes(quest_id,day,slot,actor,action,changed_at,before_state,after_state) VALUES(?,?,?,?,?,?,?,?)',(qid,day,slot,str(actor),'reassign' if target else 'drop',timing.now().isoformat(),json.dumps(before),json.dumps(after)))
        db.execute('INSERT INTO chore_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))

    def undo(actor,change_id):
        row=db.execute('SELECT quest_id,day,slot,actor,action,before_state,after_state,undone_at FROM dated_occurrence_changes WHERE id=?',(change_id,)).fetchone()
        if not row or row[3]!=str(actor) or row[4]!='skip':return 'Only the person who skipped can undo this skip.'
        qid,rawday,slot,_,_,before,after,undone=row;day=datetime.fromisoformat(rawday).date()
        end=when(day,slot)+(timedelta(hours=12) if slot=='am' else timedelta(days=1) if slot=='day' else timedelta(hours=12))
        current=record(qid,day,slot)
        if undone:return 'This skip was already undone.'
        if not valid(qid,day,slot) or timing.now()>=end or json.dumps(current)!=after:return 'The occurrence changed or ended. Nothing restored.'
        before=json.loads(before)
        if before and before[1]=='claim':
            uid=base_owner(qid,when(day,slot))
            if uid and uid!=before[2]:return 'Responsibility changed. Review this occurrence before restoring it.'
        restored=(frequency(qid),before[1],before[2],current[3]+1) if before else (frequency(qid),'released',str(actor),current[3]+1)
        with db:
            db.execute('INSERT OR REPLACE INTO dated_occurrences VALUES(?,?,?,?,?,?,?)',(qid,rawday,slot,*restored))
            db.execute('UPDATE dated_occurrence_changes SET undone_at=? WHERE id=?',(timing.now().isoformat(),change_id))
            db.execute('INSERT INTO chore_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))
        return 'Skip undone for this date and slot. Points and later repeats are unchanged.'

    def undo_id(actor,qid,day,slot):
        if timing.now()>=when(day,slot)+timedelta(hours=12 if slot in ('am','pm') else 24) or not valid(qid,day,slot):return None
        row=db.execute("SELECT id,after_state FROM dated_occurrence_changes WHERE quest_id=? AND day=? AND slot=? AND actor=? AND action='skip' AND undone_at IS NULL ORDER BY id DESC LIMIT 1",(qid,day.isoformat(),slot,str(actor))).fetchone()
        return row[0] if row and json.dumps(record(qid,day,slot))==row[1] else None

    def latest_undo(actor):
        rows=db.execute("SELECT c.id,c.quest_id,c.day,c.slot,c.after_state,d.frequency,d.state,d.actor,d.revision FROM dated_occurrence_changes c JOIN dated_occurrences d ON d.quest_id=c.quest_id AND d.day=c.day AND d.slot=c.slot WHERE c.actor=? AND c.action='skip' AND c.undone_at IS NULL AND d.state='skip' ORDER BY c.id DESC",(str(actor),)).fetchall()
        for event,qid,rawday,slot,expected,*current in rows:
            day=datetime.fromisoformat(rawday).date()
            if json.dumps(tuple(current))==expected and undo_id(actor,qid,day,slot)==event:return event,qid,day,slot
        return None

    def in_week(actor,qid,offset=0):
        start,end=ui.week_start(offset),ui.week_start(offset+1)
        for rawday,slot in db.execute("SELECT day,slot FROM dated_occurrences WHERE quest_id=? AND state='claim' AND actor=?",(qid,str(actor))):
            day=datetime.fromisoformat(rawday).date();at=when(day,slot)
            if start<=at<end and owner(qid,at)==str(actor):return True
        return False

    def upcoming(qid,start,end):
        for n in range((end-start).days):
            day=start+timedelta(days=n)
            for slot in slots(qid):
                if valid(qid,day,slot) and when(day,slot)>timing.now():yield day,slot

    return SimpleNamespace(transfer_current=transfer_current,slots=slots,when=when,key=key,valid=valid,record=record,active=active,skipped=skipped,owner=owner,base_owner=base_owner,snapshot=snapshot,change=change,undo=undo,undo_id=undo_id,upcoming=upcoming,in_week=in_week,latest_undo=latest_undo)
