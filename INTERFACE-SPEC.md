# Sprig interface specification

Prepared 1.3.2 · October 22, 2026 · Local implementation, not deployed.

This is the behavioral contract for the interface. PAGE-MAP.md shows routes; this document states what screens and controls must accomplish. Conditional controls appear only when applicable. A passing offline check is not a live Discord verification.

See [full task audit](USER-TASK-AUDIT.md), [findings](TASK-AUDIT-FINDINGS.md), and [help coverage](HELP-COVERAGE.md) for task-by-task status and correction paths.

## Product rules

- People can find, claim, finish, skip, and coordinate chores through private controls. Shared changes are visible to the household.
- Completing work credits the completing Discord account. Skip, claim, drop, reassign, and trade do not award points.
- Each responsibility change must identify its scope: this occurrence, a dated occurrence/shift, this or next week, recurring weekdays/shifts, or ongoing ownership.
- Chore labels and instructions do not establish account ownership. Home/Away is a schedule, not Discord online presence.
- Normal household catalog and coordination tools are shared. Review inbox, points reset/recovery, other-person completion correction, and update announcements are owner only. Household setup follows its existing setup permission.
- Archive hides a chore while retaining history. Restore returns the existing chore. There is no routine permanent-delete control.
- Current work and future reservations are distinct. Future occurrences can be claimed/skipped but cannot be completed early.
- Actions validate current data before saving. A stale screen must not repeat an old mutation or overwrite someone else's changes.

## Shared controls, on every applicable screen

| Control | Purpose and required result |
| --- | --- |
| Page title | Say exactly where the person is; include chore/date/person context where needed. |
| ? | Open help for this screen from the top right; preserve a return route. |
| Back | Return to the saved parent; preserve supported list/date/filter/page context. It is navigation, not Undo. |
| Dashboard | Open the household start page; use the same primary color everywhere. |
| Refresh | Re-read current state or recover an expired screen. Never resubmit the old action. |
| Previous / Next | Change only the current list page; remain in fixed positions and disabled at boundaries. |
| Previous day / Next day | Change calendar date, not list page or a chore's schedule. |
| Today | Open today's Eastern date or period. |
| Confirm | Apply the change described on that confirmation screen, once and only if still valid. |
| Cancel | Leave that proposed change unapplied and return. Already-saved changes require their own recovery action. |
| Dropdown | Reveal occasional choices; selecting an action has the same access and stale-state checks as its former button. |
| Submit / Save / Apply | Validate the displayed fields/selections; save the named change and show success or a specific error. |
| Undo Done: chore | Immediately reverse the latest unchanged completion by this account; restore prior responsibility, points and streak state. No confirmation page. |
| Undo skip: chore/date | Immediately reverse the unchanged skip; preserve future repeats and signups; no points. |

Undo is conditional, not unlimited history editing. If later changes make reversal unsafe, retain those changes and explain why Undo was refused. History remains available after reversal.

## Start and navigation screens

| Screen | Purpose | Controls and destinations |
| --- | --- | --- |
| Dashboard | Choose a household task; show personal points/streak and relevant counts. | My chores → personal list; Pick up chores → available work; Needs attention → neglected work; Manage chores → catalog. Calendar → today; Household chores → shared assignments; Who's home? → attendance roster; Workload & pace → comparison; Trades → proposals. Chore reminders, Trade alerts, Points & standings, List length → personal settings/views. Owner tools appear only with permission. Continue where I left off restores saved context. |
| Help | Explain one task in short steps. | Help topic dropdown switches topics; navigation returns home/back. |
| Page help | Explain the screen just left. | All help topics → full Help; Back → original screen. |
| Choice picker | Choose a person or option when the original page cannot fit choices inline. | Option toggles select; Apply selection submits multi-select; Find a person opens a name search; paging changes choices; Back cancels navigation. |
| Confirmation | Review one consequential proposed action. | Confirm applies exactly the described proposal; Cancel preserves state. |

## Finding chores

