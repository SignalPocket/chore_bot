# Sprig workspace implementation and deployment

## Button controls and repeating weekday signups

Each chore row has a **chore-name button**, **Claim / Done**, and **Skip**. Click the name to open instructions, checklist, estimate, responsibility, and actions. The colored day/period marker, AM/PM slot where relevant, and points appear on the name button. Taken work shows the responsible person; future rows offer Choose date for their one-time actions, while completed occurrences have disabled completion buttons. Previous and Next keep their fixed positions, and pages stay at five chores by default.

**Claim** immediately takes just the current occurrence and leaves its card open with Done available. **Responsibility → Signup options** on the card offers **This week**, **Next week**, and **Repeating weekdays / shifts**. Whole-week signups retain the existing Sunday 6 p.m. handoff. Common actions stay as buttons. Less-used responsibility and schedule/detail actions use named dropdowns; Help topics and list filters also use dropdowns. Longer option lists have Previous/Next; multi-choice screens use toggle buttons followed by **Apply selection**. **Find a person** can search the household server by the beginning of a Discord name or nickname, then display matching people as buttons. Text forms remain for names, instructions, dates, and feedback.

To take particular days: open a daily chore → **Sign-up schedule** (or **Signup options → Repeating weekdays / shifts**), use the weekday/shift grid, where your saved slots are already selected, then **Save repeating days** once. A daily task stays daily: Kas can take Mondays/Wednesdays, Zel Tuesdays/Thursdays, and other days remain open. A twice-daily chore can give AM and PM to different people. A separate Daily AM or Daily PM chore offers only its own shift. The recurring grid saves only when you press Save; toggling or leaving it changes nothing.

Repeating signups are **only when home**. Usual attendance defaults, alternating weeks, and dated home/away exceptions are checked for each occurrence and reminder. Away days pause that person’s responsibility; the saved repeating signup returns automatically when that person is home. Two people may share a weekday/shift when their home schedules do not overlap, such as opposite alternating weeks. Overlapping home responsibility is rejected when saving. If an attendance change later puts both people home for the same slot, Sprig leaves it unclaimed instead of choosing a winner: use an occurrence Claim/Reassign for coverage and adjust the signup or attendance.

Use **Sign-up schedule → unselect the slots to release → Save repeating days** to release your repeating slots. Other days and other people stay unchanged. **Skip** affects only the current occurrence, awards no points, and keeps the repeating signup. **Reassign** and accepted **Trade** change just the current occurrence when it comes from a repeating signup. Completed work, points, and history stay saved. Whole-week or ongoing assignments cannot override repeating days; release the conflicting responsibility first. Changing the regular repeat cadence requires releasing weekday signups first; splitting a twice-daily chore into separate AM/PM chores carries each shift's signups to the correct chore.

My chores, Pick up chores, Needs attention, household responsibility summaries, calendar and dated occurrences, reminders, and Workload & pace use the effective weekday/shift owner. Calendar previews show both AM and PM owners; uncovered and away slots remain available. Points still go only to the account that completes the work. Repeating signups are available for daily schedules; weekly/monthly/one-time chores retain their existing signup controls.


The current household interface is documented in **USER-GUIDE.md**. It replaces the accumulated historical development notes that described contradictory stages of the interface.

## Automatic daily database backups

The server runs `/home/discordbot/sprig-db-backup.py` with `/usr/bin/python3`, independently of the Discord bot and its virtual environment. It uses SQLite’s online backup API, so committed WAL changes are included while Sprig is running, and verifies integrity before publishing a snapshot. The destination is `/home/discordbot/sprig-backups/daily/YYYY-MM-DD/sprig.db`, with a SHA-256/count/integrity manifest beside it. Snapshots are kept; no automatic deletion is configured.

The discordbot crontab checks at minute 15 of each hour and at reboot. The script gates execution to 03:15 or later in America/New_York and makes only one snapshot per Eastern date, handling DST and catch-up after downtime. An exclusive lock prevents overlaps. Existing daily files are never overwritten. If a completed database lacks a manifest after an interrupted run, a verified manifest can be recovered without copying again. Existing hash mismatches fail visibly and preserve files. Output goes to `/home/discordbot/sprig-backups/daily/backup.log`.

Configured and tested on October 20, 2026. Seven Linux integration tests passed, including WAL copying, missing/corrupt sources, repeated execution, lock contention, and Eastern/DST scheduling. Today’s real snapshot was independently restored to a temporary database and passed integrity/count checks. The next scheduled overnight execution remains a future run, not a verified completed run.

