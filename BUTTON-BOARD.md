# Sprig workspace implementation and deployment

The current household interface is documented in **USER-GUIDE.md**. It replaces the accumulated historical development notes that described contradictory stages of the interface.

## Automatic daily database backups

The server runs `/home/discordbot/sprig-db-backup.py` with `/usr/bin/python3`, independently of the Discord bot and its virtual environment. It uses SQLite’s online backup API, so committed WAL changes are included while Sprig is running, and verifies integrity before publishing a snapshot. The destination is `/home/discordbot/sprig-backups/daily/YYYY-MM-DD/sprig.db`, with a SHA-256/count/integrity manifest beside it. Snapshots are kept; no automatic deletion is configured.

The discordbot crontab checks at minute 15 of each hour and at reboot. The script gates execution to 03:15 or later in America/New_York and makes only one snapshot per Eastern date, handling DST and catch-up after downtime. An exclusive lock prevents overlaps. Existing daily files are never overwritten. If a completed database lacks a manifest after an interrupted run, a verified manifest can be recovered without copying again. Existing hash mismatches fail visibly and preserve files. Output goes to `/home/discordbot/sprig-backups/daily/backup.log`.

Configured and tested on October 20, 2026. Seven Linux integration tests passed, including WAL copying, missing/corrupt sources, repeated execution, lock contention, and Eastern/DST scheduling. Today’s real snapshot was independently restored to a temporary database and passed integrity/count checks. The next scheduled overnight execution remains a future run, not a verified completed run.

Repository sources are `backup_database.py` and `test_backup_database.py`. This standalone helper is separate from the seven bot runtime modules. The installed server copy is outside the checkout, so routine bot pulls do not change it. Changes to the backup helper require a deliberate tested install of that file. Run its Linux tests with `python3 test_backup_database.py -q`. Run a current-day backup/check with `/usr/bin/python3 /home/discordbot/sprig-db-backup.py`; an existing valid snapshot is left untouched. Inspect `crontab -l` to confirm schedule entries.

Restore is a separate deliberate maintenance action: stop Sprig, preserve the current database, verify the selected snapshot/manifest, then restore and test before starting. Never copy over a running production database.

## Runtime files

Deploy all seven modules together:

- sprig_bot.py. Discord bot, shared command mutations, and service entry point.
- chore_board.py. Existing chore rules, specialized forms, permissions, and persistent panel registration.
- chore_timing.py. Recurrence, day markers, missed-work policy, and readiness.
- household_availability.py. Base rotation and dated attendance exceptions.
- chore_history.py. Append-only completion ledger and atomic conservative Undo.
- chore_planning.py. Personal opt-in reminders, estimates, occurrence checklists, and private calendar previews.
- chore_recovery.py. Durable owner/guild-bound navigation, expired-control recovery, and stale-action guards.
- chore_workspace.py. Private dashboards, searchable lists, common chore cards, trip editor, and owner review queue.

Dependencies remain discord.py 2.6 or newer below 3, python-dotenv, and tzdata. Configuration and the Discord token stay in the existing server environment; never put credentials into this guide or version control.

## Separate morning and evening responsibilities

Schedules `daily-am` and `daily-pm` are independent daily chores with midnight/noon Eastern readiness and separate weekly sign-ups. The chore-card confirmation splits a twice-daily chore transactionally: the original ID and reservations stay on AM; the new PM ID copies details and starts open unless carrying a current single PM claim. Existing completion records and user points are unchanged. Current-day completion state is retained to prevent duplicate awards. `chore_shift_splits` makes repeat conversion idempotent. Existing occurrence moves must be canceled before splitting. No live chore is converted merely by deploying this feature.

Validation: 186 tests pass, including independent owners/completions, boundary times, preserved reservations/points, repeated conversion, and transaction rollback.

## Owner-only score resets

