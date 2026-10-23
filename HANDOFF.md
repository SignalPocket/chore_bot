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
