"""Read-only earned-point pace and forward responsibility budgets."""
import calendar
from datetime import datetime, timedelta
from types import SimpleNamespace

import discord
from chore_timing import DAILY_SHIFTS, SCHEDULED


def install(ns, ui, w):
    db, timing, zone = ns['db'], ui.timing, ns['QUEST_TIMEZONE']

    def local(value):
        when = datetime.fromisoformat(value)
        return when.replace(tzinfo=zone) if when.tzinfo is None else when.astimezone(zone)

    def midnight(day):
        return datetime.combine(day, datetime.min.time(), tzinfo=zone)

    def week_at(when):
        start = (when-timedelta(days=(when.weekday()+1) % 7)).replace(hour=18, minute=0, second=0, microsecond=0)
        return start if when >= start else start-timedelta(days=7)

    def calculate(days=28):
        if days not in (7, 28, 90):
            raise ValueError('Choose a 7, 28, or 90 day comparison.')
        now = timing.now()
        today = now.date()
        future_start, future_end = today+timedelta(days=1), today+timedelta(days=days+1)
        events = db.execute('SELECT user_id,points,completed_at,undone_at FROM completion_log').fetchall()
        dated = [(str(uid), points, local(stamp), undone) for uid, points, stamp, undone in events]
        first = min((stamp.date() for _, _, stamp, _ in dated if stamp <= now), default=None)
        past_start = max(today-timedelta(days=days), first) if first else today
        observed = max(0, (today-past_start).days)
        quests = db.execute('SELECT id,name,frequency,points,assigned_to,completed,last_completed,reset_after FROM quests').fetchall()
        archived = {r[0] for r in db.execute('SELECT quest_id FROM archived_chores')}
        signups = {(qid, week): str(uid) for qid, week, uid in db.execute('SELECT quest_id,week_start,user_id FROM week_signups')}
        claims = {qid: str(uid) for qid, uid in db.execute('SELECT quest_id,user_id FROM claims')}
        moves = {qid: datetime.fromisoformat(day).date() for qid, day in db.execute('SELECT quest_id,day FROM occurrence_moves')}
        starts = {qid: local(ready) for qid, ready in db.execute('SELECT quest_id,ready_from FROM chore_timing')}
        ids = {str(uid) for uid, in db.execute('SELECT id FROM users')}
        ids.update(str(q[4]) for q in quests if q[4])
        ids.update(claims.values()); ids.update(signups.values())
        ids.update(uid for uid, _, _, _ in dated)
        ids.update(str(uid) for uid, in db.execute('SELECT user_id FROM alternating_members'))
        ids.update(str(uid) for uid, in db.execute('SELECT user_id FROM availability_defaults'))
        ids.update(str(uid) for uid, in db.execute('SELECT DISTINCT user_id FROM availability_exceptions'))
        ids.update(str(uid) for uid, in db.execute('SELECT DISTINCT user_id FROM repeating_signups'))
        ids.update(str(uid) for uid, in db.execute("SELECT DISTINCT actor FROM dated_occurrences WHERE state='claim'"))
        ids.update(str(uid) for uid, in db.execute('SELECT user_id FROM household_profiles'))
        ids.update(str(uid) for uid, in db.execute('SELECT user_id FROM person_colors'))
        stats = {uid: dict(earned=0, today=0, planned=0.0, away=0.0, backlog=0, past_home=0.0, future_home=0.0) for uid in ids}
        home_cache = {}

        def at(uid, when):
            key = (uid, when.isoformat())
            if key not in home_cache:
                home_cache[key] = ui.attendance.at(uid, when)
            return home_cache[key]

        def home_days(uid, start, count):
            # All exceptions are full days; only the Sunday 18:00 handoff
            # changes within a day. Count its two wall-clock portions exactly.
            return sum((.75 if at(uid, midnight(start+timedelta(days=n)).replace(hour=9)) else 0)
                       + (.25 if at(uid, midnight(start+timedelta(days=n)).replace(hour=21)) else 0)
                       for n in range(count))

        for uid, value in stats.items():
            value['past_home'] = home_days(uid, past_start, observed)
            value['future_home'] = home_days(uid, future_start, days)
        for uid, points, stamp, undone in dated:
            if undone is not None or stamp > now:
                continue
            if past_start <= stamp.date() < today:
                stats[uid]['earned'] += points
            elif stamp.date() == today:
                stats[uid]['today'] += points

        def owner(q, when, single=False):
            return ui.dated.owner(q[0],when) or (str(q[4]) if q[4] else signups.get((q[0], week_at(when).date().isoformat())) or (claims.get(q[0]) if single else None) or ui.repeating.owner(q[0],when))

        unclaimed, unplaced, unclaimed_due = 0.0, 0, 0

        def add(q, when, amount, single=False):
            nonlocal unclaimed
            if ui.dated.skipped(q[0],when):return
            uid = owner(q, when, single)
            if uid is None:
                unclaimed += amount
            else:
                frequency=q[2]
                if frequency in ('daily','twice-daily',*DAILY_SHIFTS) or frequency in SCHEDULED or single:
                    end=when+timedelta(hours=12) if frequency in ('daily-am','twice-daily') else midnight(when.date()+timedelta(days=1))
                    home=ui.attendance.during(uid,when,end)
                else:home=at(uid,when)
                if home:stats[uid]['planned'] += amount

        for q in quests:
            qid, _, frequency, points, _, completed, _, reset = q
            if qid in archived:
                continue
            completed = bool(completed and (not reset or local(reset) > now))
            earliest = starts.get(qid, midnight(today-timedelta(days=366)))
            if completed and reset:
                earliest = max(earliest, local(reset))
            moved = moves.get(qid) if not completed else None
            due_start = max(earliest, midnight(moved)) if moved else earliest
            if not completed and due_start <= now and ui.ready(qid,initialize=False):
                uid = owner(q, now, True)
                if uid is None:unclaimed_due += points
                else:stats[uid]['backlog'] += points
            if frequency == 'one-time' and not completed and not moved:
                unplaced += points
            if moved:
                if future_start <= moved < future_end:
                    add(q, midnight(moved), points, True)
                if frequency == 'one-time':
                    continue
                # Assume completion as the moved day opens, then use the real
                # next boundary (including a remaining afternoon occurrence).
                resume = local(timing.calculate_reset(midnight(moved), frequency))
                earliest = max(earliest, resume)
            if frequency == 'one-time':
                continue
            for index in range(days):
                day = future_start+timedelta(days=index)
                start = midnight(day)
                if frequency in ('daily', 'twice-daily', *DAILY_SHIFTS):
                    hours = (0, 12) if frequency == 'twice-daily' else (12,) if frequency == 'daily-pm' else (0,)
                    for hour in hours:
                        when = start.replace(hour=hour)
                        if when >= earliest:add(q, when, points)
                elif frequency in SCHEDULED:
                    if start >= earliest and timing.matches(day, frequency):add(q, start, points)
                elif frequency == 'weekly':
                    # Flexible work has a budget, not an invented due weekday.
                    # Split Sunday at the household handoff for signup owners.
                    portions = ((9, .75), (21, .25)) if day.weekday() == 6 else ((12, 1),)
                    for hour, weight in portions:
                        when = start.replace(hour=hour)
                        if when >= earliest:add(q, when, points*weight/7)
                elif frequency == 'monthly':
                    when = start.replace(hour=12)
                    if when >= earliest:add(q, when, points/calendar.monthrange(day.year, day.month)[1])
        for value in stats.values():
            value['earned_daily'] = value['earned']/observed if observed else None
            value['planned_daily'] = value['planned']/days
            value['earned_home'] = value['earned']/value['past_home'] if value['past_home'] else None
            value['planned_home'] = value['planned']/value['future_home'] if value['future_home'] else None
        return dict(days=days, past_start=past_start, past_end=today, observed=observed,
                    future_start=future_start, future_end=future_end, people=stats,
                    unclaimed=unclaimed, unplaced=unplaced, unclaimed_due=unclaimed_due,
                    planned_total=unclaimed+sum(value['planned'] for value in stats.values()))

    def number(value):
        return '—' if value is None else f'{value:.1f}'.rstrip('0').rstrip('.')

    def rate(value, multiplier=1):
        return number(None if value is None else value*multiplier)

    async def show(i, owner, days=28, page=0, order='planned', detail=False):
        if not await w.View(owner).interaction_check(i):return
        if not i.response.is_done():await i.response.defer()
        await w.present(i, Report(owner, i.guild, days, page, order, detail))

    def methods(owner, guild, days=28, page=0, order='planned', detail=False):
        guide=w.Guide(owner,'Workload & pace')
        for item in list(guide.children):
            if isinstance(item,discord.ui.Button) and item.label=='Dashboard':guide.remove_item(item)
        guide.recovery_context={'screen':'insights_help','days':days,'page':page,'order':order,'detail':detail}
        guide.nav(lambda:Report(owner,guild,days,page,order,detail))
        return guide

    class Report(w.View):
        def __init__(self, owner, guild=None, days=28, page=0, order='planned', detail=False):
            super().__init__(owner)
            if order not in ('planned','earned','name'):order='planned'
            data = calculate(days)
            self.data = data
            size = w.page_size(owner)
            people = list(data['people'].items())
            people.sort(key=(lambda item: (-item[1]['planned'], item[0])) if order=='planned' else
                        (lambda item: (-item[1]['earned'], item[0])) if order=='earned' else
                        (lambda item: (w.person(item[0],guild).casefold(),item[0])))
            page = min(max(0,page),max(0,(len(people)-1)//size))
            self.recovery_context={'screen':'insights','days':days,'page':page,'order':order,'detail':detail}
            self.paging_labels=('Previous','Next')
            chunk=people[page*size:(page+1)*size]
            self.name_ids=[uid for uid,_ in chunk]
            self.rebuild=lambda:Report(owner,guild,days,page,order,detail)
            history=(f'{data["past_start"]:%b %d}–{data["past_end"]-timedelta(days=1):%b %d} · {data["observed"]} recorded day(s)'
                     if data['observed'] else 'No completed days of recorded history yet')
            self.embed=discord.Embed(title='Workload & pace',description=
                f'Plan: {data["future_start"]:%b %d}–{data["future_end"]-timedelta(days=1):%b %d} ({days} days).\n'
                'Recurring chores pause while someone is away. Saved responsibilities resume when home; missed away occurrences do not pile up.\n'
                f'Unclaimed due now: **{data["unclaimed_due"]} points**.\n'
                + (f'History: {history}. Today is separate.\nUnclaimed planned work: {number(data["unclaimed"])} points. Undated one-time work: {data["unplaced"]} points.' if detail else ''),
                color=0x6B9B77)
            for uid,value in chunk:
                text=(f'Due now: **{value["backlog"]} points**\n'
                      f'Completed today: **{value["today"]} points**\n'
                      f'Planned per week: **{rate(value["planned_daily"],7)} points**')
                if detail:
                    share=value['planned']/data['planned_total']*100 if data['planned_total'] else 0
                    text+=(f'\nCompleted per week (past): {rate(value["earned_daily"],7)} points'
                           f'\nPlanned total (next {days} days): {number(value["planned"])} points'
                           f'\nPer home-day — completed: {number(value["earned_home"])}; planned: {number(value["planned_home"])}'
                           f'\nShare of planned household points: {number(share)}%')
                self.embed.add_field(name=w.clean(w.person(uid,guild),100),value=text,inline=False)
            if not chunk:self.embed.add_field(name='No people recorded yet',value='People appear once they have chores, signups, completion history, or an alternating schedule.')
            self.embed.set_footer(text=f'Page {page+1} of {max(1,(len(people)-1)//size+1)} · {len(people)} people · Eastern time')
            picker=discord.ui.Select(placeholder=f'Compare past / next {days} days',options=[discord.SelectOption(label=f'Past / next {n} days',value=str(n),default=n==days) for n in (7,28,90)],row=0)
            async def choose(i):await show(i,owner,int(picker.values[0]),0,order,detail)
            picker.callback=choose;self.add_item(picker)
            self.button('Less detail' if detail else 'More detail',lambda i:show(i,owner,days,page,order,not detail),row=1)
            next_order={'planned':'earned','earned':'name','name':'planned'}[order]
            self.button('Sort: '+{'planned':'Planned load','earned':'Earned pace','name':'Name'}[order],lambda i:show(i,owner,days,0,next_order,detail),row=1)
            self.button('How this is calculated',lambda i:w.present(i,methods(owner,i.guild,days,page,order,detail)),row=1)
            if page:self.button('Previous',lambda i:show(i,owner,days,page-1,order,detail),row=2)
            if (page+1)*size<len(people):self.button('Next',lambda i:show(i,owner,days,page+1,order,detail),row=2)
            self.nav()

    return SimpleNamespace(Report=Report,calculate=calculate,show=show,methods=methods)