Points & standings exposes Reset points only to ginaria (the configured OWNER account). One-account selection or Everyone leads to confirmation with affected account count, point total, and explicit streak policy. Keeping streaks is the default; clearing streaks also clears users.last_completed. Confirmation rechecks owner, household context, and the full affected score snapshot under the mutation lock. Reset audit rows and score updates commit together. No completion records or chore responsibilities are changed. History snapshots include a per-user reset epoch, so an earlier completion cannot be undone across a reset even if the numeric total later matches again. Older snapshots default to epoch zero for compatibility. Reset audit is retained in points_reset_log. Each confirmed reset also stores an atomic points_reset_batches record with affected users, before/after scores and streaks, per-user reset epochs, and completion watermarks. Owner-only reset history can undo one batch after confirmation if every affected account still matches. Restoration writes a new reset audit row, marks the batch undone, and records the owner action in the same transaction. Older completion snapshots remain blocked across reset recovery.

Completion history offers ginaria confirmed correction of another person’s completion using the existing conservative latest-completion checks. The original person receives the reversal; owner_action_log records the actor and before/after state transactionally. The owner inbox offers Open and Resolved views; Reopen confirms, updates only a still-resolved review, and records the action without sending another DM. Every recovery mutation checks actual owner identity and household context before acquiring the lock. Database failures roll back the mutation and its audit together.

## Planning, checklists, reminders, and calendar

chore_planning.install runs after history and workspace setup. Its planning tables retain plan definitions, monotonic checklist revisions, per-occurrence checks, personal reminder settings, and delivery deduplication. Checklist cycle keys follow recurrence state, not the calendar date, so Keep overdue preserves unfinished work. Changed definitions start a new revision; estimate-only edits preserve checks. Every Done entry point uses the same backend checklist requirement before awarding points. History snapshots include planning state; an eligible Undo restores the old occurrence key and its saved progress.

The existing one-minute reset loop dispatches reminders after readiness resets, and catches dispatch errors without stopping recurrence processing. Reminder delivery is off by default, requires personal opt-in, and filters current owner/readiness/availability. A durable user/date/time delivery claim precedes network I/O; opt-in and ownership are checked again before sending. Failed/uncertain attempts are not retried. DST nonexistent times are skipped and repeated times share one delivery key. No reminder backfill older than 15 minutes. Offline tests mock all Discord delivery.

Calendar week/month/day views reuse recurrence matching and stored dated moves, with per-date weekly reservation projection and ongoing-assignment precedence. They are private schedule previews, not historical ownership reconstruction or external calendar sync. Flexible work is listed separately. Sunday uses pre-6-p.m. ownership. Future day selection cannot complete a future occurrence; current controls are opened explicitly.

## Help statuses and duplication

The planning module also maintains chore_help (append-only notes with resolution metadata) and chore_copies (stable submission keys for idempotent copying). Help status uses a recurrence-only key, independent of checklist revisions. Only the current responsible person can create/update a status on a due unfinished occurrence; any household member can confirm resolution through their own private controls. Status changes do not award points, complete work, release responsibility, or send DMs. Reassignment and occurrence moves preserve help; completion/Skip advances the active occurrence, while eligible completion Undo exposes its old unresolved note again. Earlier notes remain readable in Status history.

Duplicate chore snapshots source settings and metadata, validates the new name against active and archived names, and confirms before an atomic insert. It copies recurrence, point value, instructions, room/difficulty, estimate, checklist definitions, and missed-work policy; all ownership, history, progress, status notes, and occurrence moves start fresh. A durable submission key maps retries to the original new ID, including after an uncertain response. Checklist/recurrence/copy-key insert failures roll back together.

## Components V2 layout

Private lists use LayoutView, TextDisplay, and Section accessory buttons. Eligible current owned occurrences have inline Done buttons; other rows have Details. Five entries per page keep nested components below Discord limits. Completion captures the displayed occurrence snapshot and rechecks it after acquiring the mutation lock, preserving points/history and blocking repeated or stale clicks. Away, upcoming, next-week, and other people’s work cannot be completed through the row button.

Once a message uses Components V2, every destination on it is also rendered as V2, including existing editors and modal results. Edits explicitly clear legacy content, embeds, and attachments. Existing per-user/server/channel checks remain in force. Shared launcher entries send V2 controls ephemerally; no public chores list is introduced. Initial /chores dashboard remains compatible and upgrades to V2 on navigation. No saved-panel refresh is required for this layout-only update.

## Entry points and navigation

/chores opens a private personal dashboard. !chores opens a public starter; subsequent buttons are private. The saved public launcher has six neutral destinations: My chores, Pick up chores, Household, Who’s home?, Manage chores, and Help. Owner/admin tools are shown on the personal dashboard according to account identity and permissions.

