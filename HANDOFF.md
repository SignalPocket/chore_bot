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
