# Testing Sprig

Tests run offline with dummy credentials, mocked Discord delivery, and separate
temporary SQLite databases. Never launch a second real bot to run tests.

## While making changes

Run the tests related to the change, combining name matches when needed:

```sh
python run_tests.py --suite focused --match reminder --match audit10 --profile
```

An empty selection fails. `--list` previews a selection without running it.
The original `python test_chore_board.py -q` command still runs every bot test.

## Before an approved release

Run the full suite once on the final source files:

```sh
python run_tests.py --suite full --profile --report ../sprig-release-tests.json
```

The JSON report records every selected test, pass/fail, skipped tests, elapsed
and setup times, and source fingerprints. It contains no token or household data.
The report is outside the checkout and should not be committed. Changing runtime
code, the test suite, runner, or requirements invalidates the report. Line-ending
differences between Windows and Linux do not invalidate identical source content.

Keep the full release run even when focused checks pass. Backup-tool changes also
need their separate suites (`test_backup_database` on Linux and
`test_backup_transport`); the bot check does not replace those.

## Smaller server installation checks

After approval, transfer the full-run report to the server (for example, from
the local checkout, `scp ../sprig-release-tests.json
discordbot@24.144.97.41:/home/discordbot/sprig-release-tests.json`). Stop Sprig,
take and verify a fresh backup, and install the exact approved commit as usual.
While it remains stopped:

```sh
.venv/bin/python -m pip check
.venv/bin/python run_tests.py --suite server --release-report /home/discordbot/sprig-release-tests.json --profile --report /home/discordbot/sprig-server-checks.json
```

The server command compiles all twelve runtime modules and runs 42 selected
regressions using the server's Python, SQLite, and installed Discord library:

| Coverage | Why it stays in the server check |
| --- | --- |
| Blank DB, old-schema upgrade, record preservation, revision triggers | Migration and SQLite compatibility |
| Private fixture isolation and normal durability settings | Tests cannot reuse household state |
| Claim, simultaneous Claim, duplicate Done | Async actions and single awards |
| Failure rollback, saved trades after restart, completion Undo | Atomicity and persistence |
| Owner-only points reset | Access restrictions |
| AM/PM, DST, Sunday handoff, attendance | Timezone and schedule compatibility |
| Reminder opt-in, deduplication, ownership changes, expired delivery | No unintended or repeated notifications |
| Moved monthly Skip and reload | Timing persistence |
| Today's Calendar, private message flags, component limits | Installed Discord interface support |
| Recovery permissions and actual Discord ViewStore dispatch | Safe recovery and one action per click |
| Update notice routing, deduplication, and no mentions | One release announcement in the correct channel |

The manifest reuses existing regression methods; there is no duplicate set of
server assertions. Missing or repeated manifest entries fail. The command refuses
to run without a passing, unskipped **full** report for the current source content
and full discovered test inventory. Focused/server reports cannot approve it.
Source changes during a run mark that run unsuccessful. A server report cannot
overwrite the full report through the runner.

When a dependency, Python version, database migration, or deployment process
changes substantially, run the full suite on the server too. If the report is
missing, stale, or the smaller checks fail, do not start the new version. Diagnose
the failure; a passing local run does not override a failed server check.

Compare the stopped live database and .env against the backup before restart.
Then start Sprig interactively, verify active/running and startup logs, and check
the changed controls in Discord. Offline checks do not prove that the bot is
running, the real client renders correctly, or opted-in reminders were delivered.

## Speed and duplicate audit

The October 21 audit found 325 original tests, no shadowed test names, and no
identical bodies. Similar tests often cover different paths (legacy command,
private card, inline button, expired control, or concurrent action); those tests
were retained. Four infrastructure checks now cover blank/legacy migration,
fixture isolation, release-report rejection, and duplicate test definitions.

Profiling found that schema creation dominated startup. The first test creates a
normal empty database through the real application and saves that empty schema.
Later tests copy it to a new temporary disk DB before creating a fresh bot. No
household records, bot instance, open connection, or transaction are shared.
SQLite synchronous/journal settings remain unchanged. Explicit blank and legacy
migration tests always bypass the cached schema. Existing restart, independent
connection, rollback, and race tests remain intact.

