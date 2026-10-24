# Sprig: handoff to the next chat

Verified October 22, 2026, about 5:28 p.m. America/New_York. This is a dated snapshot: verify Git and server state before acting.

## Read this first

Sprig (Discord display name ChoreSprite) is the household chore bot, not a general-purpose project management system. Everyday interactions should be easy for the kids. Advanced features are welcome when tucked away rather than complicating Claim, Done, Skip, Need help and Undo.

**The current instruction is to try the deployed screen/help/button fixes before doing the larger task simplification proposals.** Do not interpret the audit as a request to implement 190 features or redesign attendance. Katherine accepts occasional awkward attendance work. Conversation belongs in Discord; feedback editing/retraction, discussion threads and structured owner decision explanations were explicitly unnecessary.

## Verified release state

- Repository: `C:/Users/katie/OneDrive/Documents/GitHub/chore_bot`.
- GitHub: `https://github.com/SignalPocket/chore_bot`, branch `main`.
- Identity: `SignalPocket <kkearns@signalpocket.com>`; verify active GitHub account before a push.
- Version **1.3.2**, commit **9aa952815c1703bab23d38bec27205a5346ea69f** is pushed and installed.
- Server: DigitalOcean `spring-bot`, `24.144.97.41`, SSH `discordbot`.
- Server checkout `/home/discordbot/chore_bot`; service `sprig`; `.venv/bin/python`.
- Fresh readback: **active / running**, started October 22 at 21:24:22 UTC (5:24:22 p.m. Eastern).
- **455 full offline tests passed** for the deployed source; **42 report-gated server checks passed**.
- Verified backup: `/home/discordbot/sprig-backups/20261022-212302`.
- The live database and `.env` matched the stopped backup before startup. Do not require byte equality after normal runtime writes.
- **Fresh Discord /chores visual/control checks have not been confirmed in this chat.** Do not call the whole release live-UI verified from a running process alone.

Do not repeat the completed backup/pull/install just because this is a new chat. Inspect actual state first. Starting/stopping needs interactive sudo on this server; the user enters any password privately in the console. Never ask for it in chat or work around the privilege gate.

## What shipped

Reusable page templates; useful Manage catalog; fixed component-limit failures; consistent headings/top-right help; actual chore-name links to details; occasional-action dropdowns; inline attention/calendar Details; attendance Home/Away roster; archive list/dropdown; immediate bottom Undo Done; consistent Archive wording; separate Chore reminders / Trade alerts; saved context through attendance edits; updated guides and tests.

Final polish puts Claim/Done first, removes the duplicate card completion-Undo button, and corrects old help paths. Fifteen offline payload-based screen previews were reviewed at desktop and narrow widths. They approximate Discord, not live client screenshots.

## What did not ship

The next simplification ideas discussed afterward are not implemented: a redesigned Completed history, task-search help, saved failed-form drafts, combined reassign editor, immediate Drop/Undo, date jump, unified schedule editor, apply-and-resolve feedback, or attendance redesign. Get current user direction before implementing them.

Known confirmed ambiguity: a daily chore can reset to unfinished/due and still appear in Completed because the filter checks recorded prior completion. This is documented, not fixed. Source-derived hop counts are estimates; no live measurement of every task has been completed. No test consolidation was done merely because the task audit was written.

## Where the instructions and evidence live

- `AGENTS.md`: release/version/approval rules. Read before work.
- `USER-GUIDE.md`, `BUTTON-BOARD.md`, `TESTING.md`: current usage, implementation/deployment and test procedure.
- `PAGE-TEMPLATES.md`, `chore_pages.py`: reusable screen frame; preflight 40-component/4,000-text limits before attaching controls.
- `INTERFACE-SPEC.md`, `PAGE-MAP.md`: screen/control contract and navigation.
- `TASK-AUDIT-FINDINGS.md`: concise audit and scope decisions.
- `USER-TASK-AUDIT.md` / `.json`: 190 goals: 102 supported, 31 awkward, 37 missing, 20 intentionally unavailable. Missing optional ideas are not commitments.
- `HELP-COVERAGE.md`, `TASK-TEST-AUDIT.md`, `UI-REVIEW.md`: help mappings, coverage boundaries and final polish review.
- `BACKUP-RECOVERY.md`: backup jobs, laptop copy, alerts and restore boundaries; scheduled/live delivery verification is separate from deployment.

Local full report:
`C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.3.2-polished-final.json`.
Server full report: `/home/discordbot/sprig-release-9aa9528.json`.
Server installation report: `<backup above>/server-checks.json`.
Inspect current source hashes before reusing a report; don't pin future test counts.

## Installed local skills

- `$sprig-development`: `C:/Users/katie/.codex/skills/sprig-development/SKILL.md`.
- `$sprig-release`: `C:/Users/katie/.codex/skills/sprig-release/SKILL.md`.

Both were created and structurally validated October 22, 2026. They contain no passwords or production tokens. They are local installed skills, not part of the deployed bot commit. This handoff is a new local repository document and has not been pushed yet.

## Paste into a new chat

Use $sprig-development for my household Sprig/ChoreSprite Discord bot. First read C:/Users/katie/OneDrive/Documents/GitHub/chore_bot/HANDOFF.md and verify the current repository/server state. Version 1.3.2 was installed and running; help me check fresh /chores screens before implementing more audit ideas. Keep everyday chores easy for the kids, with advanced options out of the way. Do not repeat completed deployment steps or treat the 190-task audit as a feature checklist. Use $sprig-release when I request a release; get approval for the final changes before a new push/deployment.

## Local 1.3.3 candidate — awaiting deployment approval

October 22, 2026: Katherine reviewed the simpler screen previews and requested testing/release preparation, not a push or deployment. Everyday chore actions remain visible; More options opens occasional coordination/history/feedback, then Manage this chore opens advanced editing. Page/day navigation uses plain angle brackets. Manage catalog actions follow content.