| Screen | Purpose | Controls and expected behavior |
| --- | --- | --- |
| My chores | Work for the signed-in account. | Due now / This week / Next week / Upcoming / Completed change the time view. Chore name → details. Claim or Done acts on current occurrence when allowed; Skip skips current eligible occurrence; Choose date handles future work. Search/Filters narrow the list. |
| Pick up chores | Find work needing someone. | Due now / This week / Next week / All chores change scope. Chore name → details; Claim reserves this occurrence, not a whole week. The claimed chore remains accessible through the resulting flow. |
| Household chores | Inspect who owns work and what is unclaimed. | View / By person / By chore / By day change grouping; Unclaimed only / All change inclusion. Chore name → details. Search/Filters narrow records. |
| Needs attention | See overdue, unclaimed, and blocked chores together. | Details beside each row → its chore card. Show each chore once even when labels overlap. Today's due work is not automatically overdue. |
| Search | Search the current list. | Enter query and submit → originating list, page reset appropriately. Search changes no chore. |
| Filters | Filter by person, room, or date. | Person/room dropdown applies filter; On a date → date form; Clear filters removes query/person/room/date/unclaimed constraints. Back preserves the prior list. |
| Date filter | Pick the date used to filter occurrences. | Date/today/tomorrow; blank clears. Submit returns to a dated list; invalid dates explain the problem. |
| Grouping | Choose the shared list arrangement. | By person / By chore / By day returns to Household chores with that grouping. |
| List length | Set the account's preferred maximum records per page. | Choose a supported length; save preference for this account. Dense pages may show fewer records to fit Discord limits; paging must retain every record. |

## Chore and occurrence screens

| Screen | Purpose | Controls and expected behavior |
| --- | --- | --- |
| Chore details | Read responsibility, schedule, due/completed status, points, room, instructions, estimate/checklist. | Everyday actions stay visible. More options opens occasional coordination/history actions; Manage this chore opens advanced editing. Everyday actions remain visible. Back returns to the source list/calendar. |
| Signup options | Choose the duration of responsibility. | Just this occurrence claims only now; This week / Next week reserves the household week; repeating weekdays/shifts opens the recurring editor; ongoing ownership applies until changed where supported. |
| Repeating signup | Maintain one account's repeating weekday/AM/PM pattern. | Saved choices preselected; toggle slots; Save repeating days applies replacement once. Unselect slots and Save releases those slots; empty selection releases all of this account's pattern. Other accounts stay unchanged. |
| Choose occurrence | Select an exact future or current date. | Date buttons → shift picker or dated occurrence; More dates advances to the next household week; Current occurrence returns to the current card. This selection alone changes no schedule or ownership. |
| Choose shift | Disambiguate a dated AM/PM task. | AM / PM / All day opens that exact slot. |
| Dated occurrence | Act on exactly one day/shift. | Claim just this time reserves it when home/available; Skip just this time immediately skips it; Drop this dated claim releases that reservation. Open current chore opens the ordinary card. Future Done is unavailable. |
| Checklist | See and tick the required steps. | Each step toggles its recorded state; Done completes only when requirements allow; Open chore returns to details. |
| Help status | Explain why work is unfinished. | Stuck / Need supplies / Need help opens a note form; Mark resolved closes the active status after its review flow; Status history shows prior notes. Reporting does not drop or complete work and does not automatically DM someone. |
| Help history | Inspect recorded help/status changes. | Page controls navigate records; Back returns to the chore context. |
| Completion history | Inspect recorded work and corrections. | Select a completion for supported personal Undo or owner-assisted correction. Confirm corrections where requested; preserve original record and reversal audit. |

### Chore card action dictionary

