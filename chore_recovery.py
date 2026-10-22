"""Durable, owner-bound navigation; expired controls never replay old actions."""
import asyncio
from datetime import date
import hashlib
import json
import secrets
from time import monotonic
from types import SimpleNamespace
import discord


def install(ns, ui, w):
    db, bot = ns['db'], ns['bot']
    db.executescript('''
    CREATE TABLE IF NOT EXISTS workspace_sessions(
        token TEXT PRIMARY KEY,owner TEXT NOT NULL,guild TEXT NOT NULL,bookmark TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workspace_places(
        owner TEXT NOT NULL,guild TEXT NOT NULL,bookmark TEXT NOT NULL,PRIMARY KEY(owner,guild));
    ''')
    db.commit()
    live, handled = {}, {}

    def guild_key():
        row = db.execute('SELECT guild_id FROM chore_board WHERE singleton=1').fetchone()
        return str(row[0]) if row else ''

    def bookmark(view, depth=0):
        if depth > 6:
            return {'screen': 'dashboard'}
        explicit = getattr(view, 'recovery_context', None)
        if explicit is not None:
            return json.loads(json.dumps(explicit))
        parent = getattr(view, 'recovery_parent', None)
        if parent:
            return bookmark(parent(), depth+1)
        return {'screen': 'dashboard'}

    def latest(owner):
        row = db.execute('SELECT bookmark FROM workspace_places WHERE owner=? AND guild=?',
            (str(owner), guild_key())).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except (ValueError, TypeError):
            return None

    def fingerprint():
        # Navigation writes and delivery bookkeeping must not invalidate chore screens.
        digest = hashlib.sha256()
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for name, in tables:
            if name.startswith('workspace_') or name in ('reminder_deliveries', 'trade_notifications', 'feedback_notifications', 'update_announcements', 'announcement_settings'):
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            rows = db.execute('SELECT * FROM '+quoted+' ORDER BY rowid').fetchall()
            digest.update(json.dumps([name, rows], default=str, separators=(',', ':')).encode())
        digest.update((ui.week_key()+'|'+ui.timing.now().date().isoformat()+'|'+str(ui.timing.now().hour//12)).encode())
        return digest.hexdigest()

    def restore(owner, context, guild, depth=0):
        if depth > 6:
            return w.Dashboard(owner, guild)
        kind = context.get('screen')
        parent_context = context.get('parent', {'screen': 'dashboard'})
        parent = lambda: restore(owner, parent_context, guild, depth+1)
        if kind=='page_help':return w.PageHelp(owner,name=context.get('name','Chores'),topic=context.get('topic','Start here'),parent=parent_context,guild=guild,instructions=context.get('instructions'))
        if kind=='occurrence_dates':return w.OccurrenceDates(owner,int(context['qid']),guild,week=context.get('week',0),page=context.get('page',0))
        if kind=='future_slots':return w.FutureSlots(owner,int(context['qid']),date.fromisoformat(context['day']),guild,parent)
        if kind=='future_occurrence':return w.FutureOccurrence(owner,int(context['qid']),date.fromisoformat(context['day']),context['slot'],guild,parent)
        if kind == 'repeating_signup':
            return w.Repeating(owner,int(context['qid']),guild,cells=context.get('cells'))
        if kind == 'usual_schedule':
            return w.UsualSchedule(owner,context.get('people',[]),guild,context.get('mode'),context.get('days',[]),roster_page=context.get('roster_page',0))
        if kind == 'insights_help':
            return ui.insights.methods(owner,guild,context.get('days',28),context.get('page',0),context.get('order','planned'))
        if kind == 'insights':
            return ui.insights.Report(owner,guild,context.get('days',28),context.get('page',0),context.get('order','planned'))
        if kind == 'list_length':
            return w.ListLength(owner)
        if kind == 'announcements':
            return w.Announcements(owner,guild)
        if kind == 'browse':
            state=dict(context['state'])
            state['page']=state.get('page',0)*context.get('list_size',w.browse_page_size(owner,state.get('area','mine')))//w.browse_page_size(owner,state.get('area','mine'))
            return w.Browse(owner, guild=guild, **state)
        if kind == 'card':
            return w.Card(owner, int(context['qid']), parent, guild, int(context.get('offset', 0)))
        if kind == 'calendar':
            return ui.planning.Calendar(owner, guild, date.fromisoformat(context['day']), context['mode'], context['mine'])
        if kind == 'day':
            return ui.planning.Day(owner, date.fromisoformat(context['day']), context['mine'], guild,
                context['page']*context.get('list_size',w.page_size(owner))//w.page_size(owner), context['flexible'], context['mode'])
        if kind == 'checklist':
            return ui.planning.Checklist(owner, int(context['qid']), guild, parent)
        if kind == 'points':
            return w.Points(owner, guild, context.get('page', 0))
        if kind == 'history':
            return w.History(owner, int(context['qid']), parent, context.get('page', 0))
        if kind == 'trips':
            return w.Trips(owner,guild,context.get('people',[]),context.get('page',0),context.get('roster_page',0))
        if kind == 'inbox':
            return w.Inbox(owner, guild, context.get('page', 0), context.get('resolved', False))
        if kind == 'guide':
            return w.Guide(owner, context['topic'])
        if kind == 'manage':
            page=context.get('page',0)*context.get('list_size',w.page_size(owner))//w.page_size(owner)
            return w.Manage(owner,guild,page,context.get('query',''))
        if kind == 'reminders':
            return ui.planning.Reminders(owner)
        if kind == 'attention':
            return w.Attention(owner, guild, context.get('page', 0))
        if kind == 'needs_help':
            return ui.planning.NeedsHelp(owner, guild, context.get('page', 0))
        return w.Dashboard(owner, guild)

    async def open_saved(i, context, notice='Updated with current information. Your place is kept.'):
        try:
            view = restore(i.user.id, context, i.guild)
        except (KeyError, ValueError, TypeError):
            view = w.Dashboard(i.user.id, i.guild)
            notice = 'That saved view is no longer available. Your dashboard is ready; no action was taken.'
        if isinstance(view, w.Browse) and context.get('screen') == 'browse' and view.state['page'] != context['state']['page']:
            notice += ' The list is shorter now, so this is the nearest available page.'
        await w.present(i, view, notice)

    async def resume_latest(i):
        if not ui.allowed(i):
            await i.response.send_message('Open /chores in your household server.', ephemeral=True)
            return
        await open_saved(i, latest(i.user.id) or {'screen': 'dashboard'})

    async def route(i, token, action):
        row = db.execute('SELECT owner,guild,bookmark FROM workspace_sessions WHERE token=?', (token,)).fetchone()
        if not row or row[0] != str(i.user.id) or row[1] != str(i.guild_id) or not ui.allowed(i):
            await i.response.send_message('These controls belong to a different or unavailable workspace. Open your own /chores.', ephemeral=True)
            return
        now = monotonic()
        # discord.py can dispatch both a dynamic fallback and a live component.
        # Only one path may handle a real Discord interaction, including network retries.
        interaction_id = getattr(i, 'id', None)
        if interaction_id is not None:
            if interaction_id in handled:
                return
            handled[interaction_id] = now
        for key, stamp in list(handled.items()):
            if now-stamp > 900:
                handled.pop(key, None)
        entry = live.get(token)
        expired = not entry or now-entry['created'] >= 600 or entry['panel'].is_finished()
        if action == 'r' or expired:
            if expired:
                live.pop(token, None)
            return await open_saved(i, json.loads(row[2]),
                'This screen expired or Sprig restarted. Your place is restored with current information. Nothing was repeated.'
                if expired else 'Updated with current information. Your place is kept.')
        source = entry['source']
        if not await source.interaction_check(i):
            return
        pair = entry['controls'].get(action)
        if pair is None:
            return await open_saved(i, json.loads(row[2]), 'Those controls changed. Your place is restored; no action was taken.')
        item, callback = pair
        navigation = {'Previous', 'Next', 'Previous page', 'Next page', 'Previous day', 'Next day',
            'Today', 'Back', 'Dashboard', 'Refresh', 'Details', 'Checklist', 'Open chore',
            'Due now', 'This week', 'Next week', 'Upcoming', 'Completed', 'All chores',
            'Week', 'Month', 'My calendar', 'Household', 'No fixed day'}
        # Navigation renders current data itself. Changes elsewhere must not force
        # an extra click just to change page/date or open a fresh checklist.
        safe_navigation = getattr(item,'_sprig_navigation',False) or isinstance(source, w.Dashboard) or (
            isinstance(item, discord.ui.Button) and item.label in navigation)
        if not safe_navigation and fingerprint() != entry['fingerprint']:
            return await open_saved(i, json.loads(row[2]),
                'Chore information changed. This screen is refreshed in place; no action was taken. Review the current details before trying again.')
        data = getattr(i, 'data', None)
        if data is not None:
            item._refresh_state(i, data)
        await callback(i)

    class RecoveryControl(discord.ui.DynamicItem[discord.ui.Item], template=r'sprig:recover:v1:(?P<token>[a-f0-9]{32}):(?P<action>r|[0-9]+)'):
        @classmethod
        async def from_custom_id(cls, interaction, item, match):
            return cls(item)

        async def callback(self, interaction):
            match = self.template.fullmatch(self.custom_id)
            try:
                await route(interaction, match['token'], match['action'])
            except Exception as exc:
                source = live.get(match['token'], {}).get('source') or w.View(interaction.user.id)
                await source.on_error(interaction, exc, self.item)

    bot.add_dynamic_items(RecoveryControl)

    def attach(panel, source, resume_row=None, resume=None):
        now = monotonic()
        for key, value in list(live.items()):
            if now-value['created'] >= 600:
                live.pop(key, None)
        token = secrets.token_hex(16)
        context = bookmark(source)
        encoded = json.dumps(context, separators=(',', ':'))
        guild = guild_key()
        with db:
            db.execute('INSERT INTO workspace_sessions VALUES(?,?,?,?,?)',
                (token, str(source.owner), guild, encoded, ui.timing.now().isoformat()))
            if context['screen'] != 'dashboard':
                db.execute('INSERT OR REPLACE INTO workspace_places VALUES(?,?,?)', (str(source.owner), guild, encoded))
        controls = {}
        for index, item in enumerate(list(panel.walk_children())):
            if item is resume or not isinstance(item, (discord.ui.Button, discord.ui.Select, discord.ui.UserSelect)) or not item.is_dispatchable():
                continue
            action = str(index)
            callback = getattr(item, '_sprig_recovery_callback', item.callback)
            item._sprig_recovery_callback = callback
            controls[action] = (item, callback)
            item.custom_id = f'sprig:recover:v1:{token}:{action}'
            async def callback(i, action=action):
                await route(i, token, action)
            item.callback = callback
        supplied_resume=resume is not None
        resume=resume or discord.ui.Button(label='Refresh' if resume_row is not None else 'Refresh / Resume')
        resume.custom_id=f'sprig:recover:v1:{token}:r'
        async def refresh(i):
            await route(i, token, 'r')
        resume.callback = refresh
        if supplied_resume:
            pass  # The shared page template already budgeted and placed it.
        elif resume_row is None:
            panel.add_item(discord.ui.ActionRow(resume))
        else:
            # Existing controls have already been registered for recovery;
            # preserve those objects and IDs while keeping Home last.
            home=[item for item in resume_row.children if getattr(item,'label',None)=='Dashboard']
            for item in home:resume_row.remove_item(item)
            resume_row.add_item(resume)
            for item in home:resume_row.add_item(item)
        panel.recovery_token = token
        live[token] = dict(panel=panel, source=source, controls=controls, created=now, fingerprint=fingerprint())

    return SimpleNamespace(attach=attach, bookmark=bookmark, restore=restore, latest=latest,
        resume_latest=resume_latest, route=route, open_saved=open_saved, live=live, RecoveryControl=RecoveryControl,
        fingerprint=fingerprint)