The server remains installed at 1.3.2 / 9aa952815c1703bab23d38bec27205a5346ea69f. Fresh read-only check during preparation found the service inactive; the app console is connected to spring-bot. Do not infer deployment approval from stopping the service. No new backup/install/push has been performed.

Release report target: C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.3.3-release.json. Verify success and exact source fingerprints before release. Local preview: sprig-simple-screen-review.html in that same directory; serialized dummy data with approximate Discord styling, not live verification.

Final candidate validation: 455 full offline tests passed, zero skipped, source fingerprints unchanged. Report: sprig-1.3.3-release.json at the path above. Push/deployment still awaits exact approval.

## Deployment readback — October 22, 2026, 6:42 p.m. Eastern
Explicit approval received for d17e9ea. Pushed as SignalPocket; installed SHA d17e9ea89d528b4bd2d73f29784a5b1e5aeffabd, version 1.3.3. Backup /home/discordbot/sprig-backups/20261022-224155 verified with SQLite integrity. Full report /home/discordbot/sprig-release-d17e9ea.json: 455 passed. Server report at backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped live DB and .env byte-match backup; announcement preferences preserved. Service inactive pending interactive sudo systemctl start sprig in the connected console. Running/startup readback and fresh Discord controls remain pending. This closeout note is local and uncommitted.

## Local combined Chores review — October 22, 2026
Not deployed. Dashboard now has one Chores destination replacing Calendar, Household chores and Manage chores. Chores offers Today, Week and All chores; a person filter, search, date/page navigation, direct Claim/Done and Edit, Add chore and Archived chores. The gear opens personal List length, Chore reminders and Trade alerts only. Header order is Home, Refresh, Settings, Help on the new Chores, chore details/advanced actions, personal settings and Dashboard screens. Older saved routes remain recoverable. Three chore rows per page maximum reserve room within Discord component limits. Live Discord validation remains pending.

## Compact screen pass — October 23, 2026, local review
All adapted screens now use Home, Refresh, personal Settings, Help in that order in the header; Back remains below when relevant and temporary Undo stays last. Native dropdowns/person selectors remain compact instead of expanding into button walls. Occasional/advanced chore actions use clearly named selectors on their separate screens. Claim/Done, Skip, Need help and Checklist remain visible on chore details. Dense list capacity reserves the complete header footprint. Search in projected calendar lists uses canonical chore records. No push/deployment authorized for this pass.

## Ready for approval — Sprig 1.4.0, October 23, 2026
Combined Chores and compact screen pass prepared locally. Final full offline report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.4.0-final.json: 458 passed, zero skipped, source fingerprints unchanged. Updated old screen-shape tests to exercise real compact header/native selector flows; retained mutation, privacy and recovery checks. 22 serialized dummy-data previews verified for component limits and narrow overflow; sprig-compact-screen-review.html in the same directory. GitHub identity SignalPocket <kkearns@signalpocket.com> verified. Fresh read-only server check confirmed d17e9ea / 1.3.3 active. No push, new backup, install or deployment performed for 1.4.0. Prior approval applied only to d17e9ea; obtain exact approval for this new candidate. Keep announcement preference unchanged. Server report-gated checks and live Discord verification remain deployment-stage work.

## Deployment verified — October 23, 2026, 6:44 a.m. Eastern
Exact approval received for 90b161d083f9c832df15fc1334232925e4c61a29. Pushed as SignalPocket and installed version 1.4.0. Fresh backup /home/discordbot/sprig-backups/20261023-104357 verified; previous installed commit d17e9ea retained. Full report /home/discordbot/sprig-release-90b161d.json: 458 passed. Backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped database and .env matched backup byte-for-byte after checks; announcement preferences unchanged. Sprig is inactive pending interactive sudo systemctl start sprig in the app console. Startup/readback and fresh Discord screen verification are still pending. No database restore performed. This deployment closeout is local/uncommitted.

## Local Settings Back and quiet Undo fix — October 23, 2026
Settings now preserves its opening screen as a Back/recovery parent. Skip, dated Skip and Done shortcuts collapse to one neutral ↶ Undo accessory beside a small action description at the bottom. It targets the most recent eligible event by recorded timestamp; existing guarded domain reversals remain in use. Older completion/skip validity checks still apply. Local fix only, not pushed or deployed.

## Local grouped Chores layout — October 23, 2026
Approved for local preview, not deployment. Day/Week/All chores, Search, date navigation and person selector form the view controls. Separators distinguish the results and paging. Chore names remain clickable; Claim/Done remains directly beside names. Edit is a consistent right-side accessory. Day view omits repeated row dates; Mine/Unclaimed omit redundant ownership. Page count is centered between paging buttons; Manage chores labels Add/Archived controls. Two chores per page preserve every control within the Discord component budget. Settings Back and unified quiet Undo fixes remain part of this local candidate.

## Release candidate 1.4.1 — October 23, 2026, 7:05 a.m. Eastern
Ready for exact push/deployment approval: organized Chores layout, contextual Settings Back with recovery, and one neutral latest-eligible Undo with action description. Full report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.4.1-final.json verified: 460 passed, zero skipped, source fingerprints unchanged. Thirty affected tests passed separately; grouped-layout and Undo/Back previews refreshed and narrow overflow checks passed. Current server readback: 90b161d / version 1.4.0, inactive. No new push, backup or installation performed. SignalPocket identity verified. Preserve announcement preferences. After approval, obtain fresh stopped backup, install only approved commit and run report-gated server checks. Startup and fresh Discord validation remain separate steps. Earlier approvals cover earlier commits only.

## Deployment readback — 1.4.1, October 23, 2026, 7:12 a.m. Eastern
Explicit approval received for 047a3281bf2143fd09e672d32c291f49019ca4d6. Pushed as SignalPocket; installed SHA/version verified. Fresh protected backup /home/discordbot/sprig-backups/20261023-111215 passed SQLite integrity; previous SHA 90b161d retained. Full report /home/discordbot/sprig-release-047a328.json: 460 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped live database and .env byte-match backup after checks, preserving announcement preferences. Sprig inactive; interactive sudo systemctl start sprig is the next step in the opened console. Running/startup and fresh Discord validation remain pending. No data restore. Local closeout note only, uncommitted.