| Action | Result / destination |
| --- | --- |
| Claim | Reserve this current occurrence for the acting account, with attendance/conflict checks. |
| Done | Complete this occurrence once, award its points, update streak/history, and offer bottom Undo Done when safe. |
| Checklist | Open the step list; incomplete required steps can prevent Done. |
| Skip this occurrence | Save immediate skip; no points; retain later repeats and weekly responsibility; offer Undo. Not available for one-time tasks. |
| Undo Done / history correction | Bottom Undo Done is the immediate shortcut. Completion history retains the reviewed correction route; the card does not duplicate the Undo button. |
| Stuck / need help | Open Help status for this occurrence. |
| Choose occurrence | Open date and shift selection without changing the regular schedule. |
| Signup options | Open duration choices. |
| Sign-up schedule | Edit saved repeating weekdays/shifts. |
| Take this week / Take next week | Reserve that specific household week when available. |
| Release this week / Release next week | Release only that weekly reservation. |
| Every week · ongoing | Set ongoing responsibility where eligible; does not replace someone else's repeating pattern. |
| Reassign | Choose a different account and explicit responsibility scope; confirm the guarded transfer. |
| Drop responsibility | Release the selected responsibility scope; recurring patterns may open their editor instead. |
| Propose trade | Open exchange choices; ownership does not change until acceptance. |
| Edit chore | Open prefilled name/points/instructions/room editing. |
| Change schedule | Open repeat pattern selection with schedule conflict guards. |
| Change regular day | Set/change a weekly chore's fixed weekday; undo by changing it again where allowed. |
| Move this occurrence | Enter one moved date; do not change the repeat pattern. |
| Cancel occurrence move | Confirm return to the regular schedule. |
| Estimate / checklist | Edit minutes estimate and checklist instructions; show validation errors without discarding the form silently. |
| Duplicate chore | Prefill a copy form; submit creates a separate chore with a separate identity. |
| Give feedback | Open feedback about instructions, timing, points or other concerns; suggestions do not automatically change the chore. |
| Completion history | Open recorded completion/correction list. |
| Separate AM and PM sign-ups | Confirm split of a twice-daily chore into independent shifts; preserve earned history and defined assignment migration. |

## Catalog screens and forms

| Screen | Purpose | Controls / result |
| --- | --- | --- |
| Manage chores | Browse the active catalog, including completed chores. | Edit beside a row opens its prefilled form; Search filters; Clear search restores all active records; Add chore starts creation; Archive chore / Archived chores open lifecycle lists. |
| Add chore schedule | Choose recurrence before entering details. | Frequency choices → weekday/repeat choices where required, then Add form. |
| Weekday / repeat choices | Configure schedule details. | Pick weekday or supported interval/pattern; continue to form or save guarded schedule change. |
| Add chore form | Enter chore name, points and instructions, with supported room fields. | Submit validates and creates once; default points are 5. Duplicate safeguards apply. |
| Edit chore chooser | Legacy/supporting route to edit an existing chore. | Choose chore; Edit details opens form; Change schedule opens pattern picker; Missed chores opens policy. |
| Edit chore form | Change existing details without losing ownership/history. | Prefilled fields; Save rejects stale snapshot and returns to saved catalog context where entered from Manage. |
| Missed chores | Choose what happens when a scheduled occurrence is missed. | Keep overdue preserves unfinished work; Skip if missed advances at the period boundary. |
| Regular day | Choose a fixed weekday for flexible weekly work. | Weekday selection and guarded save; changes when future work is due. |
| Archive chore | Hide an existing chore without deleting its record. | Readable list + chore dropdown; Confirm archive applies after selection; Archived chores switches lists. |
| Archived chores | Restore a hidden chore. | Readable list + restore dropdown; Restore makes it active; Active chores returns to active archive candidates. |
| Duplicate form | Create a new chore based on an existing one. | Review copied details and submit; original chore remains unchanged. |
| Estimate/checklist form | Edit effort and instructions together. | Save valid minutes/steps; later step progress remains governed by occurrence rules. |

## Assignment and trade screens

