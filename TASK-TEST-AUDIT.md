# Task-oriented test audit

October 22, 2026 · 455-test exact-source offline pass is current. This document audits evidence and gaps; it does not claim the existing suite has been consolidated or every task individually tested.

## Evidence and follow-up checks

| Task area | Representative existing check | Important remaining check / boundary |
| --- | --- | --- |
| Start/recovery | `test_recovery_checklist_restores_its_card_and_original_filtered_page` | Nested forms, rejected input drafts, task-specific help text and routes need scenario checks beyond a visible ?. |
| Find work | `test_attention_inline_details_replace_bottom_chore_buttons` | Completed ambiguity is demonstrated by a standalone probe; turn approved semantics into a durable regression before fixing it. |
| Complete/Undo | `test_bottom_undo_done_immediate_private_atomic_and_repeat_safe` | Add combined dated-skip + normal-skip + Done Undo coexistence scenario; prevent callbacks from addressing the wrong saved event. |
| Stale completion correction | `test_bottom_undo_done_revalidates_after_points_change` | Also exercise timer rollover, archive, and points-reset interactions through the actual bottom control, not only the underlying undo function. |
| Repeating patterns | `test_repeating_schedule_buttons_cancel_private_recovery_and_stale_confirm` | Measure saved-pattern replacement and Clear selection path; keep opposite-home-week conflicts and another person’s untouched slots. |
| Assignment/trade | `test_reassign_occurrence_retains_points_history_and_blocks_stale` | Full user flow should include wrong scope, recipient lookup, declined/canceled/accepted cases, and explicit no-Undo accepted-trade guidance. |
| Catalog edit | `test_manage_direct_edit_prefills_saves_privately_and_rejects_stale_retry` | Check invalid fields preserve recoverable input once implemented; do not just assert an error exists. |
| Archive/restore | `test_removed_chores_readable_list_native_restore_dropdown` | Keep original identity, history, claims and restored completed state; archive search/paging remains distinct. |
| Attendance | `test_attendance_complete_edit_task_keeps_roster_parent_on_save_and_recovery` | Extend to mode changes, multi-person mixed defaults, canceled exceptions and the original source page across each branch. |
| Reminders/alerts | `test_clear_reminder_trade_labels_and_independent_preferences` | This saves settings but cannot prove real scheduled Discord DM delivery. Preserve the delivery-race/opt-in tests. |
| Calendar | `test_calendar_details_preview_back_and_recovery_keep_date_page_and_scope` | Add task-specific counts for future date/AM-PM selection and distant-week navigation, rather than snapshotting arbitrary button rows. |
| Owner recovery | `test_owner_recovery_review_reopen_confirmation_permissions_and_no_dm` | Apply-and-resolve remains separate. Author editing/retraction, threads and structured owner explanations are explicitly unnecessary; do not add tests that require those features. |
| Layout safety | `test_undo_dense_household_list_fits_and_remains_usable` | Keep actual wire component counting, guard every source callback, include temporary Undo choices. |

## Confirmed standalone probe

A daily chore was claimed and completed on October 22 in a temporary database. After advancing to October 23 and applying normal resets, its current completed flag was 0, but it was still included in My chores → Completed. Evidence: the probe output recorded `current_completed_flag: 0` and `shown_in_completed_tab: true`. No production data was read or changed. This is a confirmed ambiguity, not a chosen new product behavior.

## How to revise tests after the task design is approved

1. Map each high-value goal and alternate/error/correction scenario to a behavioral test. Keep related function-level checks where they prove atomicity and invariants.
2. Prefer real rendered controls, saved database result, safe return route and Undo/correction over checking labels alone.
3. Consolidate only tests with the same scenario and failure mechanism. Similar buttons across roles, scopes, time boundaries or concurrent changes are not duplicate coverage.
4. Keep a small layout contract for titles/help, stable paging, readable record actions, callback access guards and Discord component/text limits.
5. Avoid locking in accidental order, extra choice pages or unclear Completed semantics. Approve intended behavior first, then test it.
6. Do not use click count alone as a pass/fail budget until the exact scenario/start state and rendered selector style are specified.
7. Missing capabilities need an honest guard/help expectation, not tests asserting imaginary success.

No tests were removed during this audit. Product fixes and deliberate test consolidation remain separate reviewable follow-up work.