## Version A actual interface — prepared 1.5.0, October 23, 2026
Local candidate, not deployed. Private /chores opens a text-first daily sheet: Mine / Available / Everyone, a readable multi-chore list, one chooser for the work card, unchanged Prev/Next arrows, Other dates, Manage chores and personal Settings. New-account sheet length defaults to 8; existing saved preferences stay intact; Settings supports 1–10. Legacy dense lists retain their protected capacity cap.

The compact work card keeps Claim, Done, Skip, Need help and required Checklist visible, with native action icons. Other actions uses named guarded callbacks for coordination, editing, dates and history. Help/status warnings and chore instructions remain visible. Back to list preserves the parent context; Settings Back and recovery do likewise. One neutral latest-eligible Undo remains last. Catalog editing, archive/restore, search, and Household tools remain available through Manage chores. Public text-command launcher behavior is preserved; private slash entry uses the new sheet. Prototype HTML remains separate from actual source validation. No push/deployment authorization for 1.5.0.

## Version A ready locally — 1.5.0, October 23, 2026, 8:50 a.m. Eastern
User selected Version A with action icons and explicitly instructed not to deploy yet. Actual /chores entry, daily sheets, compact work cards and native action icons are implemented, not merely prototyped. Eight-row real-source fixture and guarded Claim/Done/Undo, Settings Back, parent/restart recovery, repeat rendering and private entry were verified. Existing saved list-length preferences remain intact; new-account sheet default is 8 and Settings permits 1–10; legacy dense views retain safe caps.\nFull exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.5.0-ready.json: 461 passed, zero skipped, sources unchanged. Actual-source review: sprig-actual-version-a-review.html in that directory; seven representative payloads passed component and narrow layout checks. Success completion notices are concise; safety/error messages remain intact. Existing calendar/advanced household tools are retained.\nFresh server readback during preparation: 047a328 / 1.4.1 active. No push, backup, install or deployment was performed for 1.5.0. Keep announcement preferences unchanged. Obtain exact approval for this new final commit before any push/deployment; earlier approvals cover older commits only. Deployment still requires fresh stopped backup, report-gated server checks, startup readback and real Discord verification.


## Personal color markers — October 23, 2026, local review
Added Settings → Your color with persistent account-ID choices, guarded save, No marker and contextual Back/recovery. Workspace names display the chosen marker. Initial exact display-name/username defaults: Dar lavender (purple dot), John blue, Kas pink (heart), Z/Zel orange; the known owner account defaults green. These are display defaults only, not ownership matching; saved account choices override them. No standard lavender/pink circle exists in Discord emoji. Existing notification and list preferences are preserved. Included in the still-unreleased 1.5.0 candidate.
Full report sprig-1.5.0-colors.json: 462 passed, zero skipped, exact sources unchanged. Five actual-source color preview screens serialized within 40 components and checked for narrow overflow. Review: C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-actual-version-a-review.html. This supersedes the earlier 461-test report for the changed sources. No push, server action or deployment. Changes after f6a0616 are local pending screen review.


## Deployment readback — 1.5.0, October 23, 2026, 9:02 a.m. Eastern
User explicitly approved the reviewed Version A with personal colors for push as SignalPocket and deployment to spring-bot. Pushed and installed 0075057fa3f87eba936f0030b771a04e02e4339a (APP_VERSION 1.5.0). Fresh protected stopped backup /home/discordbot/sprig-backups/20261023-130136 passed SQLite integrity, retaining previous 047a328. Full exact-source report /home/discordbot/sprig-release-0075057.json: 462 passed, zero skipped. Report-gated backup/server-checks.json: 42 passed; dependencies and compilation passed. Stopped live DB and .env byte-match backup, preserving announcement preferences. Service verified inactive after installation; sudo -n start required a password, so interactive sudo systemctl start sprig is pending in the opened app console. Do not bypass sudo or collect passwords. Startup/readback and fresh Discord verification remain pending. No database restore performed. Local closeout note, not part of pushed commit.


## Compact one-line rows — local 1.5.1 review, October 23, 2026
User requested lighter daily-sheet rows, eight chores and color markers, with an actual Discord preview before deployment. Removed bold titles and list points; points stay on work cards. Middle-dot numbering avoids Discord Markdown ordered-list formatting. Everyone resolves visible names via the existing name primer and suppresses mention-chip fallback; unresolved accounts read Assigned. Existing list preference remains intact. No new push/deployment.
With explicit permission, ChoreSprite sent one private DM preview to the known owner account using fictional temporary data and disabled controls. Stable key sprig-compact-rows-20261023-v1, channel 1562187921056993311, message 1563178059660525703; delivery read back through Discord API. Sender identity verified ChoreSprite. No second bot, production code install or chore mutation; no notification preference changes. Rendering must be reviewed in Discord; API readback alone is delivery verification, not visual approval.

User reviewed the private Discord preview and said "love it". Layout approved; no deployment requested for 1.5.1. Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-1.5.1-rows.json: 463 passed, zero skipped, sources unchanged. Existing 1.5.0 deployment approval does not cover this new patch.


## 2.0.0 release authorized — October 23, 2026
User named the reviewed compact-row release 2.0 and explicitly authorized push to SignalPocket/chore_bot as SignalPocket and deployment to spring-bot with backup/server checks, preserving announcement preferences. APP_VERSION and announcement test aligned at 2.0.0; a fresh full report is required after this version change. Earlier 1.5.1 notes describe this same approved layout.