| Screen | Purpose | Controls / result |
| --- | --- | --- |
| Reassign | Give a selected scope to another person. | Select chore if not preselected, scope and person; Confirm reassignment transfers only that scope; Cancel leaves ownership. |
| Drop responsibility | Release the displayed occurrence/week/ongoing responsibility. | Confirm the stated scope; later unrelated signups/history remain. |
| Trade proposal | Offer work in exchange for another chore. | Choose recipient/exchange where offered; Propose trade records pending proposal; invalid/stale proposals are refused. |
| Trade inbox | Review requests to or from this account. | Select request; recipient Accept revalidates and swaps; Decline closes it; sender Cancel proposal withdraws. No points are transferred. |
| Weekly signup / responsibility views | Supporting shared weekly overview. | This week / Next week switches scope; select a chore/person; Sign up for week / Release week changes that week; Chore review opens relevant review tools. |

## Attendance screens

| Screen | Purpose | Controls / result |
| --- | --- | --- |
| Who's home | Show the known-household roster and scheduled Home/Away now. | Change beside each person selects their schedule; people picker supports multi-person changes; paging preserves roster context. |
| Selected person's schedule | Inspect defaults, exceptions and coverage. | Home today / Away today save immediately with audit; Mark home / Mark away open a date range; quick date shortcuts prefill; Usual schedule edits defaults; saved-exception picker opens one record; Weekly attendance opens week view. |
| Usual schedule | Set normal attendance for selected accounts. | Household default / Home every day / Away every day / selected home weekdays / same or opposite alternating weeks. Toggle weekdays when applicable; Save usual schedule validates stale multi-person changes atomically. |
| Trip/date form and preview | Override attendance for a date or inclusive range. | Enter dates/reason; preview and Confirm; reject overlap/stale edits rather than silently overwrite. |
| Saved exception | Inspect/change/cancel an existing override. | Edit dates opens prefilled form; Cancel exception confirms deactivation; history remains and defaults resume. |
| Weekly attendance | Inspect availability across the selected week. | Switch week/person as supported; open date exception controls; no automatic reassignment. |
| Household setup | Configure the alternating accounts and base rotation. | Select Kas/Zel accounts and saved rotation settings; Save household validates permissions and excludes bots. |

Attendance changes do not erase chores. Coverage remains visible. Dated exceptions take precedence over defaults and expire back to them; the default alternating handoff stays Sunday 6 p.m. Eastern.

## Calendar, messages, points and owner screens

| Screen | Purpose | Controls / result |
| --- | --- | --- |
| Calendar day | Work scheduled on one date, default today. | Details beside row → dated occurrence/current chore; Previous/Next page retain date; day controls change date; Week/Month switch scope. |
| Calendar week/month | Survey scheduled work. | Previous/Today/Next move period; day buttons open date; My calendar/Household switches ownership scope; No fixed day opens flexible work. |
| Chore reminders | Configure scheduled due-work DMs for this account. | Turn on/off; Change times opens up to 10 daily times. Away, empty, completed and changed work suppress inappropriate reminders. |
| Reminder times form | Edit the account's daily delivery times. | Save validates and displays actual stored times; invalid entries do not silently truncate. |
| Trade alerts | Configure new trade proposal DMs for this account. | Turn trade DMs on/off only changes proposal alerts. No daily schedule; requests remain in Trades even when alerts are off. |
| Points & standings | Show balance, streak and household rankings. | Paging browses people; owner Reset points and Reset history / Undo open protected recovery. |
| Workload & pace | Compare earned averages and projected responsibilities. | 7/28/90-day comparison; Sort cycles planned load/earned pace/name; How this is calculated explains denominators and uncertainty. |
| Reset points | Reset one person's or everyone's balance. | Choose target; Keep streaks / Reset streaks too sets scope; Confirm reset records audit; Cancel does nothing. |
| Reset history / Undo | Review recorded resets. | Select/page a reset; Undo points reset performs guarded restoration; reject when later changes make it unsafe. |
| Give feedback | Propose a chore improvement. | Enter comments, timing and suggested points; Save records review; owner notification/inbox does not auto-apply suggestion. |
| Owner review inbox | Process open/resolved feedback. | Open reviews / Resolved reviews switch queue; Open chore / Edit chore inspect/change separately; Resolve and next records review; Reopen review confirms return to open queue without a duplicate DM. |
| Update announcements | Control release notices. | Turn automatic on/off changes startup-update policy; Announce this update reviews/confirms the saved household channel and deduplicates a release attempt. Notices include version, time and brief change summary. |

