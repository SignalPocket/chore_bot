# 2.3.1 — 2026-11-08

- Allow Every week · ongoing assignments while the recipient is away. Keep attendance checks for completing work, current-occurrence reassignment, and weekly eligibility. Preserve saved schedules, assignment conflicts, points/history, and stale-screen safeguards.

# 2.3.0 — 2026-11-08

- Restore Archive chore directly on the current Manage catalog (#13).
- Needs attention has a guarded Claim button beside each current occurrence and refreshes the list after claiming (#14). Four-row pages keep these controls within Discord limits.
- Quick Done on Mine and Dashboard opens your due-task list with inline Done buttons and the existing checklist, ownership, and duplicate-award protections (#15).
- Who’s home includes eligible cached chores-channel members, creates missing accounts without replacing scores/preferences, and distinguishes duplicate display names by Discord ID (#16). The person picker remains available for uncached members; complete membership discovery still depends on Discord member availability.
- Today’s calendar Details opens the actionable card directly, including dated claims and AM/PM chores (#17). Future dates keep date/shift controls.

# Sprig release notes

## 1.5.0

- Make the Version A daily sheet the private /chores entry: readable multi-chore text lists and one chore picker.
- Use compact work cards with protected Claim, Done, Skip, Need help, checklist and quiet Undo.
- Add native action icons; preserve Prev/Next arrows and personal settings return context.
- Support longer sheet preferences without expanding legacy dense-button screens beyond their component budgets.

## 1.4.1

- Group Chores controls, results, paging and management; retain visible Claim/Done and consistent right-side Edit.
- Settings Back restores the screen and filters that opened it, including after recovery.
- Replace separate Skip/Done undo buttons with one neutral Undo and a compact action description.

## 1.4.0

- Combine calendar, household assignments and catalog management in Chores, with Today, Week, All chores, people filters and search.
- Put personal preferences behind the gear and use Home / Refresh / Settings / Help headers.
- Keep native selectors compact and everyday Claim/Done/Skip/Need help visible; keep Undo last.

## 1.3.3

- Keep everyday chore actions visible; move occasional coordination and advanced editing to separate screens.
- Use plain < Prev / Next > page controls and << Prev day / Next day >> date controls without yellow squares.
- Put Manage chores catalog actions below the content.

## 1.3.2

- Final screen polish: concise card/attention help matches visible menus, old help paths corrected, and duplicate card Undo removed in favor of bottom Undo Done.

- Immediate bottom Undo Done reverses the latest unchanged completion while preserving atomic history/points safeguards.
- Use Archive consistently; distinguish Chore reminders from Trade alerts with separate help and preferences.

- Archived chores show a readable list and native restore dropdown instead of chore-name buttons.

- Needs attention places Details beside each chore, replacing the duplicate chore buttons underneath.

- Who’s home opens a paged household roster with current Home/Away status, schedule explanations, and inline Change controls.

- Reusable page templates plan titles with top-right ? help, toolbars, content, paging, actions, navigation, and Undo before rendering; shared limits validate the entire page.
- Keep common buttons visible; use named dropdowns for occasional card actions, Help topics, and filters. Chore-name buttons always open details; date selection is explicit.

- Reserve room for current and future Skip Undo controls on full lists, preventing Discord component-limit errors without losing chores or navigation.

- Manage chores opens all active chores directly, with inline Edit buttons, search, fixed paging, and return to the same search/page after saving.

## 1.3.1 - Installed

- Group chore-card actions by occurrence, responsibility, and schedule/details; keep navigation together and retain every existing action.

- Restore the earlier readable calendar rows with Details on the right; page help stays with navigation and cannot land inside a chore row.

## 1.3.0 - Installed

- clear screen names and a private contextual ? button on every screen, with Back and restart recovery; forms keep named titles and instructions on their launch screen.

- Direct one-occurrence Claim keeps its card open; shorter signup, checklist, person/option choice, home/away, and schedule-edit flows.
- Preselected exact recurring day/shift grid with one atomic Save; audited Home/Away today safely splits a longer trip.

- Purple dashboard accents and consistent Dashboard buttons; Claim/Done/Save actions use green; Skip/Undo/Drop actions use red. Previous/Next navigation has yellow markers; disabled boundaries remain disabled.
- One-time future date and AM/PM claims and skips with Undo; calendar, reminders, household views, and projected points follow the reservation.
- Keep current claims, saved recurring signups, completion history, and earned points separate from future reservations.


## 1.2.1 - Installed; restart and live Discord verification pending

- Skip immediately without a confirmation screen; undo from the bottom of chore lists or details before the next occurrence, provided the chore has not changed.
- Preserve skip and undo history, claims, schedule, points, and repeating signups.

## 1.2.0 - Installed; live Discord verification pending

- Button-only chore controls and repeating weekday or AM/PM signups that follow who is home.
- Short change summaries in automatic and manual update announcements.

## 1.1.0

- Skip this occurrence without points, loss of weekly reservations, or changes to the regular schedule.
- Correct the release version used in update notices.
- Require a version bump and release notes for every future release.

## 1.0

- Existing baseline with visible navigation and versioned update announcements.


### Prepared 1.5.0 addition: personal color markers
Added Settings → Your color, persistent per-account choices and household defaults, with markers beside workspace names. No marker remains available. Lavender uses purple and pink a heart because of Discord emoji limits. Local preparation only.


## 2.0.0 — Compact Discord rows
Daily-sheet rows use plain titles and middle-dot numbering, omit list points, and retain color markers and eight-row preference. Resolve visible account names before rendering; unresolved names use Assigned instead of mention chips. Full points and instructions remain on the work card. Reviewed through a private Discord preview.


### Pending scope highlight fix
Mine, Available and Everyone highlight the selected view with Discord primary style; other scope controls stay neutral. Local only, not deployed.


## 2.0.1 — Prepared refresh and scope highlights
Every workspace page has a compact Refresh button. Daily sheets and work cards now show Home, Refresh, Settings, Help consistently; refresh restores current context without repeating mutations. Mine/Available/Everyone highlight the selected scope. Not deployed.


## 2.0.2 — Prepared Done emoji fix
Replace the Done button’s plain check glyph with the supported check-mark emoji. Discord rejected the prior payload when opening assigned chore details (HTTP 400 / Invalid emoji). No domain or layout changes. Local only.


## Prepared 2.0.3 chore card
Claim/Done remain prominent with Back beside them. Sign up… groups available responsibility choices. More… opens a separate screen for occasional tools. Skip and neutral Need help remain visible below the main actions. Discord button sizes are fixed; quieter styling and placement reduce emphasis. Refresh and restart recovery preserve context. Local only, not deployed.


## 2.0.4 — Prepared Claim double-click layout fix
Unclaimed cards show Claim then Back. Cards offering Done show Back then Done, so Done no longer replaces Claim at the same click position. Deliberate completion and points guards are unchanged. Local only.


## 2.0.5 — Prepared inline More menu
Sign up… and More… are separate native dropdowns directly on the work card. Less-used tools open directly from More without the intermediate page. Existing saved More-page routes still recover safely. Claim/Done and Back positioning, neutral Need help, and guarded actions remain. Local only.


## Prepared 2.0.6 — one Chores destination
Dashboard and new starter messages expose one Chores destination. Older persistent My chores/Pick up chores buttons redirect to Chores → Mine/Available, and older household buttons redirect to Everyone. Existing private legacy callbacks and date/history tools remain available. Default work-card Back opens Chores → Mine. No push or deployment.


## Prepared 2.0.6 — inline personal settings
Your settings contains native color and list-length dropdowns, direct reminder and trade-alert toggles, and Change times opening a small native text-entry modal. Saves return to the same Settings page; Back keeps the opening screen. Reminder times/revisions use existing guarded validation; trade toggles reject stale state. No navigation-only preference buttons. Existing opt-ins are preserved unless the user changes them. Not deployed.


## 2.0.7 — Prepared drop return fix
Avoid adapting/rendering the same Components V2 screen twice through an interaction proxy. Fixes Discord rejecting the Chores return button after a saved drop. Already-rendered layout panels remain intact. Error guidance points to /chores. No responsibility or points-rule changes. Not deployed.


### Prepared name marker palette
Settings → Name marker offers extra red, white, black and brown dots plus star, flower, leaf, moon and paw-print symbols in the same chooser. Existing saved choices and household defaults remain unchanged. Symbols retain native emoji colors. No marker remains available. Local only.


### Prepared Other dates scope fix
Other dates carries Mine into the personal calendar and Everyone into the household calendar. Existing week/month/date navigation and recovery preserve that scope. Local only, not deployed.


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