## 2.0.0 pushed; installation waiting on interactive stop — October 23, 2026, 9:19 a.m. Eastern
Fresh exact-source full report sprig-2.0.0-release.json: 463 passed, zero skipped, sources unchanged. Committed/pushed 86af1f9be0a529bfc2f84cde153d7c29fdab2f02 to SignalPocket/chore_bot as verified SignalPocket identity. Full report transferred and verified at /home/discordbot/sprig-release-86af1f9.json with --prepare-only. Server still active at 0075057 / 1.5.0; sudo -n stop requires password. App console opened and user given sudo systemctl stop sprig. No 2.0 backup/install/server checks yet; no announcement preferences changed. After inactive is verified, run inspected deploy_with_full_report.py with exact approved SHA/report (without --prepare-only), obtaining fresh backup and gated server checks. Then interactive start and fresh startup/readback remain required. Existing exact user approval covers these pending 2.0.0 deployment steps. This closeout note is local/uncommitted.


## 2.0.0 installed — October 23, 2026, 9:40 a.m. Eastern
After user stopped Sprig, verified inactive and installed approved 86af1f9be0a529bfc2f84cde153d7c29fdab2f02 / 2.0.0. Fresh protected backup /home/discordbot/sprig-backups/20261023-133943 retained prior 0075057 and passed SQLite integrity. Full report /home/discordbot/sprig-release-86af1f9.json: 463 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped live database and .env matched backup byte-for-byte, preserving announcement preferences. sudo -n start requires password; service remains inactive pending user console sudo systemctl start sprig. Startup/readback and fresh /chores validation remain pending. No data restore. This closeout note is local/uncommitted.


## Local 2.0.1 — Refresh everywhere and selected view highlights, October 23, 2026
User requested refresh on every screen and testing of selected Mine/Available/Everyone highlights, explicitly no deployment. The daily sheet and compact work card now use the common Home / Refresh / Settings / Help header. Existing Dashboard and generic workspace pages already supply a single Refresh; native pop-up forms retain Discord submit/cancel. Refresh uses guarded saved-context recovery and never repeats the prior action; selected scope uses native primary style, other scopes secondary. Eight-row compact content and color markers are retained.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.1-refresh.json: 465 passed, zero skipped, sources unchanged. Checks cover all three highlights, scope switching, refresh context/no quest mutation, existing privacy/restart recovery, dense component limits and the expanded settings/catalog/secondary screen matrix. Actual-source preview rebuilt: five screens within Discord component limits, no narrow overflow. No Discord message sent for this change. No push or deployment; changes remain local. Live 2.0.0 startup verification remains as previously recorded.


## 2.0.1 deployed, startup pending — October 23, 2026, 9:53 a.m. Eastern
Exact user approval received. Verified GitHub account/commit identity SignalPocket, pushed and installed a774237fabe824dc9e0b14c45643a2b6229fc2e8 / 2.0.1. Sprig was already inactive. Fresh protected backup /home/discordbot/sprig-backups/20261023-135322 retained previous 86af1f9 and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-a774237.json: 465 passed, zero skipped. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped live DB and .env byte-match backup; announcement preferences unchanged. sudo -n start requires password; service verified inactive after installation. User must run sudo systemctl start sprig in connected console; startup/readback and new /chores refresh/highlight verification remain pending. No data restore performed. Local closeout note, uncommitted.


## Local 2.0.2 — Discord rejected Done emoji, October 23, 2026
User showed failure while opening chore details. Fresh journal readback confirmed service active on 2.0.1 and gateway startup at 14:13 UTC. At 14:13:48 UTC, chooser → Card → present failed HTTP 400 / 50035: data.components.3.components.0.emoji.name Invalid emoji. The Done decorator used plain ✓, which is not an emoji. Replaced only the Done emoji with ✅; points, responsibility and layout unchanged. Failing chooser opens details and performs no domain mutation.
Local APP_VERSION/announcement tests aligned at 2.0.2. Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.2-emoji.json: 466 passed, zero skipped, sources unchanged. New regression inspects serialized Done emoji and exercises guarded completion. No push or deployment authorized/performed for this new patch. Existing live bot still 2.0.1; future deployment requires exact approval, fresh backup/server checks, startup and real Discord details check. Local closeout note only.


## 2.0.2 installed — October 23, 2026, 10:19 a.m. Eastern
Exact user approval received; pushed as verified SignalPocket and installed b79987f9f68014acc674bd3b533e101bb962b6b3 / 2.0.2. Sprig was inactive before deployment. Fresh protected backup /home/discordbot/sprig-backups/20261023-141921 retained a774237 and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-b79987f.json: 466 passed, zero skipped. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed; stopped DB and .env matched backup byte-for-byte, announcement preferences preserved. Fresh installed SHA/version/inactive status verified. Interactive sudo systemctl start sprig remains required; startup/readback and fresh live chore-details verification remain pending. No database restore. Local closeout note, uncommitted.


## Local chore-card regrouping — 2.0.3, October 23, 2026
User requested signup choices in one dropdown, More as a separate occasional-tools screen, Claim/Done prominent with Back beside them, and Need help less prominent. Implemented direct guarded signup choices, More screen with existing protected actions, primary action/Back row, and secondary neutral Skip/Need help/More row. Discord sizes are fixed; quieter styling/placement replaces physical size changes. Existing points/scope/cancellation/stale and recovery checks retained. More context restores the chore and original list. Help/guide/spec and version tests aligned. No push/deployment authorized.
User explicitly requested a Discord preview before deployment, using the established private ChoreSprite-to-owner preview workflow. One new preview DM sent and read back, then updated in place after secondary-row order was finalized (no duplicates). Stable key sprig-card-actions-20261023-v1; channel 1562187921056993311; message 1563202862715117710. Actual serialized temporary-fixture card has Done, adjacent Back, Sign up dropdown, neutral Need help and More. Controls disabled; no household records changed. Discord accepted the final payload, including action emojis. Full regression report target: C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.3-card.json. Verify success before release.

Final 2.0.3 full exact-source report verified: 467 passed, zero skipped, sources unchanged. Targeted access/expired-control tests also passed. Still local, not pushed or deployed. Private Discord preview awaiting user review.