The dashboard includes incoming trade counts and personal points/streaks. Browse, search, filter, card, confirmation, and specialized editor navigation replace the current private message. Validation errors may be separate private responses. Action callbacks expire after ten minutes or a restart; persistent recovery routing refreshes the saved view rather than replaying an expired action. Existing public messages are not automatically deleted.

Everyone with access to the configured chores channel and its history can manage routine chores and attendance. Specialized controls retain opener ownership and server/channel checks. Household setup requires Manage Server. Review resolution requires ginaria, account 301104023405199361.

## Data preservation and migrations

New tables are created additively. No existing chore or point total is rewritten merely by starting this release. Existing weekly reservations, claims, attendance exceptions, feedback, and archived records remain.

completion_log records each new award in the same transaction as its chore completion and user point/streak update. It stores before/after states and an undone marker. Earlier individual completions cannot be reconstructed. Undo checks the acting account, most recent un-undone user completion, current week/ownership, chore state, user totals, timing, missed policy, and occurrence move. It restores them together or rejects without partial reversal.

occurrence_moves holds a single moved unfinished occurrence without replacing the regular cadence. Completion clears the move; a regular schedule edit clears it too. A moved skipped occurrence gets an adjusted expiry. Canceling a move restores normal timing. The week’s ownership is not silently extended.

Multi-person date changes validate every person before a single transaction. Editing an exception deactivates the old version and inserts its replacement; cancellation is also retained as inactive history. Duplicate exact trips do not create additional records. Overlaps and stale edits are rejected.

The optional room uses the existing category field. It defaults to general; existing categories are preserved unless explicitly edited. Search covers names and instructions. Filters cover person, room, date, and unclaimed work. In-process per-area preferences remain available, and a durable per-person/guild last-place bookmark supports Continue where I left off after restart. Per-message recovery tokens retain the exact saved page/filter/card/calendar context for that screen.

## Notifications and owner review

New feedback is privately sent to ginaria and always saved first. The owner inbox shows reviews directly, with Resolve and next and contextual editing. Only ginaria resolves; household members can still contribute and read individual chore reviews. Reviewed records are retained. Suggestions never apply themselves.

Trade DMs are off by default. Each recipient can opt in through their own Notifications screen. Incoming trades remain visible without DMs. Delivery is bounded to ten seconds and recorded before attempting it; failed/uncertain attempts are not automatically retried. Old feedback and trades do not generate a startup notification backlog.

## Legacy compatibility

Claim, unclaim, and done retain the shared chore rules. Add/edit use shared validation. !deletequest now archives instead of hard-deleting; !resetquest opens the safe correction path without reopening or re-awarding. !help starts with /chores and keeps command-specific help for older workflows.

Old saved public panel buttons must be refreshed after deployment. The persistent launcher keeps established IDs for its remaining destinations; fresh /chores workspaces use the new interface immediately.

## Verify and deploy

1. Run the full offline release suite: `python run_tests.py --suite full --profile --report ../sprig-release-tests.json`. It uses isolated temporary databases, a dummy token, and mocked Discord delivery. Keep the passing exact-source report for the server check; see [TESTING.md](TESTING.md). Do not start a second real bot.
2. Compile all eight modules with `python -m py_compile sprig_bot.py chore_board.py chore_timing.py household_availability.py chore_history.py chore_workspace.py chore_planning.py chore_recovery.py`.
3. Obtain approval for the exact commit, SignalPocket identity, main branch push, and deployment. These steps are separate from local preparation.
4. Stop the existing sprig service interactively and verify inactive.
5. Back up the entire server checkout and database, record the previous commit, and verify the backup database integrity before updating.
6. Fetch and fast-forward only to the exact approved commit. Preserve the existing database, environment, and untracked historical backup.
7. Install the approved requirements in the existing virtual environment (`.venv/bin/python -m pip install -r requirements.txt`); Components V2 requires discord.py >=2.6,<3. Run `python run_tests.py --suite server --release-report /home/discordbot/sprig-release-tests.json --profile` using the server virtual environment while the service remains stopped. This compiles all eight modules and runs 24 installation checks, gated by the passing full local report. For major dependency, Python, migration, or deployment changes, also run the full suite on the server. See [TESTING.md](TESTING.md) for report transfer and failure handling.
8. Start the existing sprig service interactively; verify active/running and normal startup logs.
9. Reopen /chores. An administrator runs !refreshchoreboard once to edit the existing saved launcher rather than posting another one. No slash re-registration is needed for this upgrade.
10. Check real Discord layout on desktop/mobile and with two household accounts: future work, one claim/Done/Undo, weekly reservation, trip preview/edit, owner inbox access, and notification opt-in. Live rendering and notification delivery are not proven by offline tests.