Repository sources are `backup_database.py` and `test_backup_database.py`. This standalone helper is separate from the nine bot runtime modules. The installed server copy is outside the checkout, so routine bot pulls do not change it. Changes to the backup helper require a deliberate tested install of that file. Run its Linux tests with `python3 test_backup_database.py -q`. Run a current-day backup/check with `/usr/bin/python3 /home/discordbot/sprig-db-backup.py`; an existing valid snapshot is left untouched. Inspect `crontab -l` to confirm schedule entries.

Restore is a separate deliberate maintenance action: stop Sprig, preserve the current database, verify the selected snapshot/manifest, then restore and test before starting. Never copy over a running production database.

## Runtime files

Deploy all twelve runtime modules together:

- sprig_bot.py. Discord bot, shared command mutations, and service entry point.
- chore_board.py. Existing chore rules, specialized forms, permissions, and persistent panel registration.
- chore_timing.py. Recurrence, day markers, missed-work policy, and readiness.
- household_availability.py. Base rotation and dated attendance exceptions.
- chore_history.py. Append-only completion ledger and atomic conservative Undo.
- chore_planning.py. Personal opt-in reminders, estimates, occurrence checklists, and private calendar and dated occurrences.
- chore_recovery.py. Durable owner/guild-bound navigation, expired-control recovery, and stale-action guards.
- chore_pages.py. Reusable named page types, slot order, dropdown groups, and complete-layout validation.
- chore_workspace.py. Private dashboards, searchable lists, common chore cards, trip editor, and owner review queue.
- chore_insights.py. Read-only earned/projected points and attendance-normalized comparisons.
- dated_occurrences.py. Exact local-date/slot reservations, skips, history, and guarded Undo.
- repeating_signups.py. Weekday/shift signup records, home-only ownership, validation, history, and signup buttons.

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

Private lists use LayoutView, TextDisplay, Containers, and native button action rows. A chore-name button opens details; Claim/Done and Skip sit beside it. Calendar names are buttons too. Existing selector callbacks remain internal mutation handlers, while the wire UI renders button choices. Five chores per page stay within Discord component limits. Completion validates occurrence, ownership, home status, and checklist progress after taking the mutation lock. Repeated or stale actions cannot award points twice.

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

Before each new release, increment APP_VERSION in chore_board.py, update RELEASE_SUMMARY with one short sentence about changes since the previous release, update its announcement test and CHANGELOG.md, and run the full offline suite before obtaining approval for the exact commit and deployment. Use MAJOR.MINOR.PATCH: patch for fixes, minor for backward-compatible features, and major for breaking changes. Retrying or restarting the same release does not need another version bump. The largest change in the release determines the bump, not the number of commits or files.

- **x / major:** incompatible behavior, removed supported workflows, or a breaking migration that needs deliberate user action. Example: 1.3.2 → 2.0.0.
- **y / minor:** new capabilities that preserve existing records and supported workflows. Example: 1.2.1 → 1.3.0 for future dated claims/skips. A compatible schema addition alone does not make a release major.
- **z / patch:** bug fixes, color/layout polish, wording, documentation, and test-only maintenance. Example: 1.3.0 → 1.3.1.

A minor bump resets z to zero; a major bump resets y and z to zero. Bundle unreleased changes under one release version. Refresh its short announcement summary and CHANGELOG entry so they cover only changes since the previous release. Do not increment the version for a retry or a restart of the same installed release.

1. Run the full offline release suite: `python run_tests.py --suite full --profile --report ../sprig-release-tests.json`. It uses isolated temporary databases, a dummy token, and mocked Discord delivery. Keep the passing exact-source report for the server check; see [TESTING.md](TESTING.md). Do not start a second real bot.
2. Compile all nine modules with `python -m py_compile sprig_bot.py chore_board.py chore_timing.py household_availability.py chore_history.py chore_workspace.py chore_planning.py chore_recovery.py chore_insights.py`.
3. Obtain approval for the exact commit, SignalPocket identity, main branch push, and deployment. These steps are separate from local preparation.
4. Stop the existing sprig service interactively and verify inactive.
5. Back up the entire server checkout and database, record the previous commit, and verify the backup database integrity before updating.
6. Fetch and fast-forward only to the exact approved commit. Preserve the existing database, environment, and untracked historical backup.
7. Install the approved requirements in the existing virtual environment (`.venv/bin/python -m pip install -r requirements.txt`); Components V2 requires discord.py >=2.6,<3. Run `python run_tests.py --suite server --release-report /home/discordbot/sprig-release-tests.json --profile` using the server virtual environment while the service remains stopped. This compiles all nine modules and runs 28 installation checks, gated by the passing full local report. For major dependency, Python, migration, or deployment changes, also run the full suite on the server. See [TESTING.md](TESTING.md) for report transfer and failure handling.
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