## 2.0.3 installed — October 23, 2026, 10:56 a.m. Eastern
Exact user approval received; GitHub destination/account/commit identity verified SignalPocket. Pushed and installed 11f4cace216e4494e80325ee7ce1fc20fa972309 / 2.0.3. Sprig was inactive before backup. Fresh protected backup /home/discordbot/sprig-backups/20261023-145536 retained prior b79987f and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-11f4cac.json: 467 passed, zero skipped. Report-gated backup/server-checks.json: 42 passed; dependencies and compilation passed. Stopped live database and .env byte-match backup; announcement preferences unchanged. Installed SHA/version confirmed. sudo -n start requires password; service remains inactive pending console sudo systemctl start sprig. Startup/readback and fresh /chores chore-card interaction verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.0.4 — Claim/Done click-position fix, October 23, 2026
User requested swapping Done and Back after Claim to prevent a quick second click completing the chore. Unclaimed cards retain Claim | Back; cards offering Done now put Back first, then Done (and Checklist when present). Existing recovery, completion guards and points unchanged. Regression exercises real Claim, second click in the old Claim position → list with no completion/points, then deliberate Done → single completion. Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.4-click.json: 468 passed, zero skipped, sources unchanged. No push or deployment performed/authorized for 2.0.4.


## 2.0.4 pushed; interactive stop pending — October 23, 2026, 11:19 a.m. Eastern
Exact user approval received for push/deployment, preserving announcement preferences. Verified active GitHub and commit identity SignalPocket. Full exact-source report sprig-2.0.4-click.json verified: 468 passed, zero skipped, sources unchanged. Pushed 146b79c03664414f63ab01fc8f5efefd284d9428. Full report transferred/read back at /home/discordbot/sprig-release-146b79c.json using --prepare-only. Server still active on 11f4cac / 2.0.3; sudo -n stop requires password. Opened console; user instructed sudo systemctl stop sprig. No 2.0.4 backup/install/server checks yet. After inactive is confirmed, existing exact approval covers fresh backup, inspected deploy_with_full_report.py for 146b79c/current report, server checks and startup/readback. No announcement preference changes. Local note, uncommitted.


## 2.0.4 installed — October 23, 2026, 11:20 a.m. Eastern
After user stopped Sprig, verified inactive and installed approved 146b79c03664414f63ab01fc8f5efefd284d9428 / 2.0.4. Fresh protected backup /home/discordbot/sprig-backups/20261023-151934 retained previous 11f4cac and passed SQLite integrity. Full report /home/discordbot/sprig-release-146b79c.json: 468 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed; stopped live DB and .env byte-match backup, announcement preferences unchanged. Installed SHA/version verified. sudo -n start requires password; service remains inactive pending console sudo systemctl start sprig. Startup and fresh Discord Claim → Back/Done interaction verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.0.5 — inline More dropdown, October 23, 2026
User specifically approved replacing the More button/intermediate tools page with two directly visible dropdowns: Sign up… and More…. Work-card More now routes straight to the selected existing guarded tool; Sign up scopes remain separate. Primary actions/Back order, quiet Need help and current eight-row/color list remain. ChoreMore recovery class is retained only for older saved routes. No private Discord preview sent for this change.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.5-more.json: 468 passed, zero skipped, sources unchanged. Focused action/private-access/expired controls tests passed too. No push/deployment. Earlier feedback about redundant AM wording and placing compact success messages below list/paging is not included in this dropdown-only patch and remains outstanding.


## 2.0.5 installed — October 23, 2026, 11:34 a.m. Eastern
Exact user approval received; verified SignalPocket GitHub/commit identity and pushed/installed 0dcf3cb7298a563356b683283e7c772a2cddeaab / 2.0.5. Service was already inactive. Fresh protected backup /home/discordbot/sprig-backups/20261023-153400 retained prior 146b79c and passed SQLite integrity. Full report /home/discordbot/sprig-release-0dcf3cb.json: 468 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed; stopped live DB and .env byte-match backup, announcement preferences unchanged. Installed SHA/version verified. sudo -n start requires password; service remains inactive pending console sudo systemctl start sprig. Startup/readback and real Discord inline More verification pending. No data restore. Local closeout note, uncommitted.


## Local 2.0.6 — consolidate chore entry points, October 23, 2026
User approved removing separate My chores / Pick up chores destinations in favor of Chores → Mine / Available. Removed their dashboard buttons; fresh public starters expose Chores, Who’s home?, Manage chores, Help. Persistent registration retains old mine/open/household IDs privately via Launcher(legacy=True): they now open Chores Mine/Available/Everyone ephemerally, so old public messages still route. ReturnView and default Card Back use the combined page. Internal legacy filtered Browse/calendar/history views remain to preserve advanced filters, dates and recovery. Workspace help paths updated. No live starter-message edit, Git push, deployment or other external write.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.6-entry.json: 469 passed, zero skipped, sources unchanged. Focused persistent redirect/launcher/privacy/date-navigation tests also pass. Old screen-shape tests updated while retaining behavioral coverage. Ready locally only. Earlier compact status-line and redundant AM wording feedback remains separate/outstanding.


## Inline Settings added to local 2.0.6 — October 23, 2026
User requested compact single-page Settings with real controls, visible Back and a Discord preview before deployment. PersonalSettings now supplies native color/list-length dropdowns, direct reminder/trade-alert toggles, and a native Change times modal returning to Settings. Existing reminder parsing/revision checks are reused; trade toggles reject stale state; user access checks apply to all callbacks and modal submission. Existing preference tables/opt-ins preserved unless individually changed. Short save confirmations render below Settings controls, not above title. Existing old settings screens remain for saved recovery routes.
Private preview as ChoreSprite sent once to established owner DM destination; stable key sprig-inline-settings-20261023-v1, channel 1562187921056993311, message 1563217522952634424. Sent/read back through Discord API; 17 actual-source components plus disabled-example footer, accepted by Discord. Example data only; real settings untouched. No push/deployment.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.6-settings.json: 470 passed, zero skipped, sources unchanged. This supersedes earlier 469-test entry-only report. Tests cover inline field saves, access, stale reminder state, modal return, Back and prior regressions. Candidate includes already-requested consolidated Chores entry points. Other outstanding status-line/AM feedback remains outside this patch. Await user screen review and exact release authorization.