The first-ever installation uses !choreboard once in the intended channel, then !enableprivatechores for explicit guild slash registration. Repeated setup reuses the existing panel. A pending/uncertain post must be inspected before retrying to avoid duplicates.

## Regression coverage

The suite covers existing scheduling, points, claims, weekly reservations, date exceptions, stale actions, archive/restore, and access boundaries. Redesign coverage adds personal upcoming views, actionable household cards, common navigation, search/filters, owner-only resolution, transaction rollback on history-write failure, safe Undo, multi-person trip atomicity, edited exception history, occurrence moves, opt-in notification deduplication, and Discord message/component limits.

Local preparation, pushed code, installed code, a running service, and verified live Discord behavior are distinct states. Record the actual state in the deployment manual.


## Personal list polish and button-based scores
My chores shows the caller’s points total at the top and uses Completed for the history tab. Due-now rows omit the repeated caller name/status while retaining twice-daily slot and coverage information. Other household views retain owner/status context. Dashboard → Points & standings opens a private V2 score view with caller total/streak, paged household rankings, shared ranks for ties, Refresh, and Dashboard. Reading scores does not create users or change points.


## Laptop backup and failure-alert tools

See [BACKUP-RECOVERY.md](BACKUP-RECOVERY.md) for the installed server/laptop schedules, protected storage, verification, private ginaria alerts, restore commands, limitations, and tests. `backup_monitor.py` runs independently of the bot; `laptop_backup.py` downloads over SSH and encrypts with Windows CurrentUser DPAPI. `install_laptop_backup.ps1` and `run_laptop_backup.ps1` set up the hidden per-user Windows task. These tools do not modify chore records or require a bot restart. Tests: `python -m unittest test_backup_transport -q`, plus `test_backup_database` on Linux. Do not put credentials, snapshots, or local monitor state in Git.


## Expired and outdated private controls

Every V2 workspace screen includes Refresh / Resume. Persistent dynamic routing recognizes owner/guild-bound opaque session tokens even after the old view times out or the bot restarts. A recovery click rebuilds navigation from SQLite workspace_sessions/workspace_places, then presents fresh controls; it never replays an old mutation or confirmation. /chores opens the same V2 layout and includes Continue where I left off when a saved location exists. The public !chores starter remains a persistent launcher that opens private controls.

Bookmarks retain list tabs/pages/search/person/room/date/group filters, chore IDs and parent return paths, calendar dates/month/week/personal scope and page, checklists, points/history pages, trips, owner review inbox, reminders, and help topics. Lists clamp to the nearest available page if rows disappear. Specialized editors/confirmations return to their safe parent or dashboard, not an old executable confirmation; unsaved modal text is not restored. Screens predating this release have no recovery tokens: reopen /chores once after deployment.

For active controls, a current household-state fingerprint rejects stale mutating actions and presents the same location with an explanatory notice. Ordinary page/date/dashboard navigation and opening a checklist can still render current data in one click. Backend ownership, availability, occurrence snapshots, mutation locks, completion deduplication, and owner-only checks remain intact. Fingerprints ignore navigation and delivery bookkeeping. A shared interaction-ID claim prevents discord.py's dynamic and static dispatch paths from running the same action twice. Every route rechecks the caller and household channel access. No background polling, channel posts, or test DMs are added.

Recovery metadata is navigation state, not chore history. UI read-only tests exclude only workspace metadata while continuing to compare all household data. Regression tests exercise the real discord.py ViewStore dispatcher and serialized V2 messages, restart recovery with no old view registered, select values, stale/expired Done, owner reset confirmations, filters/pages and calendar return paths, cross-person/guild/access rejection, shortened lists, duplicate dispatch, and message limits. Deploy chore_recovery.py with the other seven runtime modules; no new dependency or slash-command re-registration is needed. Live behavior remains unverified until the approved release is deployed and reopened in Discord.

