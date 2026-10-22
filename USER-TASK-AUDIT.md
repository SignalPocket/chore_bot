# Sprig full user-task audit

October 22, 2026 · prepared 1.3.2 · local implementation, not deployed.

This expands the former 16 task families into individual household-user goals. It covers daily use, planning, maintenance, personal settings, feedback, recovery and owner operations. It cannot enumerate every imaginable feature; missing optional capabilities are not automatic roadmap commitments.

## Status and evidence rules

- **Supported:** a complete route exists for this stated scenario, with an available correction or an explicit safe refusal.
- **Awkward:** achievable through meaningful detours, poor discovery, manual repair, retyping or limited recovery.
- **Missing:** no complete user-facing route. A script or workaround with different semantics does not count.
- **Intentionally unavailable:** current code deliberately blocks it for integrity, permission, platform or scope reasons. The stated reason can be reconsidered; it is not an eternal product decision.

**Snapshot and evidence:** source inspection plus the existing exact-source 455-test offline pass. The whole ledger has not been exercised live in Discord and not every row has a dedicated test. Source-family references identify what was inspected, not proof of exhaustive behavior coverage. This audit changes documentation, not live household data.

## Counting effort

Routes start from an already-open Dashboard with the named item on the first relevant page, a fresh screen, and the required permission/home/due state. The /chores entry task is the exception. Paging, finding a member, changing preselected options and additional checklist steps add effort.

**Hops / controls** are source-derived baseline estimates. Hops count transitions between named screens, not same-screen refresh. Opening a modal is a control activation and is listed separately in the route. Read/typing steps are not counted as button activations. Dropdown opening and selecting count separately when shown. Adaptive inline choices may remove a dropdown opening; exact device-specific budgets need rendered/live measurements. Do not mistake these baseline estimates for universal measured click counts.

Common mistake handling for every saved action: inspect returned state; never blindly repeat an uncertain save; Refresh reads without replay; wrong-account actions must fail; stale changes must not overwrite other work; Cancel/closing a modal stops unsaved work only; Back is navigation, not Undo. Per-task limits below apply in addition.


## Inventory totals

**190 individual goals**: 102 supported, 31 awkward, 37 missing, 20 intentionally unavailable.