Every V2 workspace screen includes Refresh. Persistent dynamic routing recognizes owner/guild-bound opaque session tokens even after the old view times out or the bot restarts. A recovery click rebuilds navigation from SQLite workspace_sessions/workspace_places, then presents fresh controls; it never replays an old mutation or confirmation. /chores opens the same V2 layout and includes Continue where I left off when a saved location exists. The public !chores starter remains a persistent launcher that opens private controls.

Bookmarks retain list tabs/pages/search/person/room/date/group filters, chore IDs and parent return paths, calendar dates/month/week/personal scope and page, checklists, points/history pages, trips, owner review inbox, reminders, and help topics. Lists clamp to the nearest available page if rows disappear. Specialized editors/confirmations return to their safe parent or dashboard, not an old executable confirmation; unsaved modal text is not restored. Screens predating this release have no recovery tokens: reopen /chores once after deployment.

For active controls, a current household-state fingerprint rejects stale mutating actions and presents the same location with an explanatory notice. Ordinary page/date/dashboard navigation and opening a checklist can still render current data in one click. Backend ownership, availability, occurrence snapshots, mutation locks, completion deduplication, and owner-only checks remain intact. Fingerprints ignore navigation and delivery bookkeeping. A shared interaction-ID claim prevents discord.py's dynamic and static dispatch paths from running the same action twice. Every route rechecks the caller and household channel access. No background polling, channel posts, or test DMs are added.

Recovery metadata is navigation state, not chore history. UI read-only tests exclude only workspace metadata while continuing to compare all household data. Regression tests exercise the real discord.py ViewStore dispatcher and serialized V2 messages, restart recovery with no old view registered, select values, stale/expired Done, owner reset confirmations, filters/pages and calendar return paths, cross-person/guild/access rejection, shortened lists, duplicate dispatch, and message limits. Deploy chore_recovery.py with the other eight runtime modules; no new dependency or slash-command re-registration is needed. Live behavior remains unverified until the approved release is deployed and reopened in Discord.

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

Press **Claim** beside a due unclaimed chore, then choose **Just this occurrence**, **This week**, **Next week**, or **Repeating weekdays / shifts** as available. Claiming awards no points and does not check checklist steps. Repeating days pause while away. Click the chore name for instructions without claiming it. Away and future occurrence action buttons are disabled; expired controls refresh without repeating an action.

### Calendar starts with today

Calendar on the Dashboard opens today’s dated chores in Eastern time. Use Previous day, Today, or Next day to change dates, or Week and Month to see the broader schedule. Existing saved screens still resume their selected date and page.


## Update announcement

If ginaria enables automatic announcements, a new installed Git commit posts
once after startup in the configured household chores channel: **Sprig has been updated to version 1.3.0. Open /chores for fresh controls.** A short “What’s new” sentence describes changes since the previous release, followed by the announcement date and time in Eastern time, including EDT or EST. This release is version **1.3.0**; the timestamp records when the notice is posted, including when the owner announces manually later. Each installed Git commit remains a separate update for duplicate prevention. There are no mentions or mass pings. Open /chores again to get
the updated controls; existing chores, assignments, points, and history remain.

Restarts and Discord reconnects on the same release do not post again. A saved
per-release delivery claim prevents duplicate announcements, including concurrent
ready events. If delivery is uncertain, it is logged without automatic retry.
Missing Git/version information or an unconfigured board produces no notice.
Channel lookup must match the saved household and channel, and a changed
destination cancels the attempt. Announcement failure does not stop the bot.
Offline tests mock channel delivery; deploying the code does not itself post a
notice until Sprig starts with the approved feature installed.


### Chore-name, Claim/Done, and Skip buttons

Each list row has a chore-name button, Claim/Done, and Skip. The name opens details without changing responsibility. Claim takes just this occurrence and opens its card; Signup options handles longer responsibility; Done opens an unfinished checklist or completes eligible work. Skip happens immediately and keeps future repeats and saved responsibilities. Undo skip appears at the bottom. Future/completed action buttons are disabled.

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

