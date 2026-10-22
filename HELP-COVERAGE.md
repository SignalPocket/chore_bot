# Task help and screen context coverage

October 22, 2026 · prepared 1.3.2. This is a documentation mapping/audit, not a new runtime task-search feature.

## Canonical relationship

User goal (stable U-ID) → task help instructions → screen/context-specific entry point. Keep one canonical explanation of a task; multiple screens may link to it. Existing runtime help uses topics, not U-ID deep links. The new U-IDs are audit keys until implemented in the runtime.

Every audited goal has an existing topic as its nearest destination, but that does not mean the topic explains every missing capability. Missing/unavailable tasks need an honest limitation and alternative, not fictional how-to steps.

## Task groups to help topics

| Goal family | Current topic | Task IDs |
| --- | --- | --- |
| Start and recovery | Start here | U001–U012 |
| Find and understand work | Pick up a chore | U013–U034 |
| Complete, skip and ask for help | Finish a chore | U035–U057 |
| Reserve, share and trade | Drop, reassign, or trade | U058–U079 |
| Calendar and future work | Future occurrences | U080–U093 |
| Catalog and schedule maintenance | Add, edit, or copy chores | U094–U116 |
| Attendance and trips | Trips and traded days | U117–U132 |
| Reminders and alerts | Set reminders | U133–U146 |
| Feedback and reviews | Suggest a chore change | U147–U157 |
| Points and fair workload | Points and standings | U158–U174 |
| Operations, safety and other boundaries | Start here | U175–U190 |

## Screen mappings in current code

The ? is placed by the shared page template. The table describes the content it opens, not a claim every screen has custom instructions. Discord modal forms use their launch screen’s help.