## Needs attention

The private dashboard combines overdue, due unclaimed, and blocked work under **Needs attention**. Counts may overlap; each chore appears once with all applicable labels, its current owner, schedule, points, and any active help note. Open its chore card for existing actions. Pages, Back, and expiry/restart recovery preserve your place.

Overdue begins at the end of a scheduled day, AM/PM slot, week, or month. Moved dates use the moved day end. Flexible work without a stored occurrence date starts tracking at the first attention check; historical missed dates are not inferred. `attention_windows` persists those period ends without changing responsibility, completion history, or points.

## Simultaneous actions audit (#9)

The single bot process serializes button mutations with the shared asyncio mutation lock. Successful claim/completion command callbacks buffer their replies, so no Discord network wait occurs inside their database mutation. Claims and weekly sign-ups have unique keys; points, streaks, completion state, and history save in one SQLite transaction. Trades exchange both sides in one transaction.

Chore snapshots now include a durable `chore_revisions` counter. SQLite triggers increment it transactionally for actual quest, claim, weekly ownership, timing, missed-policy, occurrence-move, and archive changes. No-op normalization updates do not increment it, and a rollback also rolls back its counter changes. Returning a chore to earlier values cannot revive an old button or stored trade. Weekly sign-up/release callbacks now compare their saved snapshot inside the mutation lock after reset. Old pending trade snapshots from before this release fail conservatively and require a fresh proposal; history and earned points are preserved.

Regression coverage queues actual callbacks behind the production lock in both orders: competing occurrence/week claims, inline/card Done, different chore awards, Done versus Drop/Reassign/Trade/day changes, trade acceptance versus cancellation, and response loss after a saved completion. It also covers completion/undo and ownership/schedule round trips, old Release against a new reservation, persistent counters/no-op updates, and rollback of points/history/ownership/counters. Tests use temporary SQLite databases and mocked Discord delivery. This does not claim support for multiple bot processes writing the same database.

## Reminder accuracy audit (#10)

The dispatcher now rebuilds the entire due-chores query after recipient lookup, rather than filtering an earlier list. It runs resets again and reads current names, ownership, schedules, moved dates, archive state, estimates, and checklist progress. It rechecks account preference revision, current availability, canonical household location, the 15-minute window, and Sunday handoff immediately before message handoff. Slow earlier recipients cannot make later recipients use a stale batch clock.

