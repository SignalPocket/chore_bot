"""Append-only completion records and conservative, atomic undo."""
import json


def install(ns, ui):
    db=ns['db']
    db.execute('''CREATE TABLE IF NOT EXISTS completion_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL,user_id TEXT NOT NULL,
        chore_name TEXT NOT NULL,points INTEGER NOT NULL,completed_at TEXT NOT NULL,
        before_state TEXT NOT NULL,after_state TEXT NOT NULL,undone_at TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS points_reset_log(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,user_id TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,created_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS owner_action_log(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS points_reset_batches(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL,undone_at TEXT)''')
    db.commit()

    def state(qid,uid):
        return dict(planning=ui.planning.history_state(qid) if hasattr(ui,'planning') else None,reset_epoch=db.execute('SELECT COALESCE(MAX(id),0) FROM points_reset_log WHERE user_id=?',(str(uid),)).fetchone()[0],week=ui.week_key(),week_owner=ui.weekly_owner(qid),next_owner=ui.weekly_owner(qid,1),move=db.execute('SELECT day FROM occurrence_moves WHERE quest_id=?',(qid,)).fetchone(),quest=db.execute('SELECT name,frequency,points,assigned_to,completed,last_completed,reset_after FROM quests WHERE id=?',(qid,)).fetchone(),
            user=db.execute('SELECT points,streak,last_completed FROM users WHERE id=?',(str(uid),)).fetchone(),
            claim=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone(),
            timing=db.execute('SELECT ready_from FROM chore_timing WHERE quest_id=?',(qid,)).fetchone(),
            policy=db.execute('SELECT policy,deadline FROM missed_chore_policy WHERE quest_id=?',(qid,)).fetchone())

    def capture(qid,uid):
        return json.dumps(state(qid,uid))

    def record(qid,uid,before):
        current=state(qid,uid)
        db.execute('INSERT INTO completion_log(quest_id,user_id,chore_name,points,completed_at,before_state,after_state) VALUES(?,?,?,?,?,?,?)',
            (qid,str(uid),current['quest'][0],current['quest'][2],current['quest'][5],before,json.dumps(current)))

    def undo(uid,event_id,actor=None):
        if actor is not None and actor!=301104023405199361:return "Only ginaria can correct another person’s completion."
        # Readiness/reset can change the occurrence; never rewind a later occurrence.
        ns['reset_due_quests']()
        event=db.execute('SELECT quest_id,user_id,before_state,after_state,undone_at FROM completion_log WHERE id=?',(event_id,)).fetchone()
        if not event or event[1]!=str(uid) or event[4]:
            return 'This completion is no longer available to undo.'
        latest=db.execute('SELECT id FROM completion_log WHERE user_id=? AND undone_at IS NULL ORDER BY id DESC LIMIT 1',(str(uid),)).fetchone()
        if latest!=(event_id,):
            return 'Undo your most recent completion first, so your points and streak stay correct.'
        qid=event[0]
        before,after=json.loads(event[2]),json.loads(event[3])
        after.setdefault('reset_epoch',0)
        after.setdefault('planning',None)
        if json.loads(capture(qid,uid))!=after or ui.is_archived(qid):
            return 'This chore, occurrence, or points total changed. It cannot safely be undone from this screen.'
        with db:
            db.execute('UPDATE quests SET name=?,frequency=?,points=?,assigned_to=?,completed=?,last_completed=?,reset_after=? WHERE id=?',(*before['quest'],qid))
            db.execute('UPDATE users SET points=?,streak=?,last_completed=? WHERE id=?',(*before['user'],str(uid)))
            db.execute('DELETE FROM claims WHERE quest_id=?',(qid,))
            if before['claim']:
                db.execute('INSERT INTO claims VALUES(?,?)',(qid,before['claim'][0]))
            for table,columns,value in [('occurrence_moves','day',before['move']),('chore_timing','ready_from',before['timing']),('missed_chore_policy','policy,deadline',before['policy'])]:
                db.execute('DELETE FROM '+table+' WHERE quest_id=?',(qid,))
                if value:
                    db.execute('INSERT INTO '+table+'(quest_id,'+columns+') VALUES('+','.join('?' for _ in range(len(value)+1))+')',(qid,*value))
            db.execute('UPDATE completion_log SET undone_at=? WHERE id=?',(ns['now_local']().isoformat(),event_id))
            if actor is not None:
                db.execute('INSERT INTO owner_action_log(actor,action,target,details,created_at) VALUES(?,?,?,?,?)',(str(actor),'correct_completion',str(event_id),json.dumps(dict(user_id=str(uid),before=after,after=before)),ns['now_local']().isoformat()))
        return 'Completion undone. Points, streak, and the previous chore responsibility were restored.'

    def owner_undo(actor,event_id):
        if actor!=301104023405199361:return 'Only ginaria can correct another person’s completion.'
        row=db.execute('SELECT user_id FROM completion_log WHERE id=?',(event_id,)).fetchone()
        return undo(row[0],event_id,actor=actor) if row else 'This completion no longer exists.'

    ui.owner_undo_completion=owner_undo
    ui.capture_completion=capture
    ui.record_completion=record
    ui.undo_completion=undo