## 2.0.6 installed — October 23, 2026, 12:35 p.m. Eastern
User reviewed Discord Settings preview and explicitly authorized push/deployment. Verified SignalPocket account/commit identity; pushed and installed 0213a3a6a16c2bc37622776800e8a8391f4e7d91 / 2.0.6. Sprig was inactive. Fresh protected backup /home/discordbot/sprig-backups/20261023-163453 retained prior 0dcf3cb and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-0213a3a.json: 470 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped DB and .env byte-match backup; announcement preferences unchanged. Installed SHA/version confirmed. sudo -n start requires password; service remains inactive pending console sudo systemctl start sprig. Startup/readback and fresh Discord Settings saves/Back and consolidated entry checks remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.0.7 — dropped chore return error, October 23, 2026
User screenshot showed a saved drop confirmation followed by failure clicking Chores. Fresh logs confirm 2.0.6 active/startup and 16:50:03 UTC HTTP 400 / 50035: raw buttons at data.components.10/11 rejected as invalid top-level V2 components. ReturnView → workspace.present ran through InteractionProxy/ResponseProxy again, adapting an already-rendered LayoutPanel and appending bare legacy buttons. present now unwraps its interaction proxy; adapt recognizes LayoutPanel as already rendered. Generic fallback error guidance uses /chores, not the removed My chores destination.
Regression executes adapted DropChoreView Confirm drop → ReturnView Chores → rendered Chores → Refresh; checks released ownership, unchanged points, wrong-account rejection, valid top-level V2 types, no bare root buttons, and component budget. No live database mutation, message send, push or deployment. Full report target C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.7-return.json; verify success before release.

Final 2.0.7 full exact-source report verified: 471 passed, zero skipped, sources unchanged. Targeted regression passed. Fix remains local, not pushed or deployed. Current live server was verified active on 2.0.6 during diagnosis.


## Expanded personal markers in local 2.0.7 — October 23, 2026
User requested more chooser colors and asked for different icons. Added red, white, black, brown dots and star/flower/leaf/moon/paw-print symbols to the existing palette. Settings labels it Name marker, still one dropdown; stored keys use the existing per-account table. Native emoji retain their own colors. Existing saved choices and household defaults preserved. No real preferences changed; no message send, push or deployment.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.7-markers.json: 472 passed, zero skipped, sources unchanged. Supersedes the earlier drop-return-only report. Candidate includes both the return-screen bug fix and expanded markers. The Needs attention fourth-tab idea was discussed but not yet implemented or specifically approved as an action; earlier compact status-line/AM feedback remains outstanding.


## Calendar scope in local 2.0.7 — October 23, 2026
User explicitly requested Other dates preserve Mine/Everyone and noted the old switch was difficult to find. Other dates now passes mine=True from Mine and False from Everyone. Calendar week/month and Day expose persistent Mine/Everyone buttons in the toolbar below the common header; selected scope uses primary style. Week/month/date navigation and recovery keep scope. Existing schedule projection rules unchanged. Available still uses existing household calendar behavior. No push/deployment or external preview message.
Targeted tests cover inherited scope/date, selected toolbar labels/style, Next navigation, recovery, Day switching and existing calendar content/limits. A dated layout expectation was updated to include the new scope row while preserving the existing paging/day navigation order. Final full report target: C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.7-calendar.json.

Final combined 2.0.7 full report verified: 473 passed, zero skipped, sources unchanged. sprig-2.0.7-calendar.json supersedes earlier return/marker-only reports. Candidate contains drop-return fix, expanded markers and persistent calendar scope controls. Still local, no push/deployment.


## 2.0.7 installed — October 23, 2026, 1:06 p.m. Eastern
Exact user approval received. Verified SignalPocket account/commit identity; pushed and installed 771d3f41ef8d5bdc0796c6c7ffd5d8986ce4f4bc / 2.0.7. Sprig was inactive. Fresh protected backup /home/discordbot/sprig-backups/20261023-170545 retained prior 0213a3a and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-771d3f4.json: 473 passed. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed; stopped live DB and .env byte-match backup, announcement preferences unchanged. Installed SHA/version verified. sudo -n start requires password; service remains inactive pending console sudo systemctl start sprig. Startup/readback and live drop-return, calendar scope, marker checks remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.0.8 — native chore-card hierarchy, October 23, 2026
User requested a stronger card feel to distinguish heading/navigation/task/controls. Work-card app heading/navigation sit above a native accented Container holding task name, status/points, separator, To do instructions and help warnings. Actions are labeled outside the task card; Claim/Back and Back/Done safety positions, stacked signup/More menus and quiet Need help remain. Result text follows controls and Undo stays last. No domain rules changed.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.0.8-card.json: 474 passed, zero skipped, sources unchanged. Real-source Claim and Done previews each use 22 components; narrow-overflow checks passed and desktop image inspected. Approximate local review: C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-detail-card-review.html. Preview renderer corrected ## heading and line-break styling in this new artifact. No Discord preview message, push or deployment performed/authorized for this change. Real Discord visual validation remains separate.


## Local 2.1.0 — household help access and grouped menus — October 23, 2026
User requested help reporting without the responsible-person/due restriction. Any authorized household member can now report Stuck, Need supplies or Need help on unfinished, non-archived work, including unclaimed and future occurrences. Responsibility, completion and points are untouched; no automatic DM. Completed/archived/missing chores show an explicit reason. Existing stale-state, account/guild, shared history and validation protections remain. Help documentation updated.
Includes earlier pending native chore card and approved grouped More options (People, Schedule, Edit, Review, History), with icons/descriptions on real actions and original callbacks. Sign up scopes have descriptions; native selects remain stacked per Discord limits.
Full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.1.0-help.json: 476 passed, zero skipped, sources unchanged and fingerprints verified. Focused help checks: 13 passed. Tests use temporary databases and mocked delivery. No push, deployment, live data or preferences change, or new Discord preview message. Prior card HTML remains approximate; no claim of live visual verification for this candidate. Other outstanding list-status/AM wording and fourth-view discussion remain separate.