The existing unique account/date/time delivery key still commits before network I/O. Empty and away slots are now persisted as skipped so later claims or ownership changes cannot backfill them. Prior-week slots are skipped after the household handoff. Canceled, skipped, sent, and uncertain attempts are not replayed; private reminder controls explain the new skipped outcomes. There is no network await between final validation and the send call. Changes after that handoff cannot recall a message Discord is already processing. No per-chore reminder scheduling is introduced (#12 remains later).

Tests cover completion, Drop, Reassign, accepted trades, archive/restore, moved and chosen dates, AM/PM resets, Keep versus Skip, alternating person/chore weeks, trip overrides, Sunday ownership, preference changes, opt-in, concurrency and deduplication, lookup delays, stale names, skipped slots, and existing DST/failure behavior using temporary databases and mocked delivery. No real test DMs or production preference changes are needed.

A moved weekly or monthly occurrence that is skipped waits until its next regular period before becoming due again. The saved next-period date survives restart and changes between Keep and Skip. A late check after that regular period has already begun does not skip the current period. Points, assignments, and completion history are preserved.

## Claim directly from Pick up chores

Due, unclaimed chores in **Pick up chores** have a **Claim** button beside each row. This takes just the current occurrence and keeps you in the same filtered list; it does not complete the chore, check steps, award points, or reserve a whole week. The list refreshes and adjusts the page if needed. For weekly or ongoing responsibility, open the chore card. Future work and Next week keep Details so you can review the appropriate sign-up. Claims are disabled while away, and competing or stale clicks cannot overwrite another person’s responsibility. Expired controls refresh first without claiming.


### Calendar starts with today

Calendar on the Dashboard opens today’s dated chores in Eastern time. Use Previous day, Today, or Next day to change dates, or Week and Month to see the broader schedule. Existing saved screens still resume their selected date and page.


## Update announcement

If ginaria enables automatic announcements, a new installed Git commit posts
once after startup in the configured household chores channel: **Sprig has been updated. Open /chores for
fresh controls.** There are no mentions or mass pings. Open /chores again to get
the updated controls; existing chores, assignments, points, and history remain.

Restarts and Discord reconnects on the same release do not post again. A saved
per-release delivery claim prevents duplicate announcements, including concurrent
ready events. If delivery is uncertain, it is logged without automatic retry.
Missing Git/version information or an unconfigured board produces no notice.
Channel lookup must match the saved household and channel, and a changed
destination cancels the attempt. Announcement failure does not stop the bot.
Offline tests mock channel delivery; deploying the code does not itself post a
notice until Sprig starts with the approved feature installed.


### Claim and Details together

In Pick up chores, each due, available chore has **Claim** and **Details** side by
side beneath its description. Claim takes the current occurrence immediately;
Details opens instructions, schedule, weekly sign-ups, and other actions without
claiming it. Back returns to the same filtered page. Future/next-week work keeps
Details without an early Claim, and away people can still read Details while
Claim is disabled. The footer uses Refresh / Resume instead of a second Refresh
button. All controls and replies stay private.


## Owner announcement choices and horizontal pickup card

Ginaria opens **Dashboard → Update announcements**. Automatic announcements
default **Off**, including when upgrading from the earlier always-automatic
release. This gives a quiet restart until the owner deliberately enables them.
The switch persists across restarts. Turning it on applies to future starts; it
does not post immediately. Turning it off during preparation cancels that
automatic attempt before sending.

**Announce this update** works even while automatic announcements are off. It
shows the exact message and destination, then requires Confirm. Cancel posts
nothing. Owner checks apply again at confirmation, and changed destinations or
expired screens require fresh review. There is still at most one attempt per
release: already posted or uncertain notices cannot be reposted by the button.
No pings or new personal DMs are added.

Pick up chores now uses a framed Components V2 card. Chore name and schedule run
across one text line where they fit, followed by Claim and Details together.
Due-now pickup rows omit redundant Needs someone / Due now labels while keeping
AM/PM slots, estimates, help notes, and away warnings. Other dates retain their
status. Details replaces the redundant card picker in this view. Discord controls
the actual displayed width and wrapping; the bot cannot set a pixel width or
force full-window columns. This layout needs a real Discord visual check after
deployment; serialized-component tests do not prove that it looks wider.


### Fixed pagination controls

Paged workspace lists always show Previous on the left and Next on the right,
in the same pagination row. Previous is greyed out on the first page; Next is
greyed out on the last. Both are greyed out for a single-page or empty list.
Disabled buttons do nothing and never change chores or jump pages. Calendar day
lists use Previous page / Next page; moving to another day remains separate.


### Consistent pickup rows

The wider framed card keeps each chore name on its own line, with schedule,
points, and relevant due status below. Every chore has the same Claim / Details
button row. Claim is greyed out and does nothing for future, next-week, completed,
or otherwise unavailable work; Details still opens the correct chore and week.
Pickup rows do not repeat Needs someone. This week still distinguishes Due now
from future dates. Paging controls retain their fixed positions.


## Pickup list: Details on the right

Each chore now has one Details button to the right of its text. Open Details
for instructions, Just this time, weekly sign-ups, and other chore actions.
Opening Details never claims or completes the chore. The wider frame, separate
name/schedule lines, saved filters, and fixed Previous/Next controls remain.
There is no inline Claim button in the pickup list. My chores keeps its inline
Done or Checklist buttons. Earlier paired-button notes describe the previous UI.


### Pickup list footer

Below the chore card: Previous / Next, then Due now / This week / Next week /
All chores, then Search / Filters / Refresh / Dashboard. Refresh is the single
recovery control: it reloads current information and keeps your place after
expiry or restart. There is no separate Refresh / Resume row in Pick up chores.
The footer shows the page number and Eastern time; week ranges remain in the
weekly view heading. Other screens retain their existing recovery controls.
