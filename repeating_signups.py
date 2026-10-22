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

    def save(actor,qid,days,selected_shifts,expected,remove=False):
        import json
        ns['reset_due_quests']()
        if snapshot(qid)!=expected or ui.is_archived(qid):return 'This chore, attendance or signup changed. Review it again.'
        days=sorted(set(days));selected_shifts=sorted(set(selected_shifts));valid=shifts(qid)
        if not valid or not days or not selected_shifts or any(type(d) is not int or not 0<=d<=6 for d in days) or any(s not in valid for s in selected_shifts):
            return 'Choose weekdays and the available shifts for a daily chore.'
        before=slots(qid)
        if not remove:
            q=db.execute('SELECT assigned_to FROM quests WHERE id=?',(qid,)).fetchone()
            if q[0] or db.execute('SELECT 1 FROM week_signups WHERE quest_id=? AND week_start>=?',(qid,ui.week_key())).fetchone():
                return 'Release the ongoing assignment or weekly signups before adding repeating days.'
            for day,shift,uid in before:
                if day not in days or shift not in selected_shifts or uid==str(actor):continue
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
            if current_claim and current_claim[0]!=str(actor) and timing.now().weekday() in days and current_shift in selected_shifts:
                return 'Someone has the current occurrence. Let them finish or drop it before reserving this day.'
        with db:
            for day in days:
                for shift in selected_shifts:
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

    def install_views(w):
        class Repeating(w.View):
            def __init__(self,actor,qid,guild=None,days=(),selected_shifts=()):
                super().__init__(actor)
                self.recovery_context={'screen':'repeating_signup','qid':qid,'days':list(days),'shifts':list(selected_shifts)}
                self.embed=discord.Embed(title='Repeating days',description='Choose weekdays and shifts. These repeat only when you are home, using your usual schedule and date exceptions. Away slots stay open for coverage. Nothing saves until you confirm.',color=0x6B9B77)
                self.name_ids=[uid for _,_,uid in slots(qid)]
                labels=('Mon','Tue','Wed','Thu','Fri','Sat','Sun')
                existing=slots(qid)
                if existing:self.embed.add_field(name='Saved responsibilities',value='\n'.join(f'{labels[d]} · {s.upper()} · {w.person(uid,guild)} · only when home' for d,s,uid in existing)[:1000],inline=False)
                def view(new_days=days,new_shifts=selected_shifts):return Repeating(actor,qid,guild,new_days,new_shifts)
                for day,label in enumerate(labels):
                    async def toggle(i,day=day):
                        if not await self.interaction_check(i):return
                        await w.present(i,view(tuple(sorted(set(days)^{day}))))
                    self.button(('✓ ' if day in days else '')+label,toggle,row=0 if day<4 else 1,primary=day in days)
                for shift in shifts(qid):
                    async def toggle(i,shift=shift):
                        if not await self.interaction_check(i):return
                        await w.present(i,view(days,tuple(sorted(set(selected_shifts)^{shift}))))
                    self.button(('✓ ' if shift in selected_shifts else '')+{'day':'Whole day','am':'AM','pm':'PM'}[shift],toggle,row=2,primary=shift in selected_shifts)
                expected=snapshot(qid)
                for remove,label in ((False,'Save repeating days'),(True,'Release selected days')):
                    async def review(i,remove=remove):
                        if not await self.interaction_check(i):return
                        async def confirm(event):
                            if not await self.interaction_check(event):return
                            await event.response.defer()
                            async with ui.mutation_lock:notice=save(event.user.id,qid,days,selected_shifts,expected,remove)
                            await w.present(event,view(),notice)
                        text=(', '.join(labels[d] for d in days)+' · '+', '.join(s.upper() for s in selected_shifts)+' · only when home. '
                              +('Release only your selected repeating slots.' if remove else 'Reserve these days each week; other occurrences stay available. No points are awarded.'))
                        await w.present(i,w.Confirm(actor,'Release repeating days?' if remove else 'Save repeating days?',text,confirm,view))
                    self.button(label,review,row=3,primary=not remove,disabled=not days or not selected_shifts)
                self.nav(lambda:w.Card(actor,qid,guild=guild))
        return Repeating

    return SimpleNamespace(slots=slots,shifts=shifts,owner=owner,reserved=reserved,save=save,snapshot=snapshot,in_week=in_week,occurrences=occurrences,install_views=install_views)