## 2.1.0 installed — October 23, 2026, 1:33 p.m. Eastern
Exact approval received for SignalPocket push and spring-bot deployment. Verified account/commit identity and pushed/installed 6f11f8edcb55d04e7dbcf23e2ea592289ba16e4a. Graceful stop was completed through user console and inactive verified. Fresh protected backup /home/discordbot/sprig-backups/20261023-173309 retained prior 771d3f4; SQLite integrity passed. Final exact-source report sprig-2.1.0-release.json supersedes help-only report after correcting the release-summary sentence: 476 passed, zero skipped, hashes verified. Server report /home/discordbot/sprig-release-6f11f8e.json; backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped sprig.db and .env byte-match backup; announcement preferences unchanged. Installed SHA/version verified. sudo -n start requires password; service remains inactive pending user console sudo systemctl start sprig. Startup/readback and fresh Discord card/menu/help verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.1.1 — single Actions dropdown — October 23, 2026
User approved combining Sign up and More into Actions with all descriptions retained, keeping Claim/Done/Back outside and requesting review before deployment. Signup-prefixed choices come first, followed by existing People/Schedule/Edit/Review/History groups; original callbacks, icons, validation, account guards and click-position safety remain. Completed cards explicitly explain why Claim/Done are unavailable. Screenshot chore was already completed; no eligibility, scheduling or point rules changed.
Full exact-source report sprig-2.1.1-actions.json: 476 passed, zero skipped, sources unchanged and hashes verified. Targeted routing/privacy/help/completed checks pass. Refreshed actual-source approximate HTML review at C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-detail-card-review.html, three states (available Claim, assigned Done, completed explanation), 19–20 components, narrow overflow none. Local preview only; no Discord message, push or deployment. Await screen review and explicit release approval.


## 2.1.1 installed — October 23, 2026, 4:44 p.m. Eastern
Exact user approval received; SignalPocket GitHub/commit identity verified. Pushed and installed 4bfd3db39b7644ffa4e7bca73d276c7f90a16646 / 2.1.1. Sprig was already inactive, confirmed before fresh backup. Protected backup /home/discordbot/sprig-backups/20261023-204359 retains prior 6f11f8e and passed SQLite integrity. Full exact-source report /home/discordbot/sprig-release-4bfd3db.json: 476 passed, zero skipped, fingerprints verified. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed; stopped sprig.db and .env byte-match backup, announcement preferences unchanged. Installed SHA/version confirmed. sudo -n start requires password; console opened/requested sudo systemctl start sprig. Service remains inactive pending start; startup/readback and real Discord Actions-menu verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.1.2 — direct drop return — October 23, 2026
User requested Confirm drop go straight to Chores. Successful saved drop now calls shared workspace.present with Chores and a short Dropped notice; no intermediary ReturnView/Chores-button screen. Explicit callback account/access guard added; existing mutation lock, snapshot validation, history/points rules, cancellation and failures unchanged. Focused drop suite: 7 passed (sprig-2.1.2-drop-focused.json), including direct V2 return, Refresh/privacy, cancellation, ownership and points. Full final-source release suite still required before deployment. No push or deployment authorized/performed for 2.1.2.


### Action-first labels in local 2.1.2
Approved menu refinement: action names lead; categories move into the retained descriptions. People/Schedule choices use a native category icon plus a distinct action icon in the label where useful; other choices retain one icon. Related ordering and original callbacks unchanged. Refreshed actual-source approximate local review; 9 focused menu/drop tests passed (sprig-action-labels-focused.json), narrow overflow none. Includes pending direct-drop return. No push/deployment. Full exact-source release testing remains required.


## 2.1.2 fully tested and ready locally — October 23, 2026, 5:02 p.m. Eastern
User approved final testing/preparation only, explicitly no deployment. Final full exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.1.2-full.json: 476 passed, zero skipped, sources unchanged and fingerprints verified. Candidate includes direct successful drop → Chores with short notice, guarded account access, and action-first Actions menu labels with category descriptions/paired icons. Existing ownership/history/points and stale-state rules retained. Reviewed local preview is approximate, not live Discord verification. Full report supersedes earlier focused-only readiness notes. No GitHub push, server changes, external messages or preference changes. Ready for exact release approval; fresh stopped backup/server checks/startup verification remain deployment-time work.


## 2.1.2 installed — October 23, 2026, 5:17 p.m. Eastern
Exact user approval received for SignalPocket push and spring-bot deployment. Identity verified; pushed/installed 0b7ecb79acccb0cbaded4293efa043f254d4f263 / 2.1.2. Sprig was already inactive, verified before backup. Fresh protected backup /home/discordbot/sprig-backups/20261023-211715 retains prior 4bfd3db; SQLite integrity passed. Full report /home/discordbot/sprig-release-0b7ecb7.json: 476 passed, zero skipped and exact-source hashes verified. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped sprig.db and .env byte-match backup; announcement preferences unchanged. Installed version/SHA confirmed. sudo -n start requires password; console opened and user asked to run sudo systemctl start sprig. Service inactive pending startup; running/startup logs and fresh Discord direct-drop/menu verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.1.3 — finished state, October 24, 2026
User approved completion presentation and requested preview before deploying. work_card now renders completed work with Done — nice work!, Completed/secondary instructions and quiet return date; primary Back to chores, existing quiet Undo, no active Claim/Done/Skip/Need help controls. Advanced Actions remains. Redundant normal completion announcement text is suppressed on the finished card; other notices remain. No completion/point/schedule/Undo domain changes.
Focused finished/menu checks: 3 passed (sprig-finished-focused.json), including actual Done callback, exactly one completion, finished layout, wrong-person Back rejection and Undo restoring unfinished state. Real-source approximate local HTML preview refreshed with actual dummy completion and Undo: sprig-detail-card-review.html#screen-2. Three states use 19–20 components; narrow overflow none; desktop image inspected. No Discord message, push or deployment. Full final-source suite remains required before release.