## Complete-task acceptance checklist

For each task, verify the start, action, saved effect, return route, and correction path—not merely that a button exists.

| ID | Task and minimum acceptance | Existing offline evidence |
| --- | --- | --- |
| T01 | Find current/future work; open correct card; Back preserves context. | test_page_templates_chore_name_always_details_future_date_is_explicit |
| T02 | Claim current work, finish once, earn points on completer account. | test_workspace_chore_card_claim_done_and_safe_history |
| T03 | Undo Done immediately; restore points/streak/claim; reject wrong account, stale state and duplicate reversal. | test_bottom_undo_done_immediate_private_atomic_and_repeat_safe; test_bottom_undo_done_revalidates_after_points_change |
| T04 | Skip without points; Undo restores occurrence and preserves signups. | test_skip_undo_restores_claim_move_policy_and_preserves_signups |
| T05 | Pick exact future date/slot; reserve/skip only it; do not complete early. | Future-occurrence test group in test_chore_board.py |
| T06 | Save revised repeating days once; attendance respected; release saved slots without damaging others. | test_repeating_schedule_buttons_cancel_private_recovery_and_stale_confirm |
| T07 | Reassign/drop/trade correct scope; acceptance required; concurrent changes rejected. | Reassign/drop/trade integration groups in test_chore_board.py |
| T08 | Tick checklist, complete, view help status/history; no accidental points for a help note. | test_support_completion_hides_status_undo_restores_it |
| T09 | Create/edit/duplicate/archive/restore; retain earned history and other ownership. | test_remove_requires_confirmation_and_restore_keeps_data; test_manage_direct_edit_prefills_saves_privately_and_rejects_stale_retry |
| T10 | Inspect roster, change attendance/defaults, override trip dates, return and cancel exception. | test_home_overview_statuses_paging_change_and_back; test_shorter_home_today_preserves_surrounding_trip_and_is_atomic |
| T11 | Reminders and trade alerts save independently; delivery obeys current chore state. | test_clear_reminder_trade_labels_and_independent_preferences; reminder change/delivery groups |
| T12 | Feedback can be submitted, reviewed, resolved and reopened only by allowed people. | Review inbox and owner recovery groups in test_chore_board.py |
| T13 | Owner resets/corrects safely; history retained; other accounts refused. | Points reset/owner correction groups in test_chore_board.py |
| T14 | Expired screens recover place without replaying mutations. | test_recovery_checklist_restores_its_card_and_original_filtered_page; recovery integration group |
| T15 | Dense screens retain all content/actions, including simultaneous Undo controls. | test_undo_dense_household_list_fits_and_remains_usable; component-limit groups |
| T16 | Needs attention has inline Details and preserves page; archived list uses dropdown and Restore. | test_attention_inline_details_replace_bottom_chore_buttons; test_removed_chores_readable_list_native_restore_dropdown |

Verification snapshot: 455 offline tests passed, including the complete attendance edit/save/recovery task. New screen-map/spec text is documentation, not a new live verification. Pending release needs a fresh approved push/deployment and actual Discord smoke checks: open private Dashboard, current/future chore, Done/Undo, Skip/Undo, archive/restore, attendance, and both message settings. Delivery checks require actual scheduled/send conditions, not just saved preferences.

## Intentional limits and follow-up gaps

- Personal Undo Done reverses the latest unchanged completion, not arbitrary older work. Owner corrections retain safety checks; this is not unlimited history editing.
- Skip is unavailable for one-time chores. Drop releases responsibility; Archive hides the chore. These are different outcomes.
- Feedback suggestions do not change points/schedule automatically. Review and editing are separate actions. Author editing/retraction, threaded discussion and structured owner explanations are explicitly unnecessary for this household (Katherine, October 22); do not treat them as required gaps.
- Some supporting legacy pages remain internally named Remove/Notifications; public wording is Archive/Trade alerts. Internal compatibility identifiers are not product labels.
- Presence roster includes known saved household accounts and the viewer; it does not assume every server member belongs to the household.
- Back context is tested on key paths, not proven for every possible nested route. The audit found and corrected lost roster-page context through Usual schedule, including recovery and Save.
- Discord controls cannot supply arbitrary custom button colors. Use consistent available styles, readable names, and symbols.
- This spec does not assert a complete live usability audit or invented exact click counts. Use task IDs for future regression and usability checks.