Pick up chores uses a Components V2 frame containing chore-name, Claim/Done, and Skip button rows. Discord controls the actual width; serialized tests verify validity and limits, while real appearance still needs a Discord check after deployment.


### Fixed pagination controls

Paged workspace lists always show Previous on the left and Next on the right,
in the same pagination row. Previous is greyed out on the first page; Next is
greyed out on the last. Both are greyed out for a single-page or empty list.
Disabled buttons do nothing and never change chores or jump pages. Calendar day
lists use Previous page / Next page; moving to another day remains separate.


### Consistent pickup rows

Rows are button-only controls with the day/period marker, chore name, shift where applicable, and points on the name button. Claim/Done and Skip follow it in the same native action row. The name stays clickable while unavailable actions are disabled. Other information is on the chore card. Discord determines actual button widths and wrapping; verify the appearance in Discord after deployment.

## Pickup and My chores rows

Click a chore-name button to open instructions and its named actions. Claim immediately takes this occurrence and keeps its card open. Signup options offers longer responsibility, including repeating weekdays on daily chores. My chores has Done and Skip beside each name. The saved filters, five-item default pages, and fixed Previous/Next positions stay in place.

### Pickup list footer

Below the chore card: Previous / Next, then Due now / This week / Next week /
All chores, then Search / Filters / Refresh / Dashboard. Refresh is the single
recovery control: it reloads current information and keeps your place after
expiry or restart. There is no separate Refresh row in Pick up chores.
The footer shows the page number and Eastern time; week ranges remain in the
weekly view heading. Other screens retain their existing recovery controls.


### Dashboard groups

The private dashboard groups controls by purpose: Do chores (My chores, Pick up chores, Needs attention, Manage chores); Plan & coordinate (Calendar, Household chores, Who’s home?, incoming trades); My settings (Reminders, Notifications, Points & standings, Continue where I left off when available, Refresh); and Owner tools (review inbox, update announcements, household setup when permitted). Help sits beside the dashboard heading. Points and streak appear at the top. Non-owner members with setup permission find Household setup under Plan & coordinate. Refresh safely restores an expired screen after a restart; owner permissions remain unchanged.


### Calendar day layout

Calendar days have chore-name buttons with compact responsibility/points summary buttons. Page controls stay below the page count, followed by Previous day / Today / Next day, then Week / Month / Back / Refresh / Dashboard. Clicking a name opens the current card or an exact date/slot card. Choosing a date alone changes nothing; use Claim just this time or Skip just this time to save. AM/PM repeating owners are shown for the selected date.

### Household list layout

Household uses chore-name, Claim/Done, and Skip buttons. The Taken button identifies the current responsible person when it is someone else. Click the name for the full schedule and repeating weekday assignments. Time tabs, grouping/unclaimed controls, Search, Filters, Refresh and Dashboard remain visible; Back and Refresh preserve the view.

### Points & standings layout

Your points and streak appear together at the top, followed by a compact framed ranking list. Fixed Previous / Next buttons follow the page count. Owner reset and reset-history controls are grouped under Owner controls; everyone has one Refresh / Dashboard row. Refresh restores the current ranking page after expiry or a restart. These display changes do not change points, streaks, history, permissions, or reset confirmations. Points do not currently redeem rewards.


### Consistent workspace style

Workspace screens use compact framed content and one Refresh button. Lists retain fixed page controls; primary actions and selects stay above a shared Back / Refresh / Dashboard row where available. Small adjacent action groups share rows when they fit. Calendar navigation keeps its date groups. Instructions, warnings, confirmation text, owner permissions, and private recovery rules are preserved. My chores retains inline Done and Checklist actions. Refreshing an expired confirmation returns safely without applying it.


### In-app Help

Help starts with a short path for doing a chore, taking work, or looking ahead. The topic buttons use concrete tasks (for example, Finish a chore, Set reminders, and Drop, reassign, or trade). Each topic gives the actual button path and explains the result in short paragraphs. Earlier saved help topics map to the matching new topic; an unknown old topic returns to Start here. Help is private and never changes chores or points.


The dashboard uses one compact framed menu with small group labels. Points and streak sit directly under its title, with Help beside the heading. The same groups, permissions, and recovery controls remain available.


### Personal list length