For an apples-to-apples timing comparison or setup diagnosis:

```sh
python run_tests.py --suite focused --match inline_claim --cold-start --profile
python run_tests.py --suite focused --match inline_claim --profile
```

`--cold-start` also works with the full suite and restores per-test schema creation.
Timing reports show setup totals and the slowest tests so future audits can be
based on measurements instead of the number of tests.

Measured October 21, 2026: the original 325-test local release took 167.450s;
the optimized suite, retaining those tests plus four infrastructure checks, passed
all 329 in 40.194s (about 76% less time). A same-six-test Claim comparison passed
in both modes: 2.737s cold versus 1.135s cached. All 22 server checks passed in
5.949s in a disposable folder with the server’s installed virtual environment;
the live bot checkout, database, and service were not changed. These are observed
times, not a fixed performance guarantee.

The update-announcement feature adds one server check (23 total). Its delivery is mocked, so installation checks never post a real announcement. The 22-check timing above describes the original test-speed audit.

Owner announcement permissions and quiet defaults add another server check (24 total). Automatic and manual delivery are mocked in all installation tests.


Personal list lengths add two installation checks (26 total): ten-item pages fit without hidden chores, and preferences save only for the correct account and persist. Older five-item regression cases explicitly select five; separate tests exercise the actual default of ten, dense navigation, and calendar recovery when lengths change.


Workload & pace adds chore_insights.py (also deploy repeating_signups.py; twelve runtime modules total) and one arithmetic installation check (the current runner selects 42 installation checks). Projection tests cover daily/AM/PM, flexible weekly/monthly budgets, signup expiry and Sunday handoff, DST and trips, moves, unplaced work, Undo/reset history, private recovery, and display limits. The report never writes chore or points data.


Adjustable usual schedules add one installation check (28 total). Tests preserve the old fallback with no custom rows, verify per-person weekdays/rotation, day-override priority, full-day trips, DST/Sunday handoff, bulk atomicity, audit revisions, stale edits, private confirmation/recovery, reminder rechecks, and workload integration. Existing weekly signup/trade snapshots remain compatible until a custom default actually changes.


Buttons-only controls and repeating signup regressions cover name-button navigation, actual button choice/search flows (including two separately searched people), action/label limits, private recovery, weekdays and AM/PM ownership, opposite home weeks and later attendance conflicts, reminders, projected points, single-occurrence coverage/trades/Skip/Undo, schedule-edit guards, and AM/PM split preservation. Deployment source hashes include repeating_signups.py. The existing mutation/safety tests were adapted to name/button rows rather than removed.

Immediate Skip and Undo installation checks cover private one-tap controls, repeat taps, atomic restoration, and preserved recurring signups. The full suite also verifies stale changes, wrong-account attempts, next-occurrence boundaries, claims, moved dates, and missed-chore policy restoration.

Dated occurrence regression coverage includes future-only claims, independent AM/PM slots, stale/competing changes, home/away rules, exact-date reminder delivery, skip/Undo atomic rollback and expiry, persistence, workload arithmetic, calendar and household ownership, current reassignment/trades, and private screen recovery. Deploy dated_occurrences.py with the other runtime modules.

Shorter-flow regression checks exercise direct Claim and retained Done access, inline choice paging/drafts, exact recurring-grid replacement, direct checklist toggles through 12 steps, atomic Home/Away today with surrounding trip preservation, one-save usual schedules, and direct prefilled schedule edits. Existing race/permission/Undo tests remain in the full suite.

Page-help checks cover named headings, one contextual ? per screen, private access, return position, restart recovery, and Discord component limits.

Manage-list regression checks cover active/completed inclusion, archived exclusion, direct prefilled editing, saved search/page recovery, empty results, private access, stale submissions, unchanged earned points, and Discord layout limits.

Shared page-template contracts cover top-right contextual help, ordered slots, native dropdown callbacks and expiry, complete preflight validation, and dense lists with current and dated Undo together. The server manifest currently selects 42 checks; all twelve runtime modules, including chore_pages.py, must match the full release report.