## Start and recovery

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U001](#u001) | Open private controls | Supported | 1 / 1 |
| [U002](#u002) | Know what screen I am on | Supported | 0 / 0 |
| [U003](#u003) | Find help for the current screen | Awkward | 1 / 1 |
| [U004](#u004) | Find instructions for a task | Awkward | 3 / 4 |
| [U005](#u005) | Return without changing work | Supported | 3 / 3 |
| [U006](#u006) | Go home | Supported | 3 / 3 |
| [U007](#u007) | Resume after restart or expiry | Supported | 1 / 1 |
| [U008](#u008) | Refresh after someone changes a chore | Supported | 2 / 3 |
| [U009](#u009) | Recover after save succeeds but Discord reply fails | Awkward | 2 / 2 |
| [U010](#u010) | Navigate using breadcrumbs or a selectable page history | Missing | — |
| [U011](#u011) | Search help by my own task wording | Missing | — |
| [U012](#u012) | Use someone else's private controls | Intentionally unavailable | — |

<a id="u001"></a>

### U001 · Open private controls

**Supported**

**Steps:** 1. Run /chores → Dashboard.

**Undo / correction / cancellation:** Close/reopen /chores.

**Mistakes / limits:** Old public boards and private messages may be stale.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u002"></a>

### U002 · Know what screen I am on

**Supported**

**Steps:** 1. Read heading.

**Undo / correction / cancellation:** Back or Dashboard.

**Mistakes / limits:** Forms have their own titles; labels are not always task names.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u003"></a>

### U003 · Find help for the current screen

**Awkward**

**Steps:** 1. ? beside title.

**Undo / correction / cancellation:** Back returns to parent.

**Mistakes / limits:** Many screen types map to broad topics; full help specificity is not complete.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u004"></a>

### U004 · Find instructions for a task

**Awkward**

**Steps:** 1. ? → 2. All help topics → 3. Open topic dropdown → 4. Choose topic.

**Undo / correction / cancellation:** Back returns; Dashboard restarts.

**Mistakes / limits:** No help search; related tasks share topics.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u005"></a>

### U005 · Return without changing work

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Back.

**Undo / correction / cancellation:** Reopen chore.

**Mistakes / limits:** Back is not Undo and cannot cancel an already-saved action.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u006"></a>

### U006 · Go home

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Dashboard.

**Undo / correction / cancellation:** Continue where I left off when offered.

**Mistakes / limits:** Does not reverse data changes.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u007"></a>

### U007 · Resume after restart or expiry

**Supported**

**Steps:** 1. Continue where I left off.

**Undo / correction / cancellation:** Refresh or reopen /chores.

**Mistakes / limits:** Saved context is restored against current data, never replayed.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u008"></a>

### U008 · Refresh after someone changes a chore

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Refresh.

**Undo / correction / cancellation:** Review current state before retry.

**Mistakes / limits:** A stale action should be refused, not overwrite another person's work.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u009"></a>

### U009 · Recover after save succeeds but Discord reply fails

**Awkward**

**Steps:** 1. Open fresh /chores → 2. Affected list → 3. Inspect saved state.

**Undo / correction / cancellation:** Do not repeat until inspected.

**Mistakes / limits:** No universal action-receipt inbox.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u010"></a>

### U010 · Navigate using breadcrumbs or a selectable page history

**Missing**

**No complete supported route:** No breadcrumb/history selector.

**Undo / correction / cancellation:** Use Back/Dashboard/resume.

**Mistakes / limits:** Only saved route context is available.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u011"></a>

### U011 · Search help by my own task wording

**Missing**

**No complete supported route:** No full-text help search.

**Undo / correction / cancellation:** Choose nearest topic.

**Mistakes / limits:** Topic selection is not task search.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

<a id="u012"></a>

### U012 · Use someone else's private controls

**Intentionally unavailable**

**No complete supported route:** Owner-bound interactions reject another account.

**Undo / correction / cancellation:** Open own /chores.

**Mistakes / limits:** Private controls do not grant another person's identity.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Dashboard, View, Guide, PageHelp; chore_recovery.py.

## Find and understand work

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U013](#u013) | See my due chores | Supported | 1 / 1 |
| [U014](#u014) | See this week's responsibilities | Supported | 1 / 2 |
| [U015](#u015) | See next week's responsibilities | Supported | 1 / 2 |
| [U016](#u016) | See upcoming work | Supported | 1 / 2 |
| [U017](#u017) | See my completed chores | Awkward | 1 / 2 |
| [U018](#u018) | Find available work | Supported | 1 / 1 |
| [U019](#u019) | See all active chores | Supported | 1 / 2 |
| [U020](#u020) | Search chores by text | Supported | 2 / 3 |
| [U021](#u021) | Filter by responsible person | Supported | 3 / 4 |
| [U022](#u022) | Filter by room | Supported | 3 / 4 |
| [U023](#u023) | Filter by exact date | Supported | 3 / 4 |
| [U024](#u024) | Clear all filters | Supported | 3 / 3 |
| [U025](#u025) | See who does what | Supported | 1 / 1 |
| [U026](#u026) | Arrange household list by chore | Supported | 3 / 3 |
| [U027](#u027) | Arrange household list by day | Supported | 3 / 3 |
| [U028](#u028) | Show unclaimed household chores only | Supported | 1 / 2 |
| [U029](#u029) | Find overdue, unclaimed and blocked work together | Supported | 1 / 1 |
| [U030](#u030) | Read instructions, owner and effort | Supported | 2 / 2 |
| [U031](#u031) | Change list length from 1 to 5 | Supported | 1 / 2 |
| [U032](#u032) | Choose ten or more list items per page | Missing | — |
| [U033](#u033) | Save several named custom views | Missing | — |
| [U034](#u034) | Receive live list updates without refreshing | Missing | — |

<a id="u013"></a>

### U013 · See my due chores

**Supported**

**Steps:** 1. My chores.

**Undo / correction / cancellation:** Switch view or Dashboard.

**Mistakes / limits:** Due now is not automatically overdue.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u014"></a>

### U014 · See this week's responsibilities

**Supported**

**Steps:** 1. My chores → 2. This week.

**Undo / correction / cancellation:** Due now returns.

**Mistakes / limits:** Household week changes Sunday 6 p.m. Eastern.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u015"></a>

### U015 · See next week's responsibilities

**Supported**

**Steps:** 1. My chores → 2. Next week.

**Undo / correction / cancellation:** This week returns.

**Mistakes / limits:** Today's single claim does not reserve next week.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u016"></a>

### U016 · See upcoming work

**Supported**

**Steps:** 1. My chores → 2. Upcoming.

**Undo / correction / cancellation:** Choose date before changing future work.

**Mistakes / limits:** A repeat is not automatically a dated reservation.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u017"></a>

### U017 · See my completed chores

**Awkward**

**Steps:** 1. My chores → 2. Completed.

**Undo / correction / cancellation:** Open details/history for correction.

**Mistakes / limits:** The Completed filter includes chores with a recorded non-undone completion, not necessarily only currently completed occurrences. Use history for dates; recurring chores can be due again.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u018"></a>

### U018 · Find available work

**Supported**

**Steps:** 1. Pick up chores.

**Undo / correction / cancellation:** Change time scope.

**Mistakes / limits:** Only matching eligible records appear.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u019"></a>

### U019 · See all active chores

**Supported**

**Steps:** 1. Pick up chores → 2. All chores.

**Undo / correction / cancellation:** Due now narrows list.

**Mistakes / limits:** Archived chores are in Manage separately.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u020"></a>

### U020 · Search chores by text

**Supported**

**Steps:** 1. My chores → 2. Search → 3. Enter query → 4. Submit → list.

**Undo / correction / cancellation:** Clear filters or change query.

**Mistakes / limits:** Empty search is not evidence of deletion; input required.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

**Typing:** Enter query.

<a id="u021"></a>

### U021 · Filter by responsible person

**Supported**

**Steps:** 1. My chores → 2. Filters → 3. Open person picker → 4. Select person → list.

**Undo / correction / cancellation:** Clear filters.

**Mistakes / limits:** Native picker vs inline choices changes activation count.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u022"></a>

### U022 · Filter by room

**Supported**

**Steps:** 1. My chores → 2. Filters → 3. Open room picker → 4. Select room → list.

**Undo / correction / cancellation:** Clear filters.

**Mistakes / limits:** Only saved nonempty rooms are offered.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u023"></a>

### U023 · Filter by exact date

**Supported**

**Steps:** 1. My chores → 2. Filters → 3. On a date → 4. Enter date → 5. Submit → list.

**Undo / correction / cancellation:** Blank date or Clear filters.

**Mistakes / limits:** Invalid date errors; form may need reopening.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

**Typing:** Enter date.

<a id="u024"></a>

### U024 · Clear all filters

**Supported**

**Steps:** 1. My chores → 2. Filters → 3. Clear filters → list.

**Undo / correction / cancellation:** Reapply desired filters.

**Mistakes / limits:** Also clears search/person/room/unclaimed state.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u025"></a>

### U025 · See who does what

**Supported**

**Steps:** 1. Household chores.

**Undo / correction / cancellation:** Switch grouping.

**Mistakes / limits:** Saved account ownership, not a name written in chore title.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u026"></a>

### U026 · Arrange household list by chore

**Supported**

**Steps:** 1. Household chores → 2. View grouping → 3. By chore.

**Undo / correction / cancellation:** By person switches back.

**Mistakes / limits:** Changes view only.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u027"></a>

### U027 · Arrange household list by day

**Supported**

**Steps:** 1. Household chores → 2. View grouping → 3. By day.

**Undo / correction / cancellation:** Switch grouping.

**Mistakes / limits:** Flexible weekly/monthly work has no fixed day yet.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u028"></a>

### U028 · Show unclaimed household chores only

**Supported**

**Steps:** 1. Household chores → 2. Unclaimed only.

**Undo / correction / cancellation:** All restores inclusion.

**Mistakes / limits:** Ownership depends on selected date/attendance.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u029"></a>

### U029 · Find overdue, unclaimed and blocked work together

**Supported**

**Steps:** 1. Needs attention.

**Undo / correction / cancellation:** Details opens row; Back retains page.

**Mistakes / limits:** One chore appears once even with several labels.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u030"></a>

### U030 · Read instructions, owner and effort

**Supported**

**Steps:** 1. My chores → 2. Chore name → details.

**Undo / correction / cancellation:** Back returns to list.

**Mistakes / limits:** Person named in title is not a Discord assignment.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u031"></a>

### U031 · Change list length from 1 to 5

**Supported**

**Steps:** 1. List length → 2. Choose length.

**Undo / correction / cancellation:** Choose prior preference.

**Mistakes / limits:** Dense screens may show fewer than maximum, with all records paged.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u032"></a>

### U032 · Choose ten or more list items per page

**Missing**

**No complete supported route:** Current selector offers only 1–5.

**Undo / correction / cancellation:** Use paging.

**Mistakes / limits:** Earlier longer-list preference is not supported now.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u033"></a>

### U033 · Save several named custom views

**Missing**

**No complete supported route:** No named-view manager.

**Undo / correction / cancellation:** Recent area state is remembered.

**Mistakes / limits:** One remembered state is not a collection of named views.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

<a id="u034"></a>

### U034 · Receive live list updates without refreshing

**Missing**

**No complete supported route:** No live push refresh of old private messages.

**Undo / correction / cancellation:** Refresh.

**Mistakes / limits:** Current private screens can become stale.

**Task help:** Pick up a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Browse, Search, Filters, Groups, Attention; browse/attention/recovery tests.

## Complete, skip and ask for help

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U035](#u035) | Claim current work once | Supported | 2 / 2 |
| [U036](#u036) | Complete due work from list | Supported | 1 / 2 |
| [U037](#u037) | Complete from details | Supported | 2 / 3 |
| [U038](#u038) | See points after finishing | Supported | 1 / 2 |
| [U039](#u039) | Immediately undo latest Done | Supported | 1 / 2 |
| [U040](#u040) | Undo my completion through history | Awkward | 5 / 7 |
| [U041](#u041) | Undo older completion despite newer score activity | Intentionally unavailable | — |
| [U042](#u042) | Skip recurring work now | Supported | 1 / 2 |
| [U043](#u043) | Undo current skip | Supported | 1 / 2 |
| [U044](#u044) | Skip a one-time chore | Intentionally unavailable | — |
| [U045](#u045) | Report being stuck | Supported | 4 / 5 |
| [U046](#u046) | Report missing supplies | Supported | 4 / 5 |
| [U047](#u047) | Ask for help | Supported | 4 / 5 |
| [U048](#u048) | Read blocked-status history | Supported | 4 / 4 |
| [U049](#u049) | Resolve blocked status | Supported | 5 / 5 |
| [U050](#u050) | Tick/uncheck a checklist step | Supported | 3 / 4 |
| [U051](#u051) | Finish a required checklist | Supported | 3 / 5 |
| [U052](#u052) | Complete with required steps unchecked | Intentionally unavailable | — |
| [U053](#u053) | Complete future work early | Intentionally unavailable | — |
| [U054](#u054) | Repair a skip after Undo expires | Awkward | 3 / 4 |
| [U055](#u055) | Snooze a chore/reminder for a few hours | Missing | — |
| [U056](#u056) | Attach proof photos to completion | Missing | — |
| [U057](#u057) | Track actual start/stop working time | Missing | — |

<a id="u035"></a>

### U035 · Claim current work once

**Supported**

**Steps:** 1. Pick up chores → 2. Claim → details.

**Undo / correction / cancellation:** Drop selected responsibility scope.

**Mistakes / limits:** Taken/away/stale claim denied; not a weekly signup.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u036"></a>

### U036 · Complete due work from list

**Supported**

**Steps:** 1. My chores → 2. Done.

**Undo / correction / cancellation:** Bottom Undo Done.

**Mistakes / limits:** Checklist/away/due conditions can block Done.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u037"></a>

### U037 · Complete from details

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Done.

**Undo / correction / cancellation:** Bottom Undo Done.

**Mistakes / limits:** Repeat taps must not earn points twice.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u038"></a>

### U038 · See points after finishing

**Supported**

**Steps:** 1. My chores → 2. Done → 3. Read refreshed total.

**Undo / correction / cancellation:** Undo Done reverses award when safe.

**Mistakes / limits:** Completer account gets points, not merely the assigned person.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u039"></a>

### U039 · Immediately undo latest Done

**Supported**

**Steps:** 1. My chores → 2. Undo Done at bottom.

**Undo / correction / cancellation:** Done again after valid reversal.

**Mistakes / limits:** Only latest unchanged completion and score/chore state.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u040"></a>

### U040 · Undo my completion through history

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Completion history → 5. Open completion picker → 6. Choose record → confirmation → 7. Confirm → history.

**Undo / correction / cancellation:** Cancel confirmation; complete again if eligible.

**Mistakes / limits:** Older choices can be shown but safely refused.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u041"></a>

### U041 · Undo older completion despite newer score activity

**Intentionally unavailable**

**No complete supported route:** Guard refuses arbitrary points/streak rewind.

**Undo / correction / cancellation:** Owner can inspect but same safety rule applies.

**Mistakes / limits:** No unlimited historical deletion.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u042"></a>

### U042 · Skip recurring work now

**Supported**

**Steps:** 1. My chores → 2. Skip.

**Undo / correction / cancellation:** Bottom Undo skip.

**Mistakes / limits:** No points; later repeats and weekly responsibility preserved.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u043"></a>

### U043 · Undo current skip

**Supported**

**Steps:** 1. My chores → 2. Undo skip at bottom.

**Undo / correction / cancellation:** Skip again.

**Mistakes / limits:** Original actor/unchanged occurrence only; expiry can block.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u044"></a>

### U044 · Skip a one-time chore

**Intentionally unavailable**

**No complete supported route:** One-time Skip is disabled/rejected.

**Undo / correction / cancellation:** Drop to unclaim; Archive to hide.

**Mistakes / limits:** Skip is not delete or postpone.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u045"></a>

### U045 · Report being stuck

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Stuck / need help → 4. Stuck → 5. Enter note → 6. Submit → status.

**Undo / correction / cancellation:** Resolve/update note.

**Mistakes / limits:** No completion, points or automatic help DM.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

**Typing:** Enter note.

<a id="u046"></a>

### U046 · Report missing supplies

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Stuck / need help → 4. Need supplies → 5. Enter note → 6. Submit → status.

**Undo / correction / cancellation:** Resolve when supplied.

**Mistakes / limits:** Does not create shopping/order task.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

**Typing:** Enter note.

<a id="u047"></a>

### U047 · Ask for help

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Stuck / need help → 4. Need help → 5. Enter note → 6. Submit → status.

**Undo / correction / cancellation:** Update or resolve.

**Mistakes / limits:** Household must inspect; no guaranteed helper notification.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

**Typing:** Enter note.

<a id="u048"></a>

### U048 · Read blocked-status history

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Stuck / need help → 4. Status history.

**Undo / correction / cancellation:** Back.

**Mistakes / limits:** History is not a discussion thread.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u049"></a>

### U049 · Resolve blocked status

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Stuck / need help → 4. Mark resolved → confirmation → 5. Confirm → status.

**Undo / correction / cancellation:** Report again; no dedicated Undo resolve.

**Mistakes / limits:** Task still unfinished unless completed separately.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u050"></a>

### U050 · Tick/uncheck a checklist step

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Checklist → 4. Toggle step.

**Undo / correction / cancellation:** Toggle same step back.

**Mistakes / limits:** Stale changes must not overwrite new occurrence.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u051"></a>

### U051 · Finish a required checklist

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Checklist → 4. Toggle remaining step → 5. Done.

**Undo / correction / cancellation:** Undo Done; uncheck before finish when allowed.

**Mistakes / limits:** One step assumed; add one toggle per remaining step.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u052"></a>

### U052 · Complete with required steps unchecked

**Intentionally unavailable**

**No complete supported route:** Checklist gate blocks completion.

**Undo / correction / cancellation:** Check requirements or intentionally edit definition.

**Mistakes / limits:** This is a completion rule, not a missing button.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u053"></a>

### U053 · Complete future work early

**Intentionally unavailable**

**No complete supported route:** Future occurrence has no early Done.

**Undo / correction / cancellation:** Wait until due.

**Mistakes / limits:** Future claim/skip remains allowed.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u054"></a>

### U054 · Repair a skip after Undo expires

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Inspect schedule → 4. Open Schedule & details → 5. Move this occurrence.

**Undo / correction / cancellation:** Manual schedule/responsibility repair only where applicable.

**Mistakes / limits:** No guaranteed rewind after expiry. Moving the new occurrence does not restore the expired one; inspect history and avoid duplicate awards.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u055"></a>

### U055 · Snooze a chore/reminder for a few hours

**Missing**

**No complete supported route:** No hourly Snooze.

**Undo / correction / cancellation:** Move date or change reminders with different effects.

**Mistakes / limits:** Not equivalent to snoozing one occurrence.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u056"></a>

### U056 · Attach proof photos to completion

**Missing**

**No complete supported route:** No completion attachment form.

**Undo / correction / cancellation:** Use household conversation outside bot.

**Mistakes / limits:** History stores records, not photo proof.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

<a id="u057"></a>

### U057 · Track actual start/stop working time

**Missing**

**No complete supported route:** Only estimates exist.

**Undo / correction / cancellation:** Use external timer.

**Mistakes / limits:** Estimate is not measured effort.

**Task help:** Finish a chore; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Card, Browse, LayoutPanel; chore_history.py; chore_planning.py: Checklist, HelpStatus.

## Reserve, share and trade

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U058](#u058) | Reserve this week | Supported | 2 / 4 |
| [U059](#u059) | Reserve next week | Supported | 2 / 4 |
| [U060](#u060) | Release a weekly reservation | Supported | 2 / 4 |
| [U061](#u061) | Set ongoing responsibility | Supported | 2 / 4 |
| [U062](#u062) | Reserve only Mondays | Supported | 3 / 6 |
| [U063](#u063) | Reserve only AM or PM | Supported | 3 / 6 |
| [U064](#u064) | Replace Monday with Wednesday | Supported | 3 / 7 |
| [U065](#u065) | Release all repeating slots | Supported | 3 / 6 |
| [U066](#u066) | Share a slot on opposite home weeks | Supported | 3 / 6 |
| [U067](#u067) | Reassign current occurrence | Awkward | 4 / 8 |
| [U068](#u068) | Reassign this week's signup | Awkward | 4 / 8 |
| [U069](#u069) | Reassign ongoing responsibility | Awkward | 4 / 8 |
| [U070](#u070) | Transfer someone's entire repeating pattern | Missing | — |
| [U071](#u071) | Drop my current responsibility | Awkward | 4 / 6 |
| [U072](#u072) | Drop a future dated claim | Supported | 4 / 5 |
| [U073](#u073) | Propose chore exchange | Awkward | 4 / 7 |
| [U074](#u074) | Accept incoming trade | Supported | 2 / 4 |
| [U075](#u075) | Decline trade | Supported | 2 / 4 |
| [U076](#u076) | Cancel outgoing pending trade | Supported | 2 / 4 |
| [U077](#u077) | Trade without recipient acceptance | Intentionally unavailable | — |
| [U078](#u078) | Offer an open trade to any volunteer | Missing | — |
| [U079](#u079) | Claim while scheduled away | Intentionally unavailable | — |

<a id="u058"></a>

### U058 · Reserve this week

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Take this week.

**Undo / correction / cancellation:** Release same week.

**Mistakes / limits:** Does not reserve next week; availability/conflicts checked.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u059"></a>

### U059 · Reserve next week

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Take next week.

**Undo / correction / cancellation:** Release next week.

**Mistakes / limits:** Current week/history unchanged.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u060"></a>

### U060 · Release a weekly reservation

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Release this week.

**Undo / correction / cancellation:** Take again if still available.

**Mistakes / limits:** Other weeks and repeating patterns stay saved.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u061"></a>

### U061 · Set ongoing responsibility

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Every week · ongoing.

**Undo / correction / cancellation:** Drop/reassign ongoing scope.

**Mistakes / limits:** Not available for incompatible recurring slot ownership.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u062"></a>

### U062 · Reserve only Mondays

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Sign-up schedule → 5. Toggle Monday → 6. Save repeating days (same editor).

**Undo / correction / cancellation:** Unselect Monday and Save.

**Mistakes / limits:** Saved slots preselected; add toggles for desired days.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u063"></a>

### U063 · Reserve only AM or PM

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Sign-up schedule → 5. Toggle weekday/shift → 6. Save repeating days (same editor).

**Undo / correction / cancellation:** Unselect shift and Save.

**Mistakes / limits:** Only supported AM/PM schedules offer shifts; home dates apply.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u064"></a>

### U064 · Replace Monday with Wednesday

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Sign-up schedule → 5. Unselect Monday → 6. Select Wednesday → 7. Save repeating days (same editor).

**Undo / correction / cancellation:** Restore old toggles and Save.

**Mistakes / limits:** One Save replaces this account's pattern.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u065"></a>

### U065 · Release all repeating slots

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Sign-up schedule → 5. Clear selection → 6. Save repeating days (same editor).

**Undo / correction / cancellation:** Reselect and Save if available.

**Mistakes / limits:** Clear selection is available; Save commits release. Other people’s patterns remain.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u066"></a>

### U066 · Share a slot on opposite home weeks

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Sign-up schedule → 5. Select slot → 6. Save repeating days (same editor).

**Undo / correction / cancellation:** Release own slots or correct attendance.

**Mistakes / limits:** Overlapping home dates can cause conflicts needing coverage.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u067"></a>

### U067 · Reassign current occurrence

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Reassign → 5. Choose occurrence scope → 6. Open recipient picker → 7. Select person → 8. Confirm reassignment → result.

**Undo / correction / cancellation:** Reassign back manually.

**Mistakes / limits:** Recipient, home state, scope and stale ownership validated.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u068"></a>

### U068 · Reassign this week's signup

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Reassign → 5. Choose week scope → 6. Open recipient picker → 7. Select person → 8. Confirm → result.

**Undo / correction / cancellation:** Transfer same week back if still valid.

**Mistakes / limits:** Other weeks/history remain.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u069"></a>

### U069 · Reassign ongoing responsibility

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Reassign → 5. Choose ongoing scope → 6. Open recipient picker → 7. Select person → 8. Confirm → result.

**Undo / correction / cancellation:** Reassign ongoing scope back.

**Mistakes / limits:** Not a whole repeating-weekday-pattern transfer.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u070"></a>

### U070 · Transfer someone's entire repeating pattern

**Missing**

**No complete supported route:** No pattern-transfer action.

**Undo / correction / cancellation:** People edit slots; cover one occurrence with Reassign.

**Mistakes / limits:** Occurrence transfer is different scope.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u071"></a>

### U071 · Drop my current responsibility

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Drop responsibility → 5. Review scope → 6. Confirm release → result.

**Undo / correction / cancellation:** Claim again if available.

**Mistakes / limits:** Underlying weekly/repeating owner may still apply; scope matters.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u072"></a>

### U072 · Drop a future dated claim

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Choose occurrence → 4. Select reserved date → 5. Drop this dated claim.

**Undo / correction / cancellation:** Claim just this time again if available.

**Mistakes / limits:** Does not release whole-week signup.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u073"></a>

### U073 · Propose chore exchange

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Responsibility → 4. Propose trade → 5. Open exchange picker → 6. Select exchange → 7. Propose → result.

**Undo / correction / cancellation:** Cancel pending proposal in Trades.

**Mistakes / limits:** Recipient acceptance is an additional human wait; no immediate swap.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u074"></a>

### U074 · Accept incoming trade

**Supported**

**Steps:** 1. Trades → 2. Open request picker → 3. Select proposal → 4. Accept trade.

**Undo / correction / cancellation:** Reverse trade/reassign; no one-click Undo accepted trade.

**Mistakes / limits:** Ownership and attendance rechecked at acceptance.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u075"></a>

### U075 · Decline trade

**Supported**

**Steps:** 1. Trades → 2. Open request picker → 3. Select proposal → 4. Decline.

**Undo / correction / cancellation:** New proposal can be sent.

**Mistakes / limits:** Neither chore changes.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u076"></a>

### U076 · Cancel outgoing pending trade

**Supported**

**Steps:** 1. Trades → 2. Open request picker → 3. Select outgoing proposal → 4. Cancel proposal.

**Undo / correction / cancellation:** Create new proposal.

**Mistakes / limits:** Cannot withdraw already accepted swap as pending.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u077"></a>

### U077 · Trade without recipient acceptance

**Intentionally unavailable**

**No complete supported route:** Trade requires acceptance.

**Undo / correction / cancellation:** Use explicit Reassign for direct transfer.

**Mistakes / limits:** Shared Reassign has different consent semantics.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u078"></a>

### U078 · Offer an open trade to any volunteer

**Missing**

**No complete supported route:** No open marketplace.

**Undo / correction / cancellation:** Drop/claim or propose to named person.

**Mistakes / limits:** Dropping is not an exchange proposal.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

<a id="u079"></a>

### U079 · Claim while scheduled away

**Intentionally unavailable**

**No complete supported route:** Availability checks reject unavailable claims/signups.

**Undo / correction / cancellation:** Correct mistaken attendance first.

**Mistakes / limits:** Do not bypass availability with chore-name text.

**Task help:** Drop, reassign, or trade; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: ClaimChoices, Card; chore_board.py: ReassignView, DropChoreView, TradeOfferView, TradeInboxView; repeating/dated test groups.

## Calendar and future work

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U080](#u080) | Open calendar today | Supported | 1 / 1 |
| [U081](#u081) | Go to next/previous calendar day | Supported | 2 / 2 |
| [U082](#u082) | Page through chores on one date | Supported | 1 / 2 |
| [U083](#u083) | Survey week/month | Supported | 2 / 2 |
| [U084](#u084) | See only my calendar | Supported | 2 / 3 |
| [U085](#u085) | Find flexible chores with no date | Awkward | 3 / 3 |
| [U086](#u086) | Open a future day/shift | Supported | 4 / 4 |
| [U087](#u087) | Claim exactly one future date | Supported | 4 / 5 |
| [U088](#u088) | Skip exactly one future date | Supported | 4 / 5 |
| [U089](#u089) | Undo a future-date skip | Supported | 4 / 5 |
| [U090](#u090) | Reach dates beyond displayed week | Awkward | 5 / 5 |
| [U091](#u091) | Jump to arbitrary calendar date/month | Missing | — |
| [U092](#u092) | Drag calendar chore to new date | Missing | — |
| [U093](#u093) | Read past calendar as historical record | Awkward | 3 / 3 |

<a id="u080"></a>

### U080 · Open calendar today

**Supported**

**Steps:** 1. Calendar → today.

**Undo / correction / cancellation:** Today returns after browsing.

**Mistakes / limits:** Eastern date.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u081"></a>

### U081 · Go to next/previous calendar day

**Supported**

**Steps:** 1. Calendar → today → 2. Next day.

**Undo / correction / cancellation:** Previous day.

**Mistakes / limits:** Different from next list page.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u082"></a>

### U082 · Page through chores on one date

**Supported**

**Steps:** 1. Calendar → today → 2. Next page.

**Undo / correction / cancellation:** Previous page.

**Mistakes / limits:** Date unchanged; disabled boundaries do nothing.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u083"></a>

### U083 · Survey week/month

**Supported**

**Steps:** 1. Calendar → today → 2. Week or Month.

**Undo / correction / cancellation:** Choose a day.

**Mistakes / limits:** Projection, not a schedule editor.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u084"></a>

### U084 · See only my calendar

**Supported**

**Steps:** 1. Calendar → today → 2. Week → 3. My calendar.

**Undo / correction / cancellation:** Household switches back.

**Mistakes / limits:** Today defaults to household scope.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u085"></a>

### U085 · Find flexible chores with no date

**Awkward**

**Steps:** 1. Calendar → today → 2. Week → 3. No fixed day.

**Undo / correction / cancellation:** Back; assign regular day where eligible.

**Mistakes / limits:** Flexible work cannot always be reserved by exact date.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u086"></a>

### U086 · Open a future day/shift

**Supported**

**Steps:** 1. Calendar → today → 2. Next day → 3. Details → 4. AM/PM if required.

**Undo / correction / cancellation:** Back retains date/page.

**Mistakes / limits:** Single-slot chores omit shift picker; baseline assumes two shifts.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u087"></a>

### U087 · Claim exactly one future date

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Choose occurrence → 4. Select date/slot → 5. Claim just this time.

**Undo / correction / cancellation:** Drop this dated claim.

**Mistakes / limits:** Does not claim today or later repeats.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u088"></a>

### U088 · Skip exactly one future date

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Choose occurrence → 4. Select date/slot → 5. Skip just this time.

**Undo / correction / cancellation:** Undo skip for this occurrence.

**Mistakes / limits:** No points; saved signups intact.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u089"></a>

### U089 · Undo a future-date skip

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Choose occurrence → 4. Select skipped date → 5. Undo skip for this occurrence.

**Undo / correction / cancellation:** Skip again.

**Mistakes / limits:** Original actor/unchanged record; expiry applies.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u090"></a>

### U090 · Reach dates beyond displayed week

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Choose occurrence → 4. More dates → next week → 5. Select date.

**Undo / correction / cancellation:** Back/current occurrence.

**Mistakes / limits:** More dates advances weeks; not a free date-entry form.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u091"></a>

### U091 · Jump to arbitrary calendar date/month

**Missing**

**No complete supported route:** No global calendar date-jump form.

**Undo / correction / cancellation:** Period navigation; list date filter is separate.

**Mistakes / limits:** List filter does not move calendar.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u092"></a>

### U092 · Drag calendar chore to new date

**Missing**

**No complete supported route:** No drag/drop.

**Undo / correction / cancellation:** Details → Move this occurrence.

**Mistakes / limits:** Viewing a date doesn't reschedule.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

<a id="u093"></a>

### U093 · Read past calendar as historical record

**Awkward**

**Steps:** 1. Calendar → today → 2. Previous day → 3. Details.

**Undo / correction / cancellation:** Completion history for actual records.

**Mistakes / limits:** Calendar projects current definitions/owners, not frozen historical schedules.

**Task help:** Future occurrences; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: OccurrenceDates, FutureSlots, FutureOccurrence; chore_planning.py: Day, Calendar; dated/calendar tests.

## Catalog and schedule maintenance

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U094](#u094) | Create daily chore at default 5 points | Supported | 3 / 4 |
| [U095](#u095) | Create flexible weekly chore | Supported | 3 / 4 |
| [U096](#u096) | Create fixed-weekday chore | Awkward | 4 / 5 |
| [U097](#u097) | Create one-time chore | Supported | 3 / 4 |
| [U098](#u098) | Edit name/instructions/points/room | Supported | 2 / 3 |
| [U099](#u099) | Correct invalid submitted form | Awkward | 2 / 5 |
| [U100](#u100) | Set or change time estimate | Supported | 3 / 5 |
| [U101](#u101) | Create or revise checklist definition | Supported | 3 / 5 |
| [U102](#u102) | Duplicate a chore with its definition | Awkward | 4 / 6 |
| [U103](#u103) | Change recurrence pattern | Awkward | 4 / 6 |
| [U104](#u104) | Choose regular weekday for weekly chore | Awkward | 4 / 6 |
| [U105](#u105) | Return fixed weekday to flexible weekly | Awkward | 4 / 6 |
| [U106](#u106) | Move current occurrence to another date | Supported | 4 / 6 |
| [U107](#u107) | Cancel a moved occurrence date | Supported | 4 / 5 |
| [U108](#u108) | Change missed-work policy | Awkward | 5 / 6 |
| [U109](#u109) | Split twice-daily chore into AM and PM | Awkward | 4 / 5 |
| [U110](#u110) | Merge two shifts into one chore | Missing | — |
| [U111](#u111) | Archive a chore without losing history | Supported | 4 / 5 |
| [U112](#u112) | Restore archived chore | Supported | 4 / 5 |
| [U113](#u113) | Bulk edit/archive several chores | Missing | — |
| [U114](#u114) | Import chore list from a file through Discord | Missing | — |
| [U115](#u115) | Restore old instructions/points/schedule version | Missing | — |
| [U116](#u116) | Permanently erase chore and its earned history | Intentionally unavailable | — |

<a id="u094"></a>

### U094 · Create daily chore at default 5 points

**Supported**

**Steps:** 1. Manage chores → 2. Add chore → 3. Choose Daily → 4. Enter name → 5. Submit → result.

**Undo / correction / cancellation:** Archive unintended new chore.

**Mistakes / limits:** Name required; points/notes can use defaults.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter name.

<a id="u095"></a>

### U095 · Create flexible weekly chore

**Supported**

**Steps:** 1. Manage chores → 2. Add chore → 3. Choose Weekly → 4. Enter name → 5. Submit → result.

**Undo / correction / cancellation:** Edit schedule or Archive.

**Mistakes / limits:** Weekly is not a chosen weekday.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter name.

<a id="u096"></a>

### U096 · Create fixed-weekday chore

**Awkward**

**Steps:** 1. Manage chores → 2. Add chore → 3. Choose weekday pattern → 4. Choose weekday → 5. Enter name → 6. Submit → result.

**Undo / correction / cancellation:** Change regular day or Archive.

**Mistakes / limits:** Extra pattern/weekday choice; varies by schedule option.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter name.

<a id="u097"></a>

### U097 · Create one-time chore

**Supported**

**Steps:** 1. Manage chores → 2. Add chore → 3. Choose One-time → 4. Enter name → 5. Submit → result.

**Undo / correction / cancellation:** Archive; not recurring Skip.

**Mistakes / limits:** No next scheduled repeat.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter name.

<a id="u098"></a>

### U098 · Edit name/instructions/points/room

**Supported**

**Steps:** 1. Manage chores → 2. Edit beside chore → 3. Edit fields → 4. Save → catalog.

**Undo / correction / cancellation:** Edit back manually.

**Mistakes / limits:** Stale form rejected; no definition-version Undo.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Edit fields.

<a id="u099"></a>

### U099 · Correct invalid submitted form

**Awkward**

**Steps:** 1. Manage chores → 2. Open form → 3. Enter invalid value → 4. Submit → 5. Read error → 6. Reopen form → 7. Correct value → 8. Submit → result.

**Undo / correction / cancellation:** Cancel unsaved form.

**Mistakes / limits:** Input can need retyping; no universal draft recovery.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter invalid value; Correct value.

<a id="u100"></a>

### U100 · Set or change time estimate

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Estimate / checklist → 5. Enter minutes → 6. Submit → card.

**Undo / correction / cancellation:** Reopen and revise/clear as supported.

**Mistakes / limits:** Estimate is not measured time.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter minutes.

<a id="u101"></a>

### U101 · Create or revise checklist definition

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Estimate / checklist → 5. Enter steps → 6. Submit → card.

**Undo / correction / cancellation:** Edit definition again.

**Mistakes / limits:** Definition edits differ from toggling this occurrence's progress.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter steps.

<a id="u102"></a>

### U102 · Duplicate a chore with its definition

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Duplicate chore → 5. Enter new name → 6. Submit → preview → 7. Confirm → new card.

**Undo / correction / cancellation:** Cancel preview; Archive accidental copy.

**Mistakes / limits:** Copies settings/instructions, not claims/signups/history/checked progress.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter new name.

<a id="u103"></a>

### U103 · Change recurrence pattern

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Change schedule → 5. Choose pattern → 6. Review fields → 7. Save → result.

**Undo / correction / cancellation:** Restore old pattern through new edit.

**Mistakes / limits:** Existing future/recurring ownership may block incompatible change.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u104"></a>

### U104 · Choose regular weekday for weekly chore

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Change regular day → 5. Select weekday → 6. Save day → result.

**Undo / correction / cancellation:** Choose another day; flexible Weekly via Change schedule.

**Mistakes / limits:** Changes everyone's regular schedule, not one person's occurrence.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u105"></a>

### U105 · Return fixed weekday to flexible weekly

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Change schedule → 5. Choose Weekly → 6. Review fields → 7. Save → result.

**Undo / correction / cancellation:** Set a regular day again.

**Mistakes / limits:** No Clear day control in weekday chooser.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u106"></a>

### U106 · Move current occurrence to another date

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Move this occurrence → 5. Enter date → 6. Submit → confirmation → 7. Confirm → card.

**Undo / correction / cancellation:** Cancel occurrence move → Confirm.

**Mistakes / limits:** Regular recurrence remains; stale moves rejected.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

**Typing:** Enter date.

<a id="u107"></a>

### U107 · Cancel a moved occurrence date

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Cancel occurrence move → confirmation → 5. Confirm → card.

**Undo / correction / cancellation:** Move again.

**Mistakes / limits:** Returns to regular schedule if state unchanged.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u108"></a>

### U108 · Change missed-work policy

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Edit chore → 5. Missed chores → 6. Keep overdue or Skip if missed → result.

**Undo / correction / cancellation:** Switch back explicitly.

**Mistakes / limits:** Policy button saves immediately; no separate Save. Switching to Skip can advance already-overdue work. Indirect route through edit chooser.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u109"></a>

### U109 · Split twice-daily chore into AM and PM

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Separate AM and PM sign-ups → 5. Confirm → card.

**Undo / correction / cancellation:** No merge action; manual edits require care.

**Mistakes / limits:** Specific migration of claims/history/AM vs PM owners; not reversible toggle.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u110"></a>

### U110 · Merge two shifts into one chore

**Missing**

**No complete supported route:** No merge migration.

**Undo / correction / cancellation:** Manually edit/archive preserving history.

**Mistakes / limits:** Manual cleanup is not merge of both histories.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u111"></a>

### U111 · Archive a chore without losing history

**Supported**

**Steps:** 1. Manage chores → 2. Archive chore → 3. Open dropdown → 4. Choose chore → 5. Confirm archive → list.

**Undo / correction / cancellation:** Archived chores → select → Restore.

**Mistakes / limits:** Points/history/identity retained.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u112"></a>

### U112 · Restore archived chore

**Supported**

**Steps:** 1. Manage chores → 2. Archived chores → 3. Open dropdown → 4. Choose chore → 5. Restore → list.

**Undo / correction / cancellation:** Archive again.

**Mistakes / limits:** Restores same chore; does not create copy.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u113"></a>

### U113 · Bulk edit/archive several chores

**Missing**

**No complete supported route:** No multi-select batch editor.

**Undo / correction / cancellation:** Edit individually.

**Mistakes / limits:** No bulk preview or transactional Undo.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u114"></a>

### U114 · Import chore list from a file through Discord

**Missing**

**No complete supported route:** No file-import workflow.

**Undo / correction / cancellation:** Add individually or separately reviewed maintenance tools.

**Mistakes / limits:** Server scripts are not a member-facing import feature.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u115"></a>

### U115 · Restore old instructions/points/schedule version

**Missing**

**No complete supported route:** No definition revision browser/rollback.

**Undo / correction / cancellation:** Manually edit known prior values.

**Mistakes / limits:** Completion/feedback snapshots aren't editable version history.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

<a id="u116"></a>

### U116 · Permanently erase chore and its earned history

**Intentionally unavailable**

**No complete supported route:** Routine deletion archives.

**Undo / correction / cancellation:** Archive/Restore.

**Mistakes / limits:** No destructive hard-delete household UI.

**Task help:** Add, edit, or copy chores; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Manage; chore_board.py: AddChoreModal, EditChoreView, RemoveChoreView, ChooseDayView, MissedChoreView; chore_planning.py: PlanModal, DuplicateModal.

## Attendance and trips

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U117](#u117) | See who is scheduled home now | Supported | 1 / 1 |
| [U118](#u118) | Change normal home/away schedule | Supported | 4 / 5 |
| [U119](#u119) | Set home on selected weekdays | Supported | 4 / 6 |
| [U120](#u120) | Restore household attendance default | Supported | 4 / 5 |
| [U121](#u121) | Mark person away today | Supported | 2 / 3 |
| [U122](#u122) | Mark person home today | Supported | 2 / 3 |
| [U123](#u123) | Plan a multi-day trip | Awkward | 4 / 5 |
| [U124](#u124) | Trade home/away days due to trip | Awkward | 4 / 5 |
| [U125](#u125) | Edit trip dates | Supported | 5 / 7 |
| [U126](#u126) | Cancel attendance exception | Supported | 5 / 6 |
| [U127](#u127) | Apply one attendance change to multiple people | Awkward | 4 / 6 |
| [U128](#u128) | Inspect next-week availability | Awkward | 3 / 4 |
| [U129](#u129) | Start saving attendance for a new Discord person | Supported | 4 / 6 |
| [U130](#u130) | Offboard former household member everywhere | Missing | — |
| [U131](#u131) | Keep immutable historical attendance after default edits | Missing | — |
| [U132](#u132) | Automatically redistribute work during absence | Missing | — |

<a id="u117"></a>

### U117 · See who is scheduled home now

**Supported**

**Steps:** 1. Who’s home?.

**Undo / correction / cancellation:** Change opens person.

**Mistakes / limits:** Uses saved schedules/known accounts, not Discord presence.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u118"></a>

### U118 · Change normal home/away schedule

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Usual schedule → 4. Choose daily/alternating mode → 5. Save → person.

**Undo / correction / cancellation:** Restore previous default explicitly.

**Mistakes / limits:** Current defaults aren't historical snapshots; historical pace denominators can change. Schedule mode choice is a native/inline selector depending on render capacity; add an opening activation when native.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u119"></a>

### U119 · Set home on selected weekdays

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Usual schedule → 4. Home on selected weekdays → 5. Toggle weekday → 6. Save → person.

**Undo / correction / cancellation:** Restore former pattern.

**Mistakes / limits:** One weekday toggle assumed; add one per extra change.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u120"></a>

### U120 · Restore household attendance default

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Usual schedule → 4. Use household default → 5. Save → person.

**Undo / correction / cancellation:** Choose custom schedule again.

**Mistakes / limits:** Kas/Zel alternate; other people default home daily.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u121"></a>

### U121 · Mark person away today

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Away today.

**Undo / correction / cancellation:** Home today or edit/cancel relevant exception.

**Mistakes / limits:** Immediate save; responsibilities do not disappear.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u122"></a>

### U122 · Mark person home today

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Home today.

**Undo / correction / cancellation:** Away today or edit/cancel relevant exception.

**Mistakes / limits:** Changing state back is not guaranteed restoration of previously absent override.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u123"></a>

### U123 · Plan a multi-day trip

**Awkward**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Mark away → 4. Enter dates/reason → 5. Submit → preview → 6. Confirm → person.

**Undo / correction / cancellation:** Saved exception → Cancel exception → Confirm.

**Mistakes / limits:** Inclusive dates; overlap requires editing existing exception.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

**Typing:** Enter dates/reason.

<a id="u124"></a>

### U124 · Trade home/away days due to trip

**Awkward**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Mark home/away → 4. Enter dates/reason → 5. Submit → preview → 6. Confirm → person.

**Undo / correction / cancellation:** Edit/cancel each required override.

**Mistakes / limits:** No single transaction exchanging two people's two dates.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

**Typing:** Enter dates/reason.

<a id="u125"></a>

### U125 · Edit trip dates

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Open saved exception picker → 4. Select exception → 5. Edit dates → 6. Enter dates → 7. Submit → preview → 8. Confirm → person.

**Undo / correction / cancellation:** Edit again/cancel.

**Mistakes / limits:** Stale and overlapping changes refused; record history retained.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

**Typing:** Enter dates.

<a id="u126"></a>

### U126 · Cancel attendance exception

**Supported**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Open saved picker → 4. Select exception → 5. Cancel exception → 6. Confirm → person.

**Undo / correction / cancellation:** Create equivalent new override if needed.

**Mistakes / limits:** No direct Undo cancel; normal defaults resume.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u127"></a>

### U127 · Apply one attendance change to multiple people

**Awkward**

**Steps:** 1. Who’s home? → 2. Open people picker → 3. Select people → 4. Mark away → 5. Enter dates/reason → 6. Submit → preview → 7. Confirm → people.

**Undo / correction / cancellation:** Edit/cancel saved records individually.

**Mistakes / limits:** Overlap/mixed profiles can require individual edits.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

**Typing:** Enter dates/reason.

<a id="u128"></a>

### U128 · Inspect next-week availability

**Awkward**

**Steps:** 1. Who’s home? → 2. Change beside person → 3. Weekly attendance → 4. Next week.

**Undo / correction / cancellation:** This week/Back.

**Mistakes / limits:** Extra route; viewing a week does not change defaults.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u129"></a>

### U129 · Start saving attendance for a new Discord person

**Supported**

**Steps:** 1. Who’s home? → 2. Open people picker → 3. Select member → 4. Usual schedule → 5. Choose default → 6. Save → person.

**Undo / correction / cancellation:** Adjust profile later.

**Mistakes / limits:** Roster inferred from saved records; no explicit member directory.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u130"></a>

### U130 · Offboard former household member everywhere

**Missing**

**No complete supported route:** No member archive/offboarding workflow.

**Undo / correction / cancellation:** Mark away; reassign work; keep history.

**Mistakes / limits:** Away-every-day does not remove account from rosters.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u131"></a>

### U131 · Keep immutable historical attendance after default edits

**Missing**

**No complete supported route:** Defaults aren't versioned historical profiles.

**Undo / correction / cancellation:** Use dated exceptions/document changes.

**Mistakes / limits:** Past home-day denominator can change.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

<a id="u132"></a>

### U132 · Automatically redistribute work during absence

**Missing**

**No complete supported route:** Attendance preserves responsibility.

**Undo / correction / cancellation:** Review coverage and reassign/claim individually.

**Mistakes / limits:** Away is not a silent release of saved work.

**Task help:** Trips and traded days; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Trips, UsualSchedule, TripModal, ExceptionCard; attendance/roster/recovery tests.

## Reminders and alerts

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U133](#u133) | Turn scheduled chore reminders on | Supported | 1 / 2 |
| [U134](#u134) | Turn scheduled reminders off | Supported | 1 / 2 |
| [U135](#u135) | Save up to ten daily reminder times | Supported | 2 / 3 |
| [U136](#u136) | Understand last missed/failed reminder | Awkward | 1 / 1 |
| [U137](#u137) | Enable/disable new trade DMs | Supported | 1 / 2 |
| [U138](#u138) | Choose reminders separately per chore | Missing | — |
| [U139](#u139) | Choose different times by weekday/task | Missing | — |
| [U140](#u140) | Snooze one notification | Missing | — |
| [U141](#u141) | Choose personal timezone | Missing | — |
| [U142](#u142) | Set quiet hours or temporary pause with automatic resume | Missing | — |
| [U143](#u143) | Test DM delivery from settings | Missing | — |
| [U144](#u144) | Read all delivery attempts/retry failures | Missing | — |
| [U145](#u145) | Force task/trade DMs to a person who opted out | Intentionally unavailable | — |
| [U146](#u146) | Replay all missed reminders after downtime | Intentionally unavailable | — |

<a id="u133"></a>

### U133 · Turn scheduled chore reminders on

**Supported**

**Steps:** 1. Chore reminders → 2. Turn on.

**Undo / correction / cancellation:** Turn off.

**Mistakes / limits:** Own account opt-in only.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u134"></a>

### U134 · Turn scheduled reminders off

**Supported**

**Steps:** 1. Chore reminders → 2. Turn off.

**Undo / correction / cancellation:** Turn on.

**Mistakes / limits:** Trade alerts independent; already handed-off DM cannot be recalled.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u135"></a>

### U135 · Save up to ten daily reminder times

**Supported**

**Steps:** 1. Chore reminders → 2. Change times → 3. Enter comma-separated times → 4. Submit → reminders.

**Undo / correction / cancellation:** Re-enter previous times.

**Mistakes / limits:** Valid HH:MM required; no silent truncation; input in one field.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

**Typing:** Enter comma-separated times.

<a id="u136"></a>

### U136 · Understand last missed/failed reminder

**Awkward**

**Steps:** 1. Chore reminders → 2. Read Last reminder attempt.

**Undo / correction / cancellation:** Fix times/availability/Discord privacy.

**Mistakes / limits:** Only last attempt shown; no personal full log/retry.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u137"></a>

### U137 · Enable/disable new trade DMs

**Supported**

**Steps:** 1. Trade alerts → 2. Turn trade DMs on/off.

**Undo / correction / cancellation:** Toggle back.

**Mistakes / limits:** Does not change due-chore times; Trades remains on dashboard.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u138"></a>

### U138 · Choose reminders separately per chore

**Missing**

**No complete supported route:** No per-chore preference.

**Undo / correction / cancellation:** Account-wide due responsibilities.

**Mistakes / limits:** Already deferred feature; not implemented.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u139"></a>

### U139 · Choose different times by weekday/task

**Missing**

**No complete supported route:** Times are daily/account-wide.

**Undo / correction / cancellation:** Change times manually.

**Mistakes / limits:** No weekday or AM-only task subscription.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u140"></a>

### U140 · Snooze one notification

**Missing**

**No complete supported route:** No notification pause/snooze.

**Undo / correction / cancellation:** Change times/disable reminders.

**Mistakes / limits:** Affects more than that occurrence.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u141"></a>

### U141 · Choose personal timezone

**Missing**

**No complete supported route:** Household Eastern only.

**Undo / correction / cancellation:** Convert chosen times.

**Mistakes / limits:** No per-person schedule timezone.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u142"></a>

### U142 · Set quiet hours or temporary pause with automatic resume

**Missing**

**No complete supported route:** No pause-until setting.

**Undo / correction / cancellation:** Manual toggle; away exception suppresses reminders with broader effects.

**Mistakes / limits:** Attendance is not just a notification mute.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u143"></a>

### U143 · Test DM delivery from settings

**Missing**

**No complete supported route:** No Test message action.

**Undo / correction / cancellation:** Wait for eligible scheduled time and inspect last attempt.

**Mistakes / limits:** Saved times aren't delivery proof.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u144"></a>

### U144 · Read all delivery attempts/retry failures

**Missing**

**No complete supported route:** No delivery-history/retry screen.

**Undo / correction / cancellation:** Last attempt and separate owner log investigation.

**Mistakes / limits:** Uncertain sends intentionally not repeated blindly.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u145"></a>

### U145 · Force task/trade DMs to a person who opted out

**Intentionally unavailable**

**No complete supported route:** Preference gates deny normal reminders/alerts.

**Undo / correction / cancellation:** Person opts in themselves.

**Mistakes / limits:** Configured owner feedback/backup alerts are separate authorized lanes.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

<a id="u146"></a>

### U146 · Replay all missed reminders after downtime

**Intentionally unavailable**

**No complete supported route:** No unbounded replay.

**Undo / correction / cancellation:** Current eligible slots resume.

**Mistakes / limits:** Prevents stale/duplicate DMs.

**Task help:** Set reminders; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_planning.py: Reminders, ReminderTimes, send_due_reminders; chore_workspace.py: Notifications, notify_trade; reminder tests.

## Feedback and reviews

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U147](#u147) | Suggest more/fewer effort points | Supported | 4 / 7 |
| [U148](#u148) | Suggest better instructions/timing | Supported | 4 / 6 |
| [U149](#u149) | Read household and prior feedback | Supported | 4 / 7 |
| [U150](#u150) | Edit/retract my saved feedback | Intentionally unavailable | — |
| [U151](#u151) | Reply to a review in a discussion thread | Intentionally unavailable | — |
| [U152](#u152) | Read open owner inbox | Supported | 1 / 1 |
| [U153](#u153) | Resolve review and move to next | Supported | 2 / 2 |
| [U154](#u154) | Reopen resolved review | Supported | 4 / 4 |
| [U155](#u155) | Apply point suggestion and mark handled | Awkward | 5 / 6 |
| [U156](#u156) | Receive a structured owner decision explanation | Intentionally unavailable | — |
| [U157](#u157) | Resolve/reopen owner inbox as non-owner | Intentionally unavailable | — |

<a id="u147"></a>

### U147 · Suggest more/fewer effort points

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Give feedback → 5. Open effort score picker → 6. Choose score → 7. Enter comment if wanted → 8. Submit → review.

**Undo / correction / cancellation:** Add revised suggestion; no edit/retract.

**Mistakes / limits:** Latest suggested score per person summarized; previous entries retained.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

**Typing:** Enter comment if wanted.

<a id="u148"></a>

### U148 · Suggest better instructions/timing

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Give feedback → 5. Add feedback → 6. Enter comment/timing → 7. Submit → review.

**Undo / correction / cancellation:** Submit correction as another entry.

**Mistakes / limits:** Does not auto-edit chore.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

**Typing:** Enter comment/timing.

<a id="u149"></a>

### U149 · Read household and prior feedback

**Supported**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Give feedback → 5. All feedback → 6. Open review picker → 7. Select full review.

**Undo / correction / cancellation:** Open feedback filters unresolved.

**Mistakes / limits:** Not threaded conversation.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u150"></a>

### U150 · Edit/retract my saved feedback

**Intentionally unavailable**

**No complete supported route:** Not needed for this household; explicitly excluded by Katherine on October 22, 2026.

**Undo / correction / cancellation:** Existing feedback submission, reviewed/open status, resolution and reopening remain sufficient.

**Mistakes / limits:** This is an accepted scope choice, not a missing-feature recommendation.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u151"></a>

### U151 · Reply to a review in a discussion thread

**Intentionally unavailable**

**No complete supported route:** Not needed for this household; explicitly excluded by Katherine on October 22, 2026.

**Undo / correction / cancellation:** Existing feedback submission, reviewed/open status, resolution and reopening remain sufficient.

**Mistakes / limits:** This is an accepted scope choice, not a missing-feature recommendation.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u152"></a>

### U152 · Read open owner inbox

**Supported**

**Steps:** 1. Review inbox → 2. Read current review.

**Undo / correction / cancellation:** Resolved reviews for handled entries.

**Mistakes / limits:** Owner-only inbox; DM is only notification, not sole record.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u153"></a>

### U153 · Resolve review and move to next

**Supported**

**Steps:** 1. Review inbox → 2. Resolve and next.

**Undo / correction / cancellation:** Resolved reviews → Reopen → Confirm.

**Mistakes / limits:** Does not change chore definition.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u154"></a>

### U154 · Reopen resolved review

**Supported**

**Steps:** 1. Review inbox → 2. Resolved reviews → 3. Reopen review → confirmation → 4. Confirm → inbox.

**Undo / correction / cancellation:** Resolve again.

**Mistakes / limits:** No duplicate review DM.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u155"></a>

### U155 · Apply point suggestion and mark handled

**Awkward**

**Steps:** 1. Review inbox → 2. Edit chore → 3. Edit details → 4. Enter points → 5. Save → result → 6. Return inbox → 7. Resolve and next.

**Undo / correction / cancellation:** Manually restore definition value; reopen review separately.

**Mistakes / limits:** No atomic Apply suggestion; past awards unaffected.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

**Typing:** Enter points.

<a id="u156"></a>

### U156 · Receive a structured owner decision explanation

**Intentionally unavailable**

**No complete supported route:** Not needed for this household; explicitly excluded by Katherine on October 22, 2026.

**Undo / correction / cancellation:** Existing feedback submission, reviewed/open status, resolution and reopening remain sufficient.

**Mistakes / limits:** This is an accepted scope choice, not a missing-feature recommendation.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

<a id="u157"></a>

### U157 · Resolve/reopen owner inbox as non-owner

**Intentionally unavailable**

**No complete supported route:** Owner guard rejects.

**Undo / correction / cancellation:** Submit feedback or ask owner.

**Mistakes / limits:** Shared catalog editing is separate permission.

**Task help:** Suggest a chore change; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_board.py: FeedbackView, FeedbackModal; chore_workspace.py: Inbox; owner-review tests.

## Points and fair workload

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U158](#u158) | See my balance/streak | Supported | 0 / 0 |
| [U159](#u159) | See household rankings | Supported | 1 / 1 |
| [U160](#u160) | Compare earned daily/weekly/monthly pace | Supported | 1 / 1 |
| [U161](#u161) | Compare planned future workload | Supported | 1 / 2 |
| [U162](#u162) | Compare points per home-day | Supported | 1 / 1 |
| [U163](#u163) | Sort workload by plan/earned/name | Supported | 1 / 2 |
| [U164](#u164) | Understand pace calculations | Supported | 2 / 2 |
| [U165](#u165) | Reset one person's points as owner | Supported | 4 / 6 |
| [U166](#u166) | Reset everybody's points as owner | Supported | 4 / 5 |
| [U167](#u167) | Undo a points reset as owner | Supported | 5 / 5 |
| [U168](#u168) | Correct another person's completion as owner | Awkward | 5 / 7 |
| [U169](#u169) | Give bonus points or manually set balance | Missing | — |
| [U170](#u170) | Redeem points for rewards | Missing | — |
| [U171](#u171) | Export points/workload CSV | Missing | — |
| [U172](#u172) | See earned-effort time-series graph | Missing | — |
| [U173](#u173) | Retroactively change old awards by editing chore points | Intentionally unavailable | — |
| [U174](#u174) | Reset/correct others' points as non-owner | Intentionally unavailable | — |

<a id="u158"></a>

### U158 · See my balance/streak

**Supported**

**Steps:** 1. Read dashboard total.

**Undo / correction / cancellation:** Points & standings shows more.

**Mistakes / limits:** Balance differs from all-time earned effort after reset.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u159"></a>

### U159 · See household rankings

**Supported**

**Steps:** 1. Points & standings.

**Undo / correction / cancellation:** Dashboard/paging.

**Mistakes / limits:** Credit belongs to completer.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u160"></a>

### U160 · Compare earned daily/weekly/monthly pace

**Supported**

**Steps:** 1. Workload & pace.

**Undo / correction / cancellation:** Change period.

**Mistakes / limits:** Month is 30-day equivalent; today separate.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u161"></a>

### U161 · Compare planned future workload

**Supported**

**Steps:** 1. Workload & pace → 2. Choose 7/28/90 days.

**Undo / correction / cancellation:** Change period/sort.

**Mistakes / limits:** Projection under current definitions, not guarantee.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u162"></a>

### U162 · Compare points per home-day

**Supported**

**Steps:** 1. Workload & pace → 2. Read Per home-day.

**Undo / correction / cancellation:** How this is calculated.

**Mistakes / limits:** Historical default edits can alter denominator.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u163"></a>

### U163 · Sort workload by plan/earned/name

**Supported**

**Steps:** 1. Workload & pace → 2. Sort cycle.

**Undo / correction / cancellation:** Cycle back.

**Mistakes / limits:** Read-only comparison.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u164"></a>

### U164 · Understand pace calculations

**Supported**

**Steps:** 1. Workload & pace → 2. How this is calculated.

**Undo / correction / cancellation:** Back preserves report context.

**Mistakes / limits:** Reset balance does not erase earned work history.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u165"></a>

### U165 · Reset one person's points as owner

**Supported**

**Steps:** 1. Points & standings → 2. Reset points → 3. Open person picker → 4. Select target → 5. Choose streak option → 6. Confirm reset → result.

**Undo / correction / cancellation:** Reset history → Undo → Confirm while safe.

**Mistakes / limits:** History/responsibilities retained; later activity may block Undo.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u166"></a>

### U166 · Reset everybody's points as owner

**Supported**

**Steps:** 1. Points & standings → 2. Reset points → 3. Everyone → 4. Choose streak option → 5. Confirm reset → result.

**Undo / correction / cancellation:** Undo batch while all affected states unchanged.

**Mistakes / limits:** No partial rollback after someone's newer score activity.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u167"></a>

### U167 · Undo a points reset as owner

**Supported**

**Steps:** 1. Points & standings → 2. Reset history / Undo → 3. Select/page batch → 4. Undo points reset → confirmation → 5. Confirm → history.

**Undo / correction / cancellation:** Reset again deliberately.

**Mistakes / limits:** Entire batch guard; streak state restored too.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u168"></a>

### U168 · Correct another person's completion as owner

**Awkward**

**Steps:** 1. My chores → 2. Chore name → details → 3. Open Schedule & details → 4. Completion history → 5. Open completion picker → 6. Choose record → confirmation → 7. Confirm → history.

**Undo / correction / cancellation:** Person can redo eligible work.

**Mistakes / limits:** Still latest/unchanged safety checks, not arbitrary history rewrite.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u169"></a>

### U169 · Give bonus points or manually set balance

**Missing**

**No complete supported route:** No general award/adjustment control.

**Undo / correction / cancellation:** Use genuine work/reset controls for intended scope.

**Mistakes / limits:** Do not manufacture duplicate completions for bonuses.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u170"></a>

### U170 · Redeem points for rewards

**Missing**

**No complete supported route:** No rewards/redemption feature.

**Undo / correction / cancellation:** Use points as effort measure.

**Mistakes / limits:** Optional capability, not automatic roadmap item.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u171"></a>

### U171 · Export points/workload CSV

**Missing**

**No complete supported route:** No report export UI.

**Undo / correction / cancellation:** Separate maintenance database backup isn't ready report.

**Mistakes / limits:** Manual copy is not structured export.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u172"></a>

### U172 · See earned-effort time-series graph

**Missing**

**No complete supported route:** Only summary rate comparisons.

**Undo / correction / cancellation:** Compare periods manually.

**Mistakes / limits:** Averages hide individual spikes.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u173"></a>

### U173 · Retroactively change old awards by editing chore points

**Intentionally unavailable**

**No complete supported route:** Definition edit doesn't rewrite recorded awards.

**Undo / correction / cancellation:** Correct eligible mistake or change future effort value.

**Mistakes / limits:** Historical integrity preserved.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

<a id="u174"></a>

### U174 · Reset/correct others' points as non-owner

**Intentionally unavailable**

**No complete supported route:** Owner guards deny.

**Undo / correction / cancellation:** Ask owner to inspect.

**Mistakes / limits:** Shared chore edit permission is separate.

**Task help:** Points and standings; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Points, ResetPoints, ResetHistory, History; chore_history.py; chore_insights.py: Report.

## Operations, safety and other boundaries

| ID | User task | Status | Hops / controls |
| --- | --- | --- | --- |
| [U175](#u175) | Switch automatic update notices as owner | Supported | 1 / 2 |
| [U176](#u176) | Announce installed update manually | Supported | 3 / 3 |
| [U177](#u177) | Announce updates as non-owner | Intentionally unavailable | — |
| [U178](#u178) | Retract sent public release notice via bot | Missing | — |
| [U179](#u179) | Configure alternating accounts/rotation | Awkward | 1 / 4 |
| [U180](#u180) | Recover from stale submitted form | Awkward | 2 / 4 |
| [U181](#u181) | Recover after double tap | Supported | 0 / 1 |
| [U182](#u182) | Use bot while service is offline | Intentionally unavailable | — |
| [U183](#u183) | Use a separate browser household app | Missing | — |
| [U184](#u184) | Choose arbitrary button background colors | Intentionally unavailable | — |
| [U185](#u185) | Choose arbitrary per-person font colors in bot text | Intentionally unavailable | — |
| [U186](#u186) | Create independent subtasks/dependencies | Missing | — |
| [U187](#u187) | Set task priority or an exact hourly deadline | Missing | — |
| [U188](#u188) | Bulk holiday exceptions for tasks | Missing | — |
| [U189](#u189) | Back up/restore from Discord panel | Missing | — |
| [U190](#u190) | Inspect one unified all-change audit feed | Missing | — |

<a id="u175"></a>

### U175 · Switch automatic update notices as owner

**Supported**

**Steps:** 1. Update announcements → 2. Turn automatic on/off.

**Undo / correction / cancellation:** Toggle back.

**Mistakes / limits:** Off means quiet start; deploy preserves preference.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u176"></a>

### U176 · Announce installed update manually

**Supported**

**Steps:** 1. Update announcements → 2. Announce this update → preview → 3. Confirm → result.

**Undo / correction / cancellation:** Cancel preview; no bot Undo after public send.

**Mistakes / limits:** Version/destination/dedup checked; uncertain send not blindly repeated.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u177"></a>

### U177 · Announce updates as non-owner

**Intentionally unavailable**

**No complete supported route:** Owner-only action denied.

**Undo / correction / cancellation:** Ask owner.

**Mistakes / limits:** Shared chores isn't permission to post notices.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u178"></a>

### U178 · Retract sent public release notice via bot

**Missing**

**No complete supported route:** No retract-announcement action.

**Undo / correction / cancellation:** Manual Discord message management by permitted person.

**Mistakes / limits:** External destructive action, not internal Undo.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u179"></a>

### U179 · Configure alternating accounts/rotation

**Awkward**

**Steps:** 1. Household setup → 2. Open account selector → 3. Select human accounts → 4. Save household.

**Undo / correction / cancellation:** Reopen/correct configuration.

**Mistakes / limits:** Requires setup permission; bots/outsiders denied. Account picker selection may require a separate dropdown opening; saved setup applies only after Save household.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u180"></a>

### U180 · Recover from stale submitted form

**Awkward**

**Steps:** 1. Affected screen → 2. Refresh → 3. Reopen form → 4. Re-enter fields → 5. Save → result.

**Undo / correction / cancellation:** Inspect saved state before retry.

**Mistakes / limits:** Safe refusal can still require retyping.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

**Typing:** Re-enter fields.

<a id="u181"></a>

### U181 · Recover after double tap

**Supported**

**Steps:** 1. Inspect result → 2. Refresh if needed.

**Undo / correction / cancellation:** Use relevant Undo if saved mistakenly.

**Mistakes / limits:** Mutation once; stale duplicate rejected.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u182"></a>

### U182 · Use bot while service is offline

**Intentionally unavailable**

**No complete supported route:** Interactions require running bot.

**Undo / correction / cancellation:** Reopen when restored.

**Mistakes / limits:** No offline sync client.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u183"></a>

### U183 · Use a separate browser household app

**Missing**

**No complete supported route:** No separate web application.

**Undo / correction / cancellation:** Discord desktop/mobile.

**Mistakes / limits:** No Activity/web rewrite in this release.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u184"></a>

### U184 · Choose arbitrary button background colors

**Intentionally unavailable**

**No complete supported route:** Discord supports fixed styles only.

**Undo / correction / cancellation:** Consistent styles/text/symbols.

**Mistakes / limits:** Requested purple/orange/yellow cannot be arbitrary actual backgrounds.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u185"></a>

### U185 · Choose arbitrary per-person font colors in bot text

**Intentionally unavailable**

**No complete supported route:** Ordinary Discord content has no per-name font colors.

**Undo / correction / cancellation:** Resolved names/mentions and Discord role presentation.

**Mistakes / limits:** Not a user-selectable color profile feature.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u186"></a>

### U186 · Create independent subtasks/dependencies

**Missing**

**No complete supported route:** Only checklist steps, not dependency graph.

**Undo / correction / cancellation:** Use checklist within one chore.

**Mistakes / limits:** Steps lack independent owner/schedule/points.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u187"></a>

### U187 · Set task priority or an exact hourly deadline

**Missing**

**No complete supported route:** Weekday/AM/PM/date schedules only.

**Undo / correction / cancellation:** Use schedule/instructions, knowing text doesn't drive reminder timing.

**Mistakes / limits:** Wednesday night in instructions is not a 9 p.m. deadline.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u188"></a>

### U188 · Bulk holiday exceptions for tasks

**Missing**

**No complete supported route:** No holiday calendar/bulk skip.

**Undo / correction / cancellation:** Skip dates individually.

**Mistakes / limits:** People's trips are not task holiday calendar.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u189"></a>

### U189 · Back up/restore from Discord panel

**Missing**

**No complete supported route:** No backup/restore UI.

**Undo / correction / cancellation:** Use documented maintenance procedure.

**Mistakes / limits:** Backup existence doesn't prove a tested restoration.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

<a id="u190"></a>

### U190 · Inspect one unified all-change audit feed

**Missing**

**No complete supported route:** History separated by completion/review/attendance/reset.

**Undo / correction / cancellation:** Inspect relevant records.

**Mistakes / limits:** No universal who-changed-what timeline for definitions/settings.

**Task help:** Start here; see HELP-COVERAGE.md for screen mapping specificity.

**Source evidence:** chore_workspace.py: Announcements; chore_recovery.py; TESTING.md and deployment/backup guides.