My settings → List length saves 1–5 items per page for your own account; the default is 5. Previously saved longer lists display five items without changing household data. It applies to chore lists, calendar days, standings, and completion/help-history lists. Detailed review and reset records still open one at a time. Chore pages keep chore-name, Claim/Done, and Skip buttons and fixed Previous/Next paging. Time views, Search, Filters, and Dashboard stay visible below the list, with one safe Refresh button. The combined View & tools menu has been removed. Old saved chore/calendar views keep the same approximate item position when the size changes. Other people’s preferences, chores, points, and history are unchanged.


### Compact secondary screens

Metadata shares short lines where readable; instructions, feedback, and confirmations keep their line breaks. Checklists show steps with progress. Week calendars have seven date buttons; month grids keep their formatting and date choices open buttons. Setting and account choices open button screens, with paging and Apply selection where needed. Permissions and confirmation boundaries are preserved.

### Workload & pace

Open Plan & coordinate → Workload & pace. Each person has earned and planned daily, weekly, and 30-day monthly point rates, plus points per home-day, today’s earned points, projected household share, away coverage, and current due points. Compare past/next 7, 28, or 90 full days; sort by planned load, earned pace, or name. The past ends yesterday and starts no earlier than the first recorded completion. Undone work is excluded; resetting a balance does not erase earned-work history. Future ownership is taken only from saved assignments and dated signups; unclaimed work stays visible. Flexible weekly/monthly work is prorated over its period, not assigned a made-up due day. Undated one-time work is shown separately. Forecasts assume normal completion pace and use current point values; they do not guarantee earnings. Home-day comparisons use the current rotation and saved exceptions, splitting Sunday at 6 p.m.; past attendance edits can change that denominator. The view is private and read-only.


### Home/away defaults for anyone

Who’s home? accepts any household person. With no custom default, Kas and Zel follow their saved alternating weeks (Sunday 6 p.m. Eastern); everyone else is home daily. Usual schedule can change any selected person to home daily, away daily, selected home weekdays, or same/opposite alternating weeks. Save usual schedule applies the displayed defaults to the selected people; Use household default restores the original behavior. Mark home / Mark away and Quick dates can override any individual date or trip. Dated overrides take priority over every default and expire back to it. Existing chores, signups, points, and date exceptions are preserved. Changes are recorded and stale bulk edits are rejected together. Reminders, coverage, signup checks, and workload/home-day calculations use the effective schedule. Changing a default can change historical home-day denominators because attendance defaults are not historical snapshots.


## Skip only the current occurrence

Open a due repeating chore’s **chore name → Skip this occurrence**. Skip happens immediately, with an **Undo skip** button at the bottom. Anyone in the household can do this. It awards no points, creates no completion credit, releases a single-occurrence claim, and keeps weekly sign-ups, ongoing assignments, completed history, and the regular schedule. Morning and evening are separate occurrences: skipping morning leaves evening available at its normal time.

The next occurrence opens at the next regular boundary: midnight for daily work, noon/midnight for twice-daily, the next AM/PM shift, the next selected weekday, Sunday at 6 p.m. for flexible weekly work, or the next month for monthly work. A moved occurrence returns to the regular schedule. Old checklist checks and help notes stay recorded but do not carry into the next occurrence. Skips are recorded separately from completions. Only the person who skipped can undo it, until the next occurrence begins and while the chore remains unchanged. Undo restores the occurrence and its previous claim or moved date without changing points; both actions remain in history. Completed, archived, and one-time chores have no current Skip button. Future dated work has Skip just this time; archive a one-time chore if it is no longer needed. **Skip if missed** remains a separate automatic policy.


## Claim or skip a future occurrence

A chore name always opens **Chore details**, including in **This week**, **Next week**, and **Upcoming**. Use **Choose date** beside the name or **Choose occurrence** on the card to select **AM**, **PM**, or **All day** for an exact date. You can also open **Calendar → a day → a chore**. The exact date, slot, and Eastern time appear above the actions.

- **Claim just this time** reserves only that occurrence. You must be home for it, and it cannot already belong to someone else who is home.
- **Skip just this time** skips only the selected date and slot, immediately and without points. Later repeats and weekly/repeating signups stay saved.
- **Undo skip for this occurrence** appears at the bottom. If you leave the date card, your latest eligible dated skip also has an Undo button at the bottom of chore lists and cards. Only the person who skipped can undo, until that occurrence ends and while its record is unchanged. A previous dated claim is restored if still safe.
- **Drop this dated claim** releases your one-time reservation.