## Next audit: task paths, effort, then tests

Use T01–T16 as the task inventory. Before assigning a count, record starting screen, preconditions (claimed/unclaimed, due/future, home/away, role), and selected page/date. Record the shortest valid path and a realistic recovery/correction path separately.

Count separately:

- **Page hops:** transitions between named screens. A same-screen refresh or state update is not a hop. Opening contextual Help is a hop.
- **Control activations:** each button press, dropdown opening, dropdown selection, checkbox/weekday toggle, form submission, and confirmation. A dropdown's open and choose are two interactions, even when they cause one transition.
- **Typing:** distinct fields and required values; do not call a form a single effortless click. Opening a modal is recorded separately from submitting it.
- **Waiting:** response/loading delay, deferred action, lookup, and another person's trade acceptance. Human waiting is not a page hop.
- **Detours:** manual Dashboard trips, lost filters/page/date, redundant selection, mandatory confirmation, or having to rediscover a just-claimed chore.

For every measured path, save: `Task ID | scenario/start | route | hops | activations | typed fields | waits | return/Undo route | evidence | proposed simplification`.

Do not publish a single universal click count for a conditional task. Separate common success, alternate scope, invalid/stale state, and correction paths. Counts inferred from source must be labeled source-derived; device-specific Discord observations require live measurements.

Then audit tests against these paths:

1. Keep behavioral coverage for permissions, action scope, points/history, repeat schedules, state conflicts, duplicate taps and recovery.
2. Prefer complete-task tests that follow real rendered controls, save the change, inspect stored state, and return/Undo.
3. Merge duplication only when assertions cover the same scenario and failure mechanism. Different account/scope/rollover cases are not redundant merely because they press the same button.
4. Keep a small explicit layout contract for title/help placement, stable paging/navigation, menu availability and Discord component limits.
5. Remove tests that preserve accidental button ordering or unnecessary screens. Do not weaken a behavioral test simply to accommodate a refactor.
6. Add a regression for every removed detour or broken end-to-end path. Do not freeze arbitrary click counts until the intended flow is approved.

Status: screen/control spec and task inventory prepared; full hop measurement and duplication audit are the next pass, not completed by writing this document.

## Change discipline

When adding a screen or control: assign its purpose and parent, state action scope and permissions, define persistence/Undo behavior, preserve safe recovery, update this spec/map/guide, and test the complete task affected. A route that displays choices but cannot finish the task fails the contract.

### Prepared 1.3.3 screen simplification
Chore details keeps Claim/Done, Checklist when present, Skip, Need help and Choose date visible. More options opens coordination/history/feedback; Manage this chore there opens editing. Undo remains last. Manage catalog actions follow content. Page controls use < Prev / Next >; day controls use << Prev day / Next day >>, with no yellow-square emoji. Local candidate, not deployed.

## Local combined Chores review — October 22, 2026
Not deployed. Dashboard now has one Chores destination replacing Calendar, Household chores and Manage chores. Chores offers Today, Week and All chores; a person filter, search, date/page navigation, direct Claim/Done and Edit, Add chore and Archived chores. The gear opens personal List length, Chore reminders and Trade alerts only. Header order is Home, Refresh, Settings, Help on the new Chores, chore details/advanced actions, personal settings and Dashboard screens. Older saved routes remain recoverable. Three chore rows per page maximum reserve room within Discord component limits. Live Discord validation remains pending.

## Compact screen pass — October 23, 2026, local review
All adapted screens now use Home, Refresh, personal Settings, Help in that order in the header; Back remains below when relevant and temporary Undo stays last. Native dropdowns/person selectors remain compact instead of expanding into button walls. Occasional/advanced chore actions use clearly named selectors on their separate screens. Claim/Done, Skip, Need help and Checklist remain visible on chore details. Dense list capacity reserves the complete header footprint. Search in projected calendar lists uses canonical chore records. No push/deployment authorized for this pass.