### Short Done confirmation in local 2.1.3
Approved refinement: immediately after a successful completion, show only the checked chore name, Done — nice work!, awarded points and quiet return date, with primary Back to chores and the existing quiet Undo. No instructions or Actions menu in this immediate receipt. Reopening the chore still exposes completed details/tools. No automatic navigation or domain changes. Two focused completion/menu tests passed, including real completion, Undo and reopened tools (sprig-short-done-focused.json). Actual-source approximate preview refreshed: completion uses 15 components, narrow overflow none, image inspected. No push/deployment; full final-source testing remains required.


## Local 2.2.0 — main screens implemented and fully tested — October 24, 2026
User approved applying the main-screens concept, eight chores, visible Claim/Done and full testing, with review before deployment. Includes pending short Done receipt. Chores now has native accented list card and fixed Mine/Available/Everyone/Needs attention row, ordinary one-line entries, attention reason subtext, eight-item default with saved preference preserved, and compact bottom controls. Current Needs attention reuses existing attention_rows classification. Other dates is mode=date on the same Chores screen, preserving all four scopes/day/page/query through navigation and recovery; Week calendar retains the existing week/month overview. Future attention lists projected unclaimed work without copying current help/overdue labels.
Done leaves today’s active list and Undo restores it; normal due resets are reused before reading. Claim/Back and Back/Done safety positions remain, with Back to chores wording. Finished receipt has checked name, points, quiet return date, Back and small neutral Undo; reopened cards retain tools. Native Actions descriptions/icons/routing remain. Settings uses the same compact header and direct controls; no extra Settings button below Chores. Manage catalog is a native list card, chooser opens existing EditChoreModal directly, guarded submission uses update_chore snapshot rules under the shared lock and returns to catalog context; management actions are below content and Household tools remains accessible. Dashboard main shortcuts route to the unified screens. Legacy advanced Calendar/Attention/recovery/domain APIs remain available. In-app help and docs updated.
Final report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.2.0-main.json: 477 passed, zero skipped, sources unchanged and fingerprints verified. Focused scope/date/attention/limits/privacy/edit/Done/Undo/help checks passed. Old destination/label tests updated while retaining paging, private controls, legacy recovery and midnight-calendar coverage.
Actual-source review C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-actual-main-review.html contains 12 temporary-household states: Mine, Available, Everyone, Needs attention, dated Mine/Everyone, catalog, Settings, Claim, Done, receipt and empty. 15–28 native components, narrow overflow none, individual desktop layouts inspected. Approximate styling only, not live Discord verification. Generated example data only; no real preference/data mutation, bot startup, Discord message, GitHub push or deployment. Ready locally for user screen review and exact release approval. Earlier status-line feedback is addressed on Chores; duplicate AM title wording remains separate.


## 2.2.0 pushed — awaiting graceful stop, October 24, 2026
User reviewed actual-source screens and explicitly approved SignalPocket push and spring-bot deployment. Verified identity and exact-source full report (477 passed, zero skipped, fingerprints match); committed/pushed b90fbb784d2961a6fb8b42232f9928fcb4969fb6 / 2.2.0. Full report transferred/read back at /home/discordbot/sprig-release-b90fbb7.json using prepare-only. Server was active at prior 0b7ecb7 / 2.1.2, clean tracked checkout. sudo -n stop requires password; console opened/requested sudo systemctl stop sprig. No backup/install attempted while active. Approval carries for the exact release; fresh stopped backup, install/server checks, DB/.env preservation and startup checks remain. Announcement preferences unchanged. Local closeout note, uncommitted.


## 2.2.0 installed — October 24, 2026, 7:56 a.m. Eastern
Graceful stop completed through user console and inactive verified. Fresh protected backup /home/discordbot/sprig-backups/20261024-115629 retains prior 0b7ecb7; SQLite integrity passed. Installed exact approved b90fbb784d2961a6fb8b42232f9928fcb4969fb6 / 2.2.0. Full report /home/discordbot/sprig-release-b90fbb7.json: 477 passed, zero skipped, exact-source hashes verified. Report-gated backup/server-checks.json: 42 passed. Dependencies and compilation passed. Stopped sprig.db and .env byte-match backup, announcement preferences unchanged. Installed SHA/version confirmed. sudo -n start requires password; user asked to run sudo systemctl start sprig in the opened console. Service inactive pending start; running/startup logs and fresh Discord main-screen/Claim/Done/Undo verification remain pending. No data restore. Local closeout note, uncommitted.


## Local 2.2.1 — caught-up Mine and Claim scope — October 24, 2026
User requested empty Mine say You’re caught up ✅ and Just this occurrence under Claim, with review before deployment. Implemented for unfiltered non-catalog Mine only; empty searches retain no-match explanation. Quiet scope cue appears immediately below the Claim row and not after Done. No domain or preference changes. Version/release notes updated to 2.2.1. Four relevant existing focused tests passed (sprig-2.2.1-copy-focused.json). Actual-source temporary-data review now includes 13 states with empty Mine at #screen-12 and Claim at #screen-8; both inspected, 21 components, narrow overflow none. Generator checks caught-up text exists and empty searches do not use it. No push/deployment or Discord message. Full final-source test report required before release.


## 2.2.1 fully tested and ready locally — October 24, 2026
User reviewed the two wording previews and requested full testing/preparation only, explicitly no deployment. Final exact-source report C:/Users/katie/.codex/automations/news/sprig-buttons/sprig-2.2.1-full.json: 477 passed, zero skipped, sources unchanged and fingerprints verified. Version and release summary/tests aligned at 2.2.1; diff hygiene passed. Includes empty unfiltered Mine reassurance and quiet Just this occurrence beneath Claim. Existing behavior and preferences unchanged. Actual-source review remains sprig-actual-main-review.html (#screen-12 empty Mine, #screen-8 Claim). No push, deployment, server/startup action or Discord message. Ready for exact release approval; fresh backup and server checks remain deployment-time work.
