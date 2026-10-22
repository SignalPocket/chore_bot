"""Saved weekday/shift responsibilities, activated only while their person is home."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import discord

DAILY = ('daily','twice-daily','daily-am','daily-pm')


def install(ns,ui):
    db,timing=ns['db'],ui.timing
    db.executescript('''CREATE TABLE IF NOT EXISTS repeating_signups(
        quest_id INTEGER NOT NULL,weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
        shift TEXT NOT NULL CHECK(shift IN ('day','am','pm')),user_id TEXT NOT NULL,
        PRIMARY KEY(quest_id,weekday,shift,user_id));
        CREATE TABLE IF NOT EXISTS repeating_signup_changes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL,actor TEXT NOT NULL,
        changed_at TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL);''')
    db.commit()

    def slots(qid):
        return db.execute('SELECT weekday,shift,user_id FROM repeating_signups WHERE quest_id=? ORDER BY weekday,shift,user_id',(qid,)).fetchall()

    def shifts(qid):
        row=db.execute('SELECT frequency FROM quests WHERE id=?',(qid,)).fetchone()
        if not row or row[0] not in DAILY:return ()
        return ('am','pm') if row[0]=='twice-daily' else ('am',) if row[0]=='daily-am' else ('pm',) if row[0]=='daily-pm' else ('day',)

    def candidates(qid,when):
        rows=db.execute('SELECT shift,user_id FROM repeating_signups WHERE quest_id=? AND weekday=?',(qid,when.weekday())).fetchall()
        if not rows:return []
        valid=shifts(qid)
        shift=('am' if when.hour<12 else 'pm') if valid==('am','pm') else next(iter(valid),None)
        return [uid for saved,uid in rows if saved==shift]

    def reserved(qid,when=None):
        people=candidates(qid,when or timing.now())
        return people[0] if people else None

    def owner(qid,when=None):
        when=when or timing.now()
        active=[uid for uid in candidates(qid,when) if ui.attendance.at(uid,when)]
        # Attendance exceptions can create a new overlap after signup. Never pick
        # an arbitrary winner: leave coverage visibly unclaimed until resolved.
        return active[0] if len(active)==1 else None

    def in_week(uid,qid,offset=0):
        if not db.execute('SELECT 1 FROM repeating_signups WHERE quest_id=? AND user_id=?',(qid,str(uid))).fetchone():return False
        start,end=ui.week_start(offset),ui.week_start(offset+1)
        return any(owner(qid,when)==str(uid) for when in occurrences(qid,start,end))

    def occurrences(qid,start,end):
        for n in range((end.date()-start.date()).days+1):
            day=(start+timedelta(days=n)).replace(hour=0,minute=0,second=0,microsecond=0)
            for shift in shifts(qid):
                when=day.replace(hour=12 if shift=='pm' else 0)
                if start<=when<end:yield when

    def snapshot(qid):
        people=[uid for _,_,uid in slots(qid)]
        return (ui.reassign_snapshot(qid),slots(qid),ui.attendance.defaults_snapshot(people))

    def save(actor,qid,days,selected_shifts,expected,remove=False,replace_cells=None):
        import json
        ns['reset_due_quests']()
        if snapshot(qid)!=expected or ui.is_archived(qid):return 'This chore, attendance or signup changed. Review it again.'
        days=sorted(set(days));selected_shifts=sorted(set(selected_shifts));valid=shifts(qid)
        cells=set((day,shift) for day in days for shift in selected_shifts) if replace_cells is None else set(tuple(cell) for cell in replace_cells)
        if not valid or (not cells and replace_cells is None) or any(type(d) is not int or not 0<=d<=6 or shift not in valid for d,shift in cells):
            return 'Choose weekdays and the available shifts for a daily chore.'
        before=slots(qid)
        if replace_cells is not None and cells=={(d,shift) for d,shift,uid in before if uid==str(actor)}:return "Nothing changed. Your repeating signups already match."
        if not remove and cells:
            q=db.execute('SELECT assigned_to FROM quests WHERE id=?',(qid,)).fetchone()
            if q[0] or db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,ui.week_key())).fetchone():
                return 'Release the ongoing assignment or weekly signups before adding repeating days.'
            for day,shift,uid in before:
                if (day,shift) not in cells or uid==str(actor):continue
                # Two rotation cycles establish the ordinary weekly/alternating
                # defaults; also inspect saved dated exceptions within a year.
                dates={timing.now().date()+timedelta(days=n) for n in range(28)}
                for start,end in db.execute('SELECT start_date,end_date FROM availability_exceptions WHERE active=1 AND user_id IN (?,?)',(str(actor),uid)):
                    begin=max(datetime.fromisoformat(start).date(),timing.now().date())
                    finish=min(datetime.fromisoformat(end).date(),timing.now().date()+timedelta(days=366))
                    dates.update(begin+timedelta(days=n) for n in range(max(0,(finish-begin).days+1)))
                for date in dates:
                    if date.weekday()!=day:continue
                    when=datetime.combine(date,datetime.min.time(),tzinfo=ns['QUEST_TIMEZONE']).replace(hour=12 if shift=='pm' else 0)
                    if ui.attendance.at(actor,when) and ui.attendance.at(uid,when):
                        return 'Someone already has one of those weekday/shift slots while you are both home. Nothing changed.'
            current_claim=db.execute('SELECT user_id FROM claims WHERE quest_id=?',(qid,)).fetchone()
            current_shift=('am' if timing.now().hour<12 else 'pm') if valid==('am','pm') else valid[0]
            if current_claim and current_claim[0]!=str(actor) and (timing.now().weekday(),current_shift) in cells:
                return 'Someone has the current occurrence. Let them finish or drop it before reserving this day.'
        with db:
            if replace_cells is not None:db.execute('DELETE FROM repeating_signups WHERE quest_id=? AND user_id=?',(qid,str(actor)))
            for day,shift in sorted(cells):
                if remove:db.execute('DELETE FROM repeating_signups WHERE quest_id=? AND weekday=? AND shift=? AND user_id=?',(qid,day,shift,str(actor)))
                else:db.execute('INSERT OR IGNORE INTO repeating_signups VALUES(?,?,?,?)',(qid,day,shift,str(actor)))
            after=slots(qid)
            if after==before:return 'Nothing changed. Your repeating signups are already in that state.'
            db.execute('INSERT INTO repeating_signup_changes(quest_id,actor,changed_at,before_state,after_state) VALUES(?,?,?,?,?)',
                (qid,str(actor),timing.now().isoformat(),json.dumps(before),json.dumps(after)))
            db.execute('INSERT INTO chore_revisions VALUES(?,1) ON CONFLICT(quest_id) DO UPDATE SET revision=revision+1',(qid,))
            # A claim made by this same person must not mask their other day/shift owners.
            if owner(qid)==str(actor):db.execute('DELETE FROM claims WHERE quest_id=? AND user_id=?',(qid,str(actor)))
        return ('Repeating signup released.' if remove else 'Repeating days saved. You are responsible only when home; away occurrences need coverage.')+' Points and completed history are unchanged.'

    def replace(actor,qid,cells,expected):
        return save(actor,qid,[],[],expected,replace_cells=cells)

    def install_views(w):
        class Repeating(w.View):
            def __init__(self,actor,qid,guild=None,days=None,selected_shifts=None,cells=None,expected=None):
                super().__init__(actor)
                expected=snapshot(qid) if expected is None else expected
                if cells is None:
                    cells={(d,shift) for d,shift,uid in slots(qid) if uid==str(actor)} if days is None and selected_shifts is None else {(d,shift) for d in (days or ()) for shift in (selected_shifts or ())}
                cells=set(tuple(cell) for cell in cells)
                self.recovery_context={'screen':'repeating_signup','qid':qid,'cells':[list(cell) for cell in sorted(cells)]}
                self.name_ids=[uid for _,_,uid in slots(qid)]
                self.rebuild=lambda:Repeating(actor,qid,guild,cells=cells,expected=expected)
                self.embed=discord.Embed(title='Repeating days',description='Your saved days and shifts are selected. Click a slot to add or remove it, then Save once. Only your pattern changes; responsibility applies only while you are home.',color=0x6B9B77)
                labels=('Mon','Tue','Wed','Thu','Fri','Sat','Sun')
                existing=slots(qid)
                if existing:self.embed.add_field(name='Saved responsibilities',value='\n'.join(f'{labels[d]} · {shift.upper()} · {w.person(uid,guild)} · only when home' for d,shift,uid in existing)[:1000],inline=False)
                offered=shifts(qid)
                for day in range(7):
                    for shift_index,shift in enumerate(offered):
                        async def toggle(i,day=day,shift=shift):
                            if not await self.interaction_check(i):return
                            await w.present(i,Repeating(actor,qid,i.guild,cells=cells^{(day,shift)},expected=expected))
                        label=('✓ ' if (day,shift) in cells else '')+labels[day]+(' · '+shift.upper() if shift!='day' else '')
                        self.button(label,toggle,row=(day*len(offered)+shift_index)//4,primary=(day,shift) in cells)
                async def save_selected(i):
                    if not await self.interaction_check(i):return
                    await i.response.defer()
                    async with ui.mutation_lock:notice=replace(i.user.id,qid,cells,expected)
                    await w.present(i,Repeating(actor,qid,i.guild),notice)
                self.button('Save repeating days',save_selected,row=4,primary=True)
                self.button('Clear selection',lambda i:w.present(i,Repeating(actor,qid,i.guild,cells=(),expected=expected)),row=4)
                self.nav(lambda:w.Card(actor,qid,guild=guild))
        return Repeating

    return SimpleNamespace(slots=slots,shifts=shifts,owner=owner,reserved=reserved,save=save,replace=replace,snapshot=snapshot,in_week=in_week,occurrences=occurrences,install_views=install_views)