## Version A actual interface — prepared 1.5.0, October 23, 2026
Local candidate, not deployed. Private /chores opens a text-first daily sheet: Mine / Available / Everyone, a readable multi-chore list, one chooser for the work card, unchanged Prev/Next arrows, Other dates, Manage chores and personal Settings. New-account sheet length defaults to 8; existing saved preferences stay intact; Settings supports 1–10. Legacy dense lists retain their protected capacity cap.

The compact work card keeps Claim, Done, Skip, Need help and required Checklist visible, with native action icons. Other actions uses named guarded callbacks for coordination, editing, dates and history. Help/status warnings and chore instructions remain visible. Back to list preserves the parent context; Settings Back and recovery do likewise. One neutral latest-eligible Undo remains last. Catalog editing, archive/restore, search, and Household tools remain available through Manage chores. Public text-command launcher behavior is preserved; private slash entry uses the new sheet. Prototype HTML remains separate from actual source validation. No push/deployment authorization for 1.5.0.


## Personal name colors
Settings → Your color saves a personal marker, visible beside your name to everyone on refreshed workspace screens. Defaults: Dar lavender (purple dot), John blue, Kas pink (heart), Z/Zel orange, ginaria green. Discord has no standard lavender/pink circle emoji. Choose another color or No marker. Exact household display names/usernames provide initial defaults only; saved choices belong to Discord account IDs and override defaults. No responsibility, points, list length or notification preferences change.


Daily-sheet rows are compact plain text: number · chore · person/color (Everyone). Points remain on the work card. Long titles can still wrap in narrow Discord clients. Existing list-length preference remains; eight is the new-account default.


## Prepared 2.0.3 chore card
Claim/Done remain prominent with Back beside them. Sign up… groups available responsibility choices. More… opens a separate screen for occasional tools. Skip and neutral Need help remain visible below the main actions. Discord button sizes are fixed; quieter styling and placement reduce emphasis. Refresh and restart recovery preserve context. Local only, not deployed.


The current work card has separate Sign up… and More… dropdowns directly below the primary actions. More opens the selected tool directly, without an intermediate tools page.


## Prepared 2.0.6 — one Chores destination
Dashboard and new starter messages expose one Chores destination. Older persistent My chores/Pick up chores buttons redirect to Chores → Mine/Available, and older household buttons redirect to Everyone. Existing private legacy callbacks and date/history tools remain available. Default work-card Back opens Chores → Mine. No push or deployment.


## Prepared 2.0.6 — inline personal settings
Your settings contains native color and list-length dropdowns, direct reminder and trade-alert toggles, and Change times opening a small native text-entry modal. Saves return to the same Settings page; Back keeps the opening screen. Reminder times/revisions use existing guarded validation; trade toggles reject stale state. No navigation-only preference buttons. Existing opt-ins are preserved unless the user changes them. Not deployed.


Calendar scope controls are now consistently visible as Mine / Everyone directly below the header on week, month and day views. The selected scope is highlighted; changing dates or restoring the view retains it. Other dates inherits Mine or Everyone from the Chores sheet. Not deployed.


## Prepared 2.0.8 — native chore detail card
Chore details separates app navigation from a native accented card containing task name, status/points, instructions and visible help warnings. Everyday controls appear under Actions; signup/tools remain separate dropdowns. Quiet result messages follow controls, with Undo last. Claim/Back → Back/Done position safety is preserved. Local review only, not deployed.


### Prepared organized chore menus
More orders related tools under People, Schedule, Edit, Review and History prefixes, with native icons and short descriptions on actual selectable actions. Sign up describes each responsibility scope. No selectable fake headings, no intermediate navigation, and original guarded callbacks remain in use. Local only.