| Screen type | Current help topic | Specificity assessment |
| --- | --- | --- |
| AddChoreMenu | Add, edit, or copy chores | Explicit topic mapping; validate task wording on this screen |
| Announcements | Start here | Broad/shared; needs task-specific entry or section |
| AttendanceView | Trips and traded days | Explicit topic mapping; validate task wording on this screen |
| Attention | Report a problem | Broad/shared; needs task-specific entry or section |
| Browse | Pick up a chore | Explicit topic mapping; validate task wording on this screen |
| ButtonChoices | Start here | Broad/shared; needs task-specific entry or section |
| Calendar | Use the calendar | Explicit topic mapping; validate task wording on this screen |
| Card | Pick up a chore | Broad/shared; needs task-specific entry or section |
| Checklist | Finish a chore | Explicit topic mapping; validate task wording on this screen |
| ChooseDayView | Choose or change a day | Explicit topic mapping; validate task wording on this screen |
| ClaimChoices | Pick up a chore | Broad/shared; needs task-specific entry or section |
| Confirm | Undo a mistake | Broad/shared; needs task-specific entry or section |
| Dashboard | Start here | Explicit topic mapping; validate task wording on this screen |
| Day | Use the calendar | Explicit topic mapping; validate task wording on this screen |
| DropChoreView | Drop, reassign, or trade | Explicit topic mapping; validate task wording on this screen |
| EditChoreView | Add, edit, or copy chores | Explicit topic mapping; validate task wording on this screen |
| ExceptionCard | Trips and traded days | Explicit topic mapping; validate task wording on this screen |
| FeedbackView | Suggest a chore change | Explicit topic mapping; validate task wording on this screen |
| Filters | Pick up a chore | Broad/shared; needs task-specific entry or section |
| FutureOccurrence | Future occurrences | Explicit topic mapping; validate task wording on this screen |
| FutureSlots | Future occurrences | Explicit topic mapping; validate task wording on this screen |
| Groups | Pick up a chore | Broad/shared; needs task-specific entry or section |
| Guide | Start here | Broad/shared; needs task-specific entry or section |
| HelpHistory | Report a problem | Explicit topic mapping; validate task wording on this screen |
| HelpStatus | Report a problem | Explicit topic mapping; validate task wording on this screen |
| History | Undo a mistake | Explicit topic mapping; validate task wording on this screen |
| HouseholdSetup | Trips and traded days | Broad/shared; needs task-specific entry or section |
| Inbox | Suggest a chore change | Broad/shared; needs task-specific entry or section |
| ListLength | Change list length | Explicit topic mapping; validate task wording on this screen |
| Manage | Add, edit, or copy chores | Explicit topic mapping; validate task wording on this screen |
| MissedChoreView | Schedules and missed chores | Explicit topic mapping; validate task wording on this screen |
| NeedsHelp | Report a problem | Explicit topic mapping; validate task wording on this screen |
| Notifications | Trade alerts | Explicit topic mapping; validate task wording on this screen |
| OccurrenceDates | Future occurrences | Explicit topic mapping; validate task wording on this screen |
| PageHelp | Start here | Broad/shared; needs task-specific entry or section |
| PersonalView | Pick up a chore | Explicit topic mapping; validate task wording on this screen |
| Points | Points and standings | Explicit topic mapping; validate task wording on this screen |
| ReassignView | Drop, reassign, or trade | Explicit topic mapping; validate task wording on this screen |
| Reminders | Set reminders | Explicit topic mapping; validate task wording on this screen |
| RemoveChoreView | Add, edit, or copy chores | Explicit topic mapping; validate task wording on this screen |
| RepeatMenu | Schedules and missed chores | Explicit topic mapping; validate task wording on this screen |
| Repeating | Repeating days | Explicit topic mapping; validate task wording on this screen |
| Report | Workload & pace | Explicit topic mapping; validate task wording on this screen |
| ResetHistory | Points and standings | Broad/shared; needs task-specific entry or section |
| ResetPoints | Points and standings | Broad/shared; needs task-specific entry or section |
| ResponsibilityView | Pick up a chore | Broad/shared; needs task-specific entry or section |
| ReviewInbox | Suggest a chore change | Explicit topic mapping; validate task wording on this screen |
| TradeInboxView | Drop, reassign, or trade | Explicit topic mapping; validate task wording on this screen |
| TradeOfferView | Drop, reassign, or trade | Explicit topic mapping; validate task wording on this screen |
| Trips | Trips and traded days | Explicit topic mapping; validate task wording on this screen |
| UsualSchedule | Trips and traded days | Explicit topic mapping; validate task wording on this screen |
| WeekdayMenu | Schedules and missed chores | Explicit topic mapping; validate task wording on this screen |
| WeeklyView | Pick up a chore | Broad/shared; needs task-specific entry or section |

## Subsequent polish

The screen polish adds concise inline contextual instructions for Card and Attention, corrects Claim/menu paths, and documents immediate bottom Undo Done. The base topic registry remains shared. Confirm, ButtonChoices and Announcements already have inline contextual overrides; their base topic names alone do not establish what their ? displays. Broader task-index/search improvements remain deferred.

## Audit gaps and remaining work

- Card’s inline help now explains common actions, menus and Undo; the broader task index is still a follow-up.
- Attention’s inline help now explains overdue/unclaimed/blocked inclusion and due versus overdue.
- Confirmation uses a generic inline safety explanation despite its Undo a mistake base topic; richer per-action guidance remains a possible follow-up.
- Choice picker and announcements have inline overrides; task-specific refinements should inspect those instructions, not just Start here registry entries.
- Owner reset/review screens share broad points/feedback topics; user and owner procedures need distinct subsections or anchors.
- Current help lacks a complete goal index/search, direct U-ID links and explicit instructions for all recovery limits found in USER-TASK-AUDIT.md.
- A useful button does not establish help correctness: validate the topic text against the current label and action scope after any refactor.

## Next implementation contract

Give each task a canonical title, purpose, preconditions, shortest path, saved effect, correction path, known restrictions and related tasks. Give each screen a help target plus its current chore/date/scope. Prefer linking to the same task instruction rather than maintaining duplicate prose. Do not display how-to instructions for missing features as though implemented.