Current chores, calendar ownership, household views, reminders, and projected points use the dated reservation when it arrives. AM and PM remain independent. Saved reservations stay recorded if someone later becomes away; that occurrence then needs coverage. Flexible weekly/monthly work needs a regular day before it has a dated occurrence. Future work cannot earn points or be marked Done early. Changing a repeat schedule or splitting AM/PM first requires releasing its future dated claims and undoing its future skips. All date-specific changes stay in the history.


## Button colors

Green means Claim, Done, or Save. Red means Skip, Undo, or Drop. Dashboard uses Discord’s purple primary button and the dashboard panel has a purple accent. Page controls use < Prev / Next > and day controls use << Prev day / Next day >>, without emoji markers. Details, filters, and settings stay neutral; active view choices retain their selected highlight. Disabled actions stay disabled and dimmed. Labels always name the action, so you do not need to rely on color alone.


## Shorter daily flows

Claim is immediate and keeps its chore open so you can read instructions or press Done. Signup options stays beside the main action on the card. Small choice lists appear directly when they fit; large lists have Previous/Next, and multi-person selection keeps Apply to make the group explicit.

Checklist steps are directly clickable and save one at a time. Checked steps can be clicked again to uncheck; Done awards points only after all required steps are checked. Saved repeating day/shift cells are preselected; one Save replaces only your exact pattern, preserving irregular AM/PM combinations and everyone else’s signups. Clear selection then Save releases your pattern.

Who’s home? shows Home today and Away today for the selected people. These save immediately, keep audit history, and preserve the days before/after today in an existing trip. Other dates and multi-day trips still use the date form. Usual schedule has direct weekday buttons and one Save. The chore card’s Change schedule button opens repeat choices directly, with the existing prefilled form and schedule-conflict protections.

### Screen names and page help

Every private screen has a heading and a small **?** button. It opens help for that screen; **Back** returns to your place, including unsaved choices while the screen is still active. **All help topics** opens the full guide. After a restart, Refresh restores the saved screen location; unsaved confirmation actions are never replayed. Pop-up forms have their own titles; use **?** on the screen that opens the form for instructions.

### Consistent page layouts

Every screen uses a shared page type: dashboard, list, detail, calendar, form/settings, help, or confirmation. Titles and contextual ? help identify the page. Page counts stay directly above fixed Previous/Next controls. Search/filter controls stay together; The ? stays at the top right beside the title; Back, Refresh, and Dashboard have a separate navigation row. Undo stays last. The calendar keeps readable text with Details on the right. Dropdowns hold occasional choices; Claim, Done, Skip, Checklist, paging, and navigation remain visible buttons.

### Prepared 1.3.3 screen simplification
Chore details keeps Claim/Done, Checklist when present, Skip, Need help and Choose date visible. More options opens coordination/history/feedback; Manage this chore there opens editing. Undo remains last. Manage catalog actions follow content. Page controls use < Prev / Next >; day controls use << Prev day / Next day >>, with no yellow-square emoji. Local candidate, not deployed.

## Version A actual interface — prepared 1.5.0, October 23, 2026
Local candidate, not deployed. Private /chores opens a text-first daily sheet: Mine / Available / Everyone, a readable multi-chore list, one chooser for the work card, unchanged Prev/Next arrows, Other dates, Manage chores and personal Settings. New-account sheet length defaults to 8; existing saved preferences stay intact; Settings supports 1–10. Legacy dense lists retain their protected capacity cap.

The compact work card keeps Claim, Done, Skip, Need help and required Checklist visible, with native action icons. Other actions uses named guarded callbacks for coordination, editing, dates and history. Help/status warnings and chore instructions remain visible. Back to list preserves the parent context; Settings Back and recovery do likewise. One neutral latest-eligible Undo remains last. Catalog editing, archive/restore, search, and Household tools remain available through Manage chores. Public text-command launcher behavior is preserved; private slash entry uses the new sheet. Prototype HTML remains separate from actual source validation. No push/deployment authorization for 1.5.0.


## Prepared 2.3.0

Quick actions and account roster behavior are documented in USER-GUIDE.md and QUICK-ACTIONS-REVIEW.md. Needs attention caps the current action sheet at four rows to leave space for navigation and Undo under Discord’s component limit. Quick Done reuses Browse mine/due and its shared completion/checklist backend. Channel cache roster discovery inserts only missing user IDs and preserves existing account fields; it does not enumerate unavailable members or change Discord intents.
