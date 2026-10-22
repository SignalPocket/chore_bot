# User-task audit findings

October 22, 2026 · prepared 1.3.2, not deployed.

**190 individual user goals: 102 supported, 31 awkward, 37 missing, 20 intentionally unavailable.** The previous 16 items were task families; this audit expands them into concrete goals, success routes, mistake/correction paths and help destinations.

The inventory is comprehensive for the household product areas reviewed, not a claim that every conceivable new feature has been anticipated. Missing optional features are not automatic commitments. Source-derived effort counts are estimates; conditional choices and actual Discord rendering still need live validation.

## Read the artifacts

- [Full user-task ledger](USER-TASK-AUDIT.md): one status, steps, correction/cancellation, mistakes and help destination per goal.
- [Task data](USER-TASK-AUDIT.json): the same ledger in filterable structured form.
- [Help coverage](HELP-COVERAGE.md): task families → canonical topics; 53 screen-to-help mappings and specificity gaps.
- [Interface spec](INTERFACE-SPEC.md): shared screen/control contract.
- [Page map](PAGE-MAP.md): navigation topology.
- [Task-oriented test audit](TASK-TEST-AUDIT.md): representative behavioral evidence and remaining scenario coverage gaps.

## Most useful next fixes

1. **Clarify Completed.** A reset daily chore with current completed=0 still appears in Completed because an older non-undone completion exists. Confirmed with a temporary offline database, not just inferred. Choose between a completed-occurrence history and an explicitly named ever-completed chore view; do not silently test the current ambiguity as correct.
2. **Turn broad help into task help.** Card → Pick up a chore, Needs attention → Report a problem, and generic Confirm → Undo a mistake are often poor explanations of the current action. Help should preserve task/date/scope, with a task index and honest limits.
3. **Preserve failed-form input.** Invalid or stale submissions can require reopening and retyping. A recoverable prefilled edit would reduce work without weakening stale-state guards.
4. **Make correction behavior predictable.** Undo Done/Skip are immediate, but definition edits, reassignments, accepted trades and canceled attendance overrides require manual new changes. Label that difference and make the safe repair route explicit.
5. **Improve future-date navigation.** More dates advances a week rather than opening a date box; there is no global calendar date jump. This becomes costly for distant dates.
6. **Reduce owner review detours.** Applying a suggested score and resolving the review are separate operations. A reviewed preview/apply-and-resolve flow could preserve explicit choice while saving navigation.

## Important missing capabilities to triage, not automatically implement

- No per-chore/weekday reminder schedule, temporary mute, test-DM button or full user delivery-history screen.
- No member offboarding, saved named views, bulk catalog edits, definition version rollback or full change feed.
- No merge of split AM/PM histories, automatic vacation coverage redistribution, file import or report export through Discord.
- No arbitrary hourly due times, priorities or dependent/subassigned subtasks. Checklist steps are narrower.
- Current list-length UI supports only 1–5; a previous preference for ten is not implemented now.

## Accepted household scope

Katherine confirmed on October 22 that author feedback editing/retraction, threaded discussion, and structured owner decision explanations are unnecessary. These are intentionally out of scope, not gaps to implement. Existing feedback submission, reviewed/open status, resolution and reopening remain.

## Intentional restrictions to keep explicit in help

Future work cannot be completed early. Claims obey attendance. Required checklist steps gate Done. Personal/owner completion reversal is conservative, not arbitrary historical balance rewriting. Routine chore removal archives rather than deletes. Owner actions remain owner-only. Uncertain DMs are not blindly replayed. Discord limits actual button/text styling.

## Verification and boundaries

The current exact-source offline report passes **455 tests**. This is a code/flow audit plus a focused temporary-database probe; it is not a live exercise of all 190 goals. Related test families are not equivalent to one complete-task test for each row. No production database, settings, messages or GitHub state changed during this audit.

The next validation pass should select common/risky tasks, walk the real rendered controls, measure actual hops/activations/typing/waits and verify the stored result plus correction path. Keep permission, duplicate-tap, stale-state, rollover and component-limit cases when consolidating tests.

## High-priority task references

- [U017 · See my completed chores](USER-TASK-AUDIT.md#u017)
- [U003 · Find help for the current screen](USER-TASK-AUDIT.md#u003)
- [U099 · Correct invalid submitted form](USER-TASK-AUDIT.md#u099)
- [U090 · Reach dates beyond displayed week](USER-TASK-AUDIT.md#u090)
- [U155 · Apply point suggestion and mark handled](USER-TASK-AUDIT.md#u155)
- [U065 · Release all repeating slots](USER-TASK-AUDIT.md#u065)

## Inventory by area

| Area | Supported | Awkward | Missing | Intentionally unavailable |
| --- | --- | --- | --- | --- |
| Start and recovery | 6 | 3 | 2 | 1 |
| Find and understand work | 18 | 1 | 3 | 0 |
| Complete, skip and ask for help | 14 | 2 | 3 | 4 |
| Reserve, share and trade | 13 | 5 | 2 | 2 |
| Calendar and future work | 9 | 3 | 2 | 0 |
| Catalog and schedule maintenance | 10 | 8 | 4 | 1 |
| Attendance and trips | 9 | 4 | 3 | 0 |
| Reminders and alerts | 4 | 1 | 7 | 2 |
| Feedback and reviews | 6 | 1 | 0 | 4 |
| Points and fair workload | 10 | 1 | 4 | 2 |
| Operations, safety and other boundaries | 3 | 2 | 7 | 4 |