## Prepared 2.1.0 — household help reporting
Any authorized household member may report Stuck, Need supplies or Need help on an unfinished, non-archived chore, including unclaimed or not-yet-due work. Reporting does not claim/complete/reassign the chore or award points, and sends no automatic DM. Shared-note history, validation and stale-state guards remain. Completed/archived/unavailable chores explain why reporting is closed. Includes pending native card and organized-menu refinements. Local only, not deployed.


## Prepared 2.1.1 — single chore Actions menu
Chore cards combine signups and occasional tools in one Actions dropdown. Signups come first, followed by People, Schedule, Edit, Review and History; all choices retain icons, descriptions and original guarded callbacks. Claim/Done and Back remain outside the menu with existing double-click safety positions. Completed chores explain why Claim and Done are unavailable. Local review only, not deployed.


## Prepared 2.1.2 — drop returns directly to Chores
Successful Confirm drop now opens Chores directly with a short result notice. The intermediary Chores-button screen is removed from that success path. Ownership, stale-state checks, history and earned points are preserved; cancellation and failure paths remain unchanged. Local only, not deployed.


### Action-first labels in local 2.1.2
Approved menu refinement: action names lead; categories move into the retained descriptions. People/Schedule choices use a native category icon plus a distinct action icon in the label where useful; other choices retain one icon. Related ordering and original callbacks unchanged. Refreshed actual-source approximate local review; 9 focused menu/drop tests passed (sprig-action-labels-focused.json), narrow overflow none. Includes pending direct-drop return. No push/deployment. Full exact-source release testing remains required.


## Prepared 2.1.3 — finished chore cards
Completed chore cards show Done — nice work!, Completed instructions in secondary text and a quiet next-return line. Back to chores is the primary button; the existing latest-eligible Undo stays small and neutral at the bottom. Claim/Done/Skip/Need help controls are absent from completed cards; the described Actions menu retains occasional tools. Active chore cards and completion/points/schedule/undo rules are unchanged. Local review only.


### Short Done confirmation in local 2.1.3
Approved refinement: immediately after a successful completion, show only the checked chore name, Done — nice work!, awarded points and quiet return date, with primary Back to chores and the existing quiet Undo. No instructions or Actions menu in this immediate receipt. Reopening the chore still exposes completed details/tools. No automatic navigation or domain changes. Two focused completion/menu tests passed, including real completion, Undo and reopened tools (sprig-short-done-focused.json). Actual-source approximate preview refreshed: completion uses 15 components, narrow overflow none, image inspected. No push/deployment; full final-source testing remains required.


## Prepared 2.2.0 — consistent main chore screens
Chores uses one compact native list card with Mine, Available, Everyone and Needs attention in a fixed toolbar. Eight items remain the default; existing personal list-length settings are preserved. Other dates uses the same four views and day arrows, preserving scope through paging, Back, Settings and recovery. Existing week/month Calendar remains available under Week calendar. On future dates Needs attention shows projected unclaimed work; current-day overdue/help labels are never projected into the future. Today uses the existing attention classification and normal schedule reset rules.
Completed work leaves today’s active lists; Undo restores it and future occurrences remain projected normally. The immediate Done receipt shows the checked name, points, return date, Back to chores and quiet Undo; reopening retains details/tools. Claim/Back and Back/Done positions keep double-click safety. One described Actions menu retains signup and advanced callbacks. Settings remains direct controls behind the gear with visible Back. Manage chores uses an eight-item catalog card with a direct native edit-form chooser and management actions below content; Household tools remains available. Notices sit below paging, not above the title. No live preferences, points, schedules or announcement choices are changed by preparing this interface. Local only, not pushed/deployed.

Catalog editing opens the existing prefilled native form directly and returns to the same catalog context after saving. Cancel leaves the catalog in place; validation and stale-snapshot checks still apply.


## Prepared 2.2.1 — caught up and Claim scope
Unfiltered empty Mine says “You’re caught up ✅”. Empty searches keep the no-match explanation. Work cards show “Just this occurrence” directly below the Claim row; Done cards do not show this cue. Claim, signup and completion behavior is unchanged. Local review only, not deployed.
