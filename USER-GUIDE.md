# Sprig household chore guide

## Button controls and repeating weekday signups

Each chore row has a **chore-name button**, **Claim / Done**, and **Skip**. Click the name to open instructions, checklist, estimate, responsibility, and actions. The colored day/period marker, AM/PM slot where relevant, and points appear on the name button. Taken work shows the responsible person; future and completed occurrences have disabled action buttons. Previous and Next keep their fixed positions, and pages stay at five chores by default.

**Claim** opens **Just this occurrence**, **This week**, **Next week**, and, for daily chores, **Repeating weekdays / shifts**. Whole-week signups retain the existing Sunday 6 p.m. handoff. Buttons replace dropdown controls throughout the workspace. Longer option lists have Previous/Next; multi-choice screens use toggle buttons followed by **Apply selection**. **Find a person** can search the household server by the beginning of a Discord name or nickname, then display matching people as buttons. Text forms remain for names, instructions, dates, and feedback.

To take particular days: open a daily chore → **Sign-up schedule** (or **Claim → Repeating weekdays / shifts**), toggle weekdays, choose **Whole day**, **AM**, or **PM** as offered, then **Save repeating days → Confirm**. A daily task stays daily: Kas can take Mondays/Wednesdays, Zel Tuesdays/Thursdays, and other days remain open. A twice-daily chore can give AM and PM to different people. A separate Daily AM or Daily PM chore offers only its own shift. Nothing saves before confirmation.

Repeating signups are **only when home**. Usual attendance defaults, alternating weeks, and dated home/away exceptions are checked for each occurrence and reminder. Away days need coverage; the saved repeating signup returns automatically when that person is home. Two people may share a weekday/shift when their home schedules do not overlap, such as opposite alternating weeks. Overlapping home responsibility is rejected when saving. If an attendance change later puts both people home for the same slot, Sprig leaves it unclaimed instead of choosing a winner: use an occurrence Claim/Reassign for coverage and adjust the signup or attendance.

Use **Sign-up schedule → select days/shifts → Release selected days → Confirm** to release your repeating slots. Other days and other people stay unchanged. **Skip** affects only the current occurrence, awards no points, and keeps the repeating signup. **Reassign** and accepted **Trade** change just the current occurrence when it comes from a repeating signup. Completed work, points, and history stay saved. Whole-week or ongoing assignments cannot override repeating days; release the conflicting responsibility first. Changing the regular repeat cadence requires releasing weekday signups first; splitting a twice-daily chore into separate AM/PM chores carries each shift's signups to the correct chore.

My chores, Pick up chores, Needs attention, household responsibility summaries, calendar previews, reminders, and Workload & pace use the effective weekday/shift owner. Calendar previews show both AM and PM owners; uncovered and away slots remain available. Points still go only to the account that completes the work. Repeating signups are available for daily schedules; weekly/monthly/one-time chores retain their existing signup controls.


Open **/chores** in the household Discord server. Sprig opens your private workspace. Other people cannot use your controls, but assignments and chore changes are shared household information.

## Find your way around

| Destination | What it does |
| --- | --- |
| My chores | Your work due now, this week, next week, upcoming, and completed. |
| Pick up chores | Available work you can take once or reserve for a week. |
| Household | Everyone’s work, organized by person, chore, or day. Every chore is selectable. |
| Who’s home? | Normal attendance, trips, and traded days. |
| Manage chores | Add chores and archive or restore them. Open a chore card to edit its details. |
| Trades | Incoming and outgoing proposals. The dashboard shows your incoming count. |
| Points & standings | Your total and streak, plus household standings, shown privately with buttons. |
| Calendar | Private week/month schedule preview, day details, and a separate No fixed day list. |
| Needs attention | Overdue, due unclaimed, and blocked chores together, with counts, help notes, and links to chore cards. |
| Reminders | Your own opt-in reminder times and off switch. |
| Notifications | Opt in to private trade notifications for your own account. |
| Help | Short task-oriented explanations, including the color legend. |
| Review inbox | Ginaria’s queue of household feedback. This button is visible only to ginaria. |
| Household setup | Administrator-only selection of Kas and Zel’s Discord accounts. |

The saved shared dashboard has six entry buttons. Each opens private controls. Your private dashboard includes personal counts and permitted owner/setup tools. **Back** returns to the previous screen; **Dashboard** goes home. Most navigation edits the current private message. Validation errors may appear as a separate private message.

Private controls expire after ten minutes of inactivity or a bot restart. Reopen /chores when that happens. A screen does not update live when someone else changes a chore; use Refresh or reopen it. A stale action may be rejected so it cannot apply to changed work.

## Read a chore card

Lists use Discord Components V2 with five chores per page. Previous and Next sit directly below the page numbers, above the view tabs. Each row has a chore-name button that opens details, a Claim/Done button, and Skip. Away-day Done buttons are disabled. Pressing Done refreshes the same private list. The chore-name button opens instructions and other actions. Discord controls the actual width on each device.

Select a chore from My chores, Pick up chores, or Household. Each route opens the same card:

- **Responsibility.** Who owns it and for how long.
- **When.** Its regular schedule, current occurrence, and missed-work setting.
- **Points and room.** Points earned for one completion and the optional room.
- **Instructions.** What counts as done.
- **Actions.** Named buttons for the available actions.

The three responsibility durations are **Just this time**, **This week / Next week**, and **Every week · ongoing**. A chore’s name does not assign it: a chore called “Kas: laundry” still needs an actual Discord-account assignment or sign-up.

## Separate morning and evening responsibilities

Use **Daily · AM** and **Daily · PM** when different people should handle morning and afternoon/evening work. Each shift has its own sign-ups, weekly owner, completion, and points. AM opens at midnight; PM opens at noon, Eastern time. Each shift follows its own Keep overdue or Skip if missed setting.

For an existing twice-daily chore, open its card → **Separate AM and PM sign-ups**, then confirm. The existing chore becomes AM and a separate PM chore appears. Existing weekly reservations and ongoing ownership stay with AM; PM starts open, except an existing single PM claim follows the PM shift. Both keep the original points and instructions. Already-earned points and completion history are preserved, and an already-completed shift cannot earn points again that day. Splitting after noon starts an unfinished AM shift the following morning.

For **Empty dishwasher**, reserve **Empty dishwasher · AM** and **Empty dishwasher · PM** separately. Filling the dishwasher remains a separate chore.

## See your work and find chores

**My chores** has Due now, This week, Next week, Upcoming, and Completed tabs. Being away does not erase your responsibilities. Upcoming work stays visible, but cannot be completed before it becomes available. Completed lists chores with recorded completions by you; open the card’s Completion history for individual records.

**Pick up chores** offers Due now, This week, Next week, and All chores. Weekly reservations are available only for eligible recurring chores. Monthly and one-time work can be taken when its occurrence is available or assigned on an ongoing basis where applicable.

**Household** offers the same time views, plus By person / By chore / By day and an Unclaimed only filter. A two-day chore appears on both scheduled days; totals count the chore once. Daily work has an Every day group. Flexible work keeps its weekly/monthly label without an invented weekday. The view warns when an owner is away for scheduled work.

Use **Search** for a name or words in instructions. **Filters** can select a person, room, or exact date. The date filter shows dated occurrences; flexible weekly/monthly work has no exact day until a day or occurrence move is chosen. Clear filters to return to the full list. View preferences are remembered for your account while the bot is running.

Your points total appears at the top of My chores and updates when you mark work done. The dashboard’s **Points & standings** button shows your total, streak, and household standings without typing commands. Tied scores share a rank. Points stay with the completing Discord account and do not currently redeem anything.

## Reset points — ginaria only

Open **Dashboard → Points & standings → Reset points**. Only ginaria sees this button and can confirm a reset. Choose one person with a saved score or **Everyone**. Streaks are kept by default; choose **Reset streaks too** to clear the streak and its last-completion date as well. Review the selected person or account count, total points, and streak choice, then **Confirm reset**. Cancel leaves everything unchanged. If scores or the affected roster change before confirmation, start again with a fresh preview.

The reset sets the selected totals to zero. Chore history, completed chores, assignments, and sign-ups are kept. Each affected account gets a reset audit record. Old completion Undo cannot restore points from before a reset. **Reset history / Undo** shows saved resets. Only ginaria can choose **Undo points reset**, review the confirmation, and restore the selected reset’s saved scores and streak state. All affected people are restored together or none. New completions, another reset, or changed scores block Undo so later work is not overwritten. Reset and recovery audit records remain saved; completion history is unchanged. Undoing a reset does not re-enable Undo on completions from before that reset. There is no arbitrary manual score-adjustment control.

## Estimates and checklists

Open a chore card → **Estimate / checklist**. Anyone in the household can edit these. Enter estimated minutes for one completion (1–1440), and up to 12 checklist steps, one per line, each up to 80 characters. Blank fields clear the estimate or checklist. Estimates are approximate and do not change points. A twice-daily chore has this estimate for each of its two completions.

Lists show the estimate and checklist progress. An inline **Checklist** button replaces Done when steps remain. Only the person responsible for the current, due occurrence can check or uncheck its steps. Progress follows the occurrence when it is reassigned. Finish the steps, then press **Done**; checking boxes alone awards no points. A complete checklist offers Done directly. Other people can read its progress.

The next occurrence starts unchecked. An unfinished Keep overdue occurrence retains progress; Skip if missed starts a fresh checklist when it advances. Changing checklist wording clears active progress, even when old wording is restored later. Changing only the estimate keeps progress. Completion Undo restores access to the prior occurrence’s saved progress when the usual safety checks allow it. AM/PM splitting copies the estimate and steps into both resulting chores.

## Personal chore reminders

Open **Dashboard → Reminders**. Reminders start **off** for everyone. Turn on authorizes private Discord DMs to your own account only. **Change times** accepts one to ten 24-hour times separated by commas, such as `09:00, 17:00`. Defaults are 9 a.m. and 5 p.m. Eastern. Changing times keeps your current on/off choice; **Turn off** stops future reminders. Nobody can opt another person in through these controls.

Each reminder lists your currently due, unfinished responsibilities, with estimates and progress. Unassigned work, archived chores, completed work, and upcoming work are excluded. No reminder is sent while you are away or have nothing due. Use the household-channel link in the DM, then /chores, to act on it.

Delivery is checked each minute with a 15-minute grace window. Older missed reminders are discarded after downtime. A daylight-saving time that does not exist is skipped; a repeated clock time sends at most once. Discord may block DMs: the last delivery result appears in Reminders. Failed or uncertain delivery is not automatically retried, to avoid duplicates. Turning off cannot recall a message already being sent.

## Calendar

Open **Dashboard → Calendar**. Switch **Week / Month** or **My calendar / Household**, and use Previous, Today, and Next. Week view uses colored weekday headings with dates, counts, and known estimated minutes. Month view shows a Monday-first grid and two date pickers. Choose a day to open its chore list, including responsibility and away warnings. Each day shows Page X of Y and the chore range. Previous page / Next page sit directly below that count; Previous day / Today / Next day move between dates without returning to the calendar. Date changes start at page one. Personal/household scope and Week/Month mode are retained, including when returning from a chore card.

**No fixed day** keeps flexible weekly/monthly/one-time chores separate rather than inventing a date. Move an occurrence or choose a regular day to put it on a date. Its owners are shown for the selected date’s household week. Daily AM and PM appear as separate chores; a twice-daily chore’s known workload counts both completions.

This is a schedule preview inside Discord, not an external calendar sync, historical activity report, or drag-and-drop rescheduler. Past dates do not reconstruct every earlier assignment. Sunday ownership is shown before the 6 p.m. handoff and can change that evening. Overdue chores remain in Due now. Selecting a future date does not create a claim or let someone complete future work; **Open current chore** explicitly returns to the actual current chore controls.

## Stuck, supplies, and help

Open the chore card → **Stuck / need help**. The person responsible for the current due, unfinished occurrence can choose **Stuck**, **Need supplies**, or **Need help**, then add a note. Notes are shared household information, even though controls are private. They do not drop responsibility, mark the chore Done, change points, or send an automatic DM. An away person can still explain why their due responsibility needs help.

The current status appears on chore lists and the card. **Dashboard → Needs attention** collects active issues so everyone can see what needs attention. The status follows the unfinished occurrence if it is reassigned or moved; the new responsible person can update it. Editing checklist steps or the time estimate does not remove the help note.

Anyone using their own household controls can **Mark resolved**, with confirmation, after the obstacle is handled. This clears only the active status. Updated and resolved notes remain in **Status history**, including who reported or resolved them. Cancel leaves the status unchanged. A completed, archived, or advanced occurrence no longer appears as actively needing help. If a completion is safely undone, its previous occurrence’s unresolved status is visible again. Normal Done and checklist requirements still apply.

## Duplicate a chore

Open a chore card → **Duplicate chore**. Enter a distinct new name, review the confirmation, then save. Everyone can do this; it is not owner-only. Repeated clicks or a retry after an uncertain response reopen the same saved copy rather than creating another.

The copy keeps the source’s instructions, regular schedule, points per completion, room, difficulty, time estimate, checklist steps, and Keep overdue / Skip if missed policy. It starts **unassigned, unfinished, and unchecked**, with fresh recurrence timing. Assignments, claims, weekly reservations, completion records, earned points, help notes, and one-off occurrence moves are not copied. For example, copying Kas’s laundry does not give the new chore to Kas automatically. Rename it and assign it deliberately.

Duplicate names are rejected even if the existing chore is archived. If source settings change while the form is open, reopen Duplicate chore and review the current version. If a copy is no longer needed, archive it; the original remains unchanged.

## Take work and finish it

From an available chore’s card:

- **Claim → Just this occurrence.** Claim the current occurrence.
- **Take this week / Take next week.** Reserve its repeating responsibility for that household week.
- **Every week · ongoing.** Confirm an assignment that continues until dropped or reassigned. This is offered when it does not conflict with weekly reservations.

Press **Done** beside your chore, or open its card and press **Done** when the work is finished. Points are awarded once for the occurrence. An ongoing assignment or weekly reservation stays yours after completion. Daily work returns the next day; twice-daily work returns in its next slot.

## Drop, reassign, or trade

Use the named action buttons on the chore card.

**Drop responsibility** shows the exact duration before confirmation. Dropping an ongoing assignment releases future occurrences too; dropping this week does not release a separate future-week reservation.

**Reassign** lets any trusted household person choose a valid duration and recipient, then confirm. It takes effect immediately without the recipient accepting. Points already earned stay with the person who earned them. Names and instructions do not change automatically; reassigning “Kas: laundry” does not rename it.

**Propose trade** offers your chore for someone else’s responsibility. The proposal shows the duration on both sides. Nothing changes until the recipient opens **Trades**, selects the proposal, and chooses **Accept trade**. They may Decline; you may Cancel proposal. Changing chores, dates, or weeks can make a proposal stale. Propose a fresh trade after reviewing the changes.

Trade DMs start off. A person can authorize notifications to their own account in **Notifications**. Pending proposals remain visible without DMs. Failed or uncertain deliveries are not automatically retried, avoiding duplicate notifications.

## Correct a completion

After Done, the chore card offers **Undo completion** for your most recent recorded completion. Completion history also offers Undo with confirmation.

Undo restores the previous chore state, claim, points, and streak values together. It is deliberately conservative: you must undo your most recent recorded completion first, and its occurrence, ownership, schedule, and points must still match. A later reset or edit can make safe undo unavailable. It cannot reconstruct completions made before this update.

**Ginaria can assist another person** from the chore card → Completion history → Choose completion to correct. The confirmation identifies the original person and points being reversed. It restores that person’s prior points/streak and the chore responsibility together, keeps the completion marked Undone, and records who corrected it. This uses the same safety rules: it must be that person’s latest completion, with no conflicting later state or score changes. It cannot force a rewind of later work or reconstruct unrecorded completions.

**Completion history starts with this release.** Earlier point totals remain intact, but earlier individual completions were not recorded in a reconstructable ledger. Undone records remain visible as Undone.

## Schedule chores

The household week runs **Sunday at 6 p.m. Eastern to the next Sunday at 6 p.m.** The displayed dates matter, especially around trips.

| Schedule | When it repeats |
| --- | --- |
| Daily | Midnight each day. |
| Twice daily | Morning before noon; afternoon/evening after noon. Resets at noon and midnight. |
| 🤍 Weekly | Flexible within the household week; resets Sunday at 6 p.m. |
| Specific weekday | The selected weekday. |
| Twice a week | The two selected weekdays. |
| Every other week | A weekday during base Kas/Zel home or away weeks. |
| 🟫 Monthly | First day of the next month. |
| One time | Does not repeat after completion. |

Weekdays are 🔴 Monday, 🟠 Tuesday, 🟡 Wednesday, 🟢 Thursday, 🔵 Friday, 🟣 Saturday, and 🩷 Sunday. Words accompany the markers; color is not the only way to identify the day.

**Change regular day** changes a weekly chore’s weekday for future weeks as well. Review the date preview and Save day. Use **Edit chore → Change schedule** for other cadences.

**Move this occurrence** changes one unfinished occurrence to today or a future date. Preview and confirm it. Its regular cadence and ownership remain unchanged; weekly ownership still expires at the normal handoff. The card shows the move and offers **Cancel occurrence move**. A regular schedule edit cancels an outstanding occurrence move.

**Edit chore → Missed chores** offers Keep overdue and Skip if missed. Selecting the choice saves it. Keep overdue leaves unfinished work due. Skip advances expired work without completion credit or points and releases only its single claim. Weekly reservations and ongoing assignments remain. Switching to Skip can immediately advance already-overdue work. One-time chores have no deadline to skip.

Notes such as “afternoon” or “Wednesday night” are instructions. They do not create reminder messages by themselves; personal reminders use the times you explicitly choose. Missed occurrences do not build up a separate backlog of copies.

## Trips and traded days

Open **Who’s home?** and choose one or more people. Select Mark home, Mark away, or a quick date shortcut. Dates accept YYYY-MM-DD, MM/DD/YYYY, MM/DD in the current year, today, or tomorrow. The last day is included. Check the readable preview before confirming.

Select a saved exception to **Edit dates** directly or **Cancel exception**. Editing retains the old record as inactive history. An overlap with a different exception is rejected; open the existing exception to revise it. A group trip is saved for all selected people together or none if any conflicts remain.

Exceptions cover full Eastern calendar days. They temporarily override attendance, then normal rotation resumes. They preserve chores and reservations; check Household for coverage warnings and reassign or trade work as needed. Fixed-day reservations require the person home on the scheduled days. Partial-week daily responsibilities may need coverage.

Kas and Zel’s base rotation changes Sunday at 6 p.m.; October 18, 2026 begins an away week. An administrator must select their actual accounts in Household setup. Their base home/away chore schedules, such as recycling, do not move automatically with individual trip exceptions.

## Feedback, effort scores, and the owner inbox

From a chore card choose **Give feedback**. Add comments, a better day/time, suggested points, or any combination. Common effort scores are 0, 1, 2, 3, 5, 8, 13, and 21; other nonnegative whole numbers are accepted. Leave points blank for a comment without a vote. The latest point suggestion per person appears once; earlier reviews stay saved.

Feedback is household information displayed through private controls. It is not an anonymous or confidential message to the owner. New feedback is also DMed to ginaria. If Discord blocks the DM, it remains saved in the inbox. Older feedback appears in the inbox without a DM backlog.

Ginaria’s **Review inbox** opens each review directly. **Resolve and next** advances the queue. **Edit chore** opens the relevant settings. Only ginaria can resolve reviews; everyone can contribute and read the individual chore discussion. Resolving a review does not apply a suggestion or delete it. Ginaria can open **Review inbox → Resolved reviews → Reopen review**, then confirm. This returns the same saved review to the open inbox, records the owner action, and sends no duplicate DM. Edits change future point awards and schedules deliberately.

## Add, edit, archive, and restore

Open **Manage chores → Add chore**, choose a schedule and any days, then fill in the name, instructions, points, and optional room. New chores default to five points; explicit zero is allowed. New chores are shared unless assigned afterward. Duplicate names, including archived names, are rejected.

Open a chore card → Edit chore. Edit details changes the name, instructions, points, and room. Change schedule replaces the cadence. Existing claims, reservations, and earned points remain. A switch to monthly/one-time can require releasing incompatible weekly reservations first.

**Archive chore** hides a chore after confirmation. **Archived chores → Restore** brings it back with its saved state. The older !deletequest command now archives too. The older !resetquest command directs you to safe Undo rather than reopening work without correcting its points. Older add/edit commands share the same validation where supported; routine household use should start with /chores.

## If something goes wrong

- **Old or expired buttons.** Use Refresh, or click the old control: it restores fresh controls in the same place without repeating the old action. You can also reopen /chores → Continue where I left off. Screens from before this update need a fresh /chores once.
- **This chore changed.** Read the refreshed card; someone else or a reset changed its state.
- **Nothing matches.** Clear filters and check another time tab.
- **Away today.** Check Who’s home? and coverage; responsibilities have not disappeared.
- **Feedback DM missing.** Check the owner inbox; the saved review is authoritative.
- **Trade not transferred.** The recipient must accept, and neither responsibility may have become stale.
- **Undo unavailable.** Later work or changes prevent an automatic safe reversal; no second award or partial reversal is performed.

Administrator setup and deployment instructions are in BUTTON-BOARD.md and the household’s How I Do Things manual.

## What can be changed or undone?

This table describes available controls, not a promise that every action has universal Undo.

| Action | Change or reverse it | Limit |
| --- | --- | --- |
| Claim, weekly reservation, ongoing assignment | Drop or Reassign from the chore card. | Earned points stay with the completing person. |
| Done | Completing person uses Undo; ginaria can correct another person through Completion history, with confirmation. | Latest completion for the original person first; later state changes or a points reset can prevent correction. |
| Reassign or accepted trade | Reassign again or arrange a new accepted trade. | No one-click reversal of the original transfer. |
| Pending trade | Sender cancels; recipient declines or accepts. | Accepted proposals are not cancelable. |
| Name, instructions, room, point value, regular schedule | Edit the chore again. | No edit-version restore; a regular schedule change clears an occurrence move. |
| One occurrence moved to another date | Cancel occurrence move, or replace its date. | Does not restore a previous move automatically. |
| Missed chore skipped | Change future missed-work policy. | No control to recover that missed occurrence; no completion or points were awarded. |
| Archive | Restore from Archived chores. | Restores saved state, not an earlier version. |
| Trip or attendance exception | Edit dates or cancel the exception. | No generic restore button for a canceled exception. |
| Feedback and point suggestions | Submit follow-up feedback; latest point vote per person is shown. Ginaria can reopen a resolved review with confirmation. | No edit/delete feedback button; reopening sends no duplicate DM. |
| AM/PM split | Edit or archive either resulting chore. | No merge-back control; original history stays with the original chore ID. |
| Points reset | Ginaria can undo through Reset history / Undo, with confirmation and an audit record. | Newer score activity for any affected person blocks the whole restoration; no arbitrary point adjustment. |
| Help status | Responsible person updates the note; any household member can mark resolved with confirmation. | Earlier notes remain in Status history; resolving does not complete the chore. |
| Duplicate chore | Review a new name and confirm; archive the copy if no longer needed. | No source assignments, history, checked steps, or earned points are transferred. |
| Checklist progress | Check/uncheck steps for your current due responsibility. | New occurrences start fresh; changing step definitions restarts progress. |
| Personal reminders | Change your times or turn off. | Already-sent DMs cannot be recalled; uncertain deliveries are not automatically retried. |
| Trade notifications | Toggle on or off. | Already-sent DMs cannot be recalled. |

Remaining improvements to consider: arbitrary owner score adjustments with an audit and reversal, correction after later work makes safe completion reversal impossible, editing feedback, and recovering a skipped occurrence. Point redemption is also not implemented; personal reminders are available as described above. None of these are implied by the current guide.


## Keep your place when screens expire or change

**Refresh** brings the current information back into your private screen. After ten minutes or a restart, an old button or selection refreshes the saved location first; it does not perform that old action. Review the new controls, then choose Done, Claim, or another action again if still appropriate.

Your page, tab, search, filters, chore card and return path, and calendar date/view are kept. If a list becomes shorter, Sprig uses the nearest available page and tells you. Reopening **/chores → Continue where I left off** restores your last saved location after a restart. Your saved place is private to your Discord account and household.

If another person changes chores while your screen is open, navigation still opens current information normally. An outdated action refreshes your location and explains that no action was taken. Expired confirmations return to the relevant card, scores, or other safe parent view so you can review a new confirmation. Unsaved form text is not recovered. If a saved location no longer exists, Sprig returns to the dashboard.

After this feature is first deployed, reopen /chores once. Earlier messages were created without recovery information and cannot gain it retroactively. No private screens are posted publicly or automatically polled.

## Find work needing attention

Open **Dashboard → Needs attention**. This private household view shows each chore once, with every applicable label: **Overdue**, **Needs someone**, and **Blocked** (Stuck, Need supplies, or Need help). Counts can overlap. Help notes and current responsible people appear beside the schedule and points. Open a chore card to claim, reassign, complete, or review its help status; Back returns to your page. Previous and Next sit below the page number. Refresh restores the view after expiry or restart.

Needs someone includes unfinished work due now without a current owner; next week's reservation does not cover this week. Overdue means its scheduled day or shift has ended, or a flexible weekly/monthly period has ended. Due today alone is not overdue. Moved occurrences use the end of the moved day. One-time chores have no overdue deadline. Completed, archived, skipped expired occurrences, and resolved help notes are excluded as appropriate.

For flexible daily, twice-daily, weekly, and monthly work without a recorded occurrence date, the first attention check saves the end of the current period. That date persists while the occurrence remains unfinished. Sprig does not guess historical missed dates before tracking began. This tracking does not change the chore's schedule, missed-work policy, ownership, points, or history.

## Repeated clicks and simultaneous changes

If two people try to take the same chore or weekly responsibility, one succeeds and the other sees current information. Done awards points once per occurrence. Completing separate chores still awards both sets of points without counting the same streak day twice.

Old actions require fresh review after a chore changes, even if its owner or settings later return to the original values, or its completion is undone. Reopen the chore and choose again deliberately. An old weekly Release cannot remove a new reservation. A stored trade becomes outdated if either chore changes; propose a fresh trade instead. Pending trades created before this protection was installed may also require a fresh proposal.

If Discord fails after an action saves, check the current card or Refresh before trying again. Sprig does not automatically repeat uncertain actions. When Done competes with Drop, Reassign, accepting a Trade, or changing the regular day, the first valid action saves and the outdated action asks for review. Earned points and recorded completions remain attached to the completing person.

## How reminders follow changes

Reminder times belong to your Discord account, not individual chores. Reminders are personal opt-in, with up to ten Eastern times. A chore edit or reassignment does not turn on another person's reminders.

Before handing a reminder to Discord, Sprig refreshes the current names and full list of due responsibilities, applies occurrence resets and Skip if missed, and rechecks your preferences, home/away status, household location, and reminder time. Completed, dropped, reassigned-away, archived, moved-to-future, and future scheduled work is excluded. Newly assigned, restored, or newly due work can be included if it arrives while that reminder is being prepared. Trades and the Sunday 6 p.m. handoff use current ownership; trip exceptions and alternating weeks use current availability.

An empty or away reminder time is recorded as skipped. Taking work afterward does not backfill that skipped reminder; it can appear at your next chosen time. Prior-week reminder times are not sent after Sunday handoff. Slots more than 15 minutes old are not sent, and a slot that expires during recipient lookup is canceled. The Reminders screen explains skipped and canceled results.

Each account/time slot is handled once. Opting out or changing times while a reminder is being prepared cancels the old attempt. Failed or uncertain sends are not automatically retried. A message already handed to Discord cannot be recalled when chores change afterward; open /chores for current information.

A moved weekly or monthly occurrence that is skipped waits until its next regular period before becoming due again. The saved next-period date survives restart and changes between Keep and Skip. A late check after that regular period has already begun does not skip the current period. Points, assignments, and completion history are preserved.

## Claim directly from Pick up chores

Press **Claim** beside a due unclaimed chore, then choose **Just this occurrence**, **This week**, **Next week**, or **Repeating weekdays / shifts** as available. Claiming awards no points and does not check checklist steps. Repeating days pause while away. Click the chore name for instructions without claiming it. Away and future occurrence action buttons are disabled; expired controls refresh without repeating an action.

### Calendar starts with today

Calendar on the Dashboard opens today’s dated chores in Eastern time. Use Previous day, Today, or Next day to change dates, or Week and Month to see the broader schedule. Existing saved screens still resume their selected date and page.


## Update announcement

If ginaria enables automatic announcements, a new installed Git commit posts
once after startup in the configured household chores channel: **Sprig has been updated to version 1.2.0. Open /chores for fresh controls.** A short “What’s new” sentence describes changes since the previous release, followed by the announcement date and time in Eastern time, including EDT or EST. This release is version **1.2.0**; the timestamp records when the notice is posted, including when the owner announces manually later. Each installed Git commit remains a separate update for duplicate prevention. There are no mentions or mass pings. Open /chores again to get
the updated controls; existing chores, assignments, points, and history remain.

Restarts and Discord reconnects on the same release do not post again. A saved
per-release delivery claim prevents duplicate announcements, including concurrent
ready events. If delivery is uncertain, it is logged without automatic retry.
Missing Git/version information or an unconfigured board produces no notice.
Channel lookup must match the saved household and channel, and a changed
destination cancels the attempt. Announcement failure does not stop the bot.
Offline tests mock channel delivery; deploying the code does not itself post a
notice until Sprig starts with the approved feature installed.


### Chore-name, Claim/Done, and Skip buttons

Each list row has a chore-name button, Claim/Done, and Skip. The name opens details without changing responsibility. Claim opens the duration choices; Done opens an unfinished checklist or completes eligible work. Skip requires confirmation and keeps future repeats and saved responsibilities. Future/completed action buttons are disabled.

## Owner announcement choices and horizontal pickup card

Ginaria opens **Dashboard → Update announcements**. Automatic announcements
default **Off**, including when upgrading from the earlier always-automatic
release. This gives a quiet restart until the owner deliberately enables them.
The switch persists across restarts. Turning it on applies to future starts; it
does not post immediately. Turning it off during preparation cancels that
automatic attempt before sending.

**Announce this update** works even while automatic announcements are off. It
shows the exact message and destination, then requires Confirm. Cancel posts
nothing. Owner checks apply again at confirmation, and changed destinations or
expired screens require fresh review. There is still at most one attempt per
release: already posted or uncertain notices cannot be reposted by the button.
No pings or new personal DMs are added.

Pick up chores uses a Components V2 frame containing chore-name, Claim/Done, and Skip button rows. Discord controls the actual width; serialized tests verify validity and limits, while real appearance still needs a Discord check after deployment.


### Fixed pagination controls

Paged workspace lists always show Previous on the left and Next on the right,
in the same pagination row. Previous is greyed out on the first page; Next is
greyed out on the last. Both are greyed out for a single-page or empty list.
Disabled buttons do nothing and never change chores or jump pages. Calendar day
lists use Previous page / Next page; moving to another day remains separate.


### Consistent pickup rows

Rows are button-only controls with the day/period marker, chore name, shift where applicable, and points on the name button. Claim/Done and Skip follow it in the same native action row. The name stays clickable while unavailable actions are disabled. Other information is on the chore card. Discord determines actual button widths and wrapping; verify the appearance in Discord after deployment.

## Pickup and My chores rows

Click a chore-name button to open instructions and its named actions. Claim opens signup-duration buttons, including repeating weekdays on daily chores. My chores has Done and Skip beside each name. The saved filters, five-item default pages, and fixed Previous/Next positions stay in place.

### Pickup list footer

Below the chore card: Previous / Next, then Due now / This week / Next week /
All chores, then Search / Filters / Refresh / Dashboard. Refresh is the single
recovery control: it reloads current information and keeps your place after
expiry or restart. There is no separate Refresh row in Pick up chores.
The footer shows the page number and Eastern time; week ranges remain in the
weekly view heading. Other screens retain their existing recovery controls.


### Dashboard groups

The private dashboard groups controls by purpose: Do chores (My chores, Pick up chores, Needs attention, Manage chores); Plan & coordinate (Calendar, Household chores, Who’s home?, incoming trades); My settings (Reminders, Notifications, Points & standings, Continue where I left off when available, Refresh); and Owner tools (review inbox, update announcements, household setup when permitted). Help sits beside the dashboard heading. Points and streak appear at the top. Non-owner members with setup permission find Household setup under Plan & coordinate. Refresh safely restores an expired screen after a restart; owner permissions remain unchanged.


### Calendar day layout

Calendar days have chore-name buttons with compact responsibility/points summary buttons. Page controls stay below the page count, followed by Previous day / Today / Next day, then Week / Month / Back / Refresh / Dashboard. Clicking a name opens its current card today or a schedule preview on another date; it never claims or reschedules work. AM/PM repeating owners are shown for the selected date.

### Household list layout

Household uses chore-name, Claim/Done, and Skip buttons. The Taken button identifies the current responsible person when it is someone else. Click the name for the full schedule and repeating weekday assignments. Time tabs, grouping/unclaimed controls, Search, Filters, Refresh and Dashboard remain visible; Back and Refresh preserve the view.

### Points & standings layout

Your points and streak appear together at the top, followed by a compact framed ranking list. Fixed Previous / Next buttons follow the page count. Owner reset and reset-history controls are grouped under Owner controls; everyone has one Refresh / Dashboard row. Refresh restores the current ranking page after expiry or a restart. These display changes do not change points, streaks, history, permissions, or reset confirmations. Points do not currently redeem rewards.


### Consistent workspace style

Workspace screens use compact framed content and one Refresh button. Lists retain fixed page controls; primary actions and selects stay above a shared Back / Refresh / Dashboard row where available. Small adjacent action groups share rows when they fit. Calendar navigation keeps its date groups. Instructions, warnings, confirmation text, owner permissions, and private recovery rules are preserved. My chores retains inline Done and Checklist actions. Refreshing an expired confirmation returns safely without applying it.


### In-app Help

Help starts with a short path for doing a chore, taking work, or looking ahead. The topic buttons use concrete tasks (for example, Finish a chore, Set reminders, and Drop, reassign, or trade). Each topic gives the actual button path and explains the result in short paragraphs. Earlier saved help topics map to the matching new topic; an unknown old topic returns to Start here. Help is private and never changes chores or points.


The dashboard uses one compact framed menu with small group labels. Points and streak sit directly under its title, with Help beside the heading. The same groups, permissions, and recovery controls remain available.


### Personal list length

My settings → List length saves 1–5 items per page for your own account; the default is 5. Previously saved longer lists display five items without changing household data. It applies to chore lists, calendar days, standings, and completion/help-history lists. Detailed review and reset records still open one at a time. Chore pages keep chore-name, Claim/Done, and Skip buttons and fixed Previous/Next paging. Time views, Search, Filters, and Dashboard stay visible below the list, with one safe Refresh button. The combined View & tools menu has been removed. Old saved chore/calendar views keep the same approximate item position when the size changes. Other people’s preferences, chores, points, and history are unchanged.


### Compact secondary screens

Metadata shares short lines where readable; instructions, feedback, and confirmations keep their line breaks. Checklists show steps with progress. Week calendars have seven date buttons; month grids keep their formatting and date choices open buttons. Setting and account choices open button screens, with paging and Apply selection where needed. Permissions and confirmation boundaries are preserved.

### Workload & pace

Open Plan & coordinate → Workload & pace. Each person has earned and planned daily, weekly, and 30-day monthly point rates, plus points per home-day, today’s earned points, projected household share, away coverage, and current due points. Compare past/next 7, 28, or 90 full days; sort by planned load, earned pace, or name. The past ends yesterday and starts no earlier than the first recorded completion. Undone work is excluded; resetting a balance does not erase earned-work history. Future ownership is taken only from saved assignments and dated signups; unclaimed work stays visible. Flexible weekly/monthly work is prorated over its period, not assigned a made-up due day. Undated one-time work is shown separately. Forecasts assume normal completion pace and use current point values; they do not guarantee earnings. Home-day comparisons use the current rotation and saved exceptions, splitting Sunday at 6 p.m.; past attendance edits can change that denominator. The view is private and read-only.


### Home/away defaults for anyone

Who’s home? accepts any household person. With no custom default, Kas and Zel follow their saved alternating weeks (Sunday 6 p.m. Eastern); everyone else is home daily. Usual schedule can change any selected person to home daily, away daily, selected home weekdays, or same/opposite alternating weeks. Review & save confirms the affected people; Use household default restores the original behavior. Mark home / Mark away and Quick dates can override any individual date or trip. Dated overrides take priority over every default and expire back to it. Existing chores, signups, points, and date exceptions are preserved. Changes are recorded and stale bulk edits are rejected together. Reminders, coverage, signup checks, and workload/home-day calculations use the effective schedule. Changing a default can change historical home-day denominators because attendance defaults are not historical snapshots.


## Skip only the current occurrence

Open a due repeating chore’s **chore name → Skip this occurrence**, then confirm. Anyone in the household can do this. It awards no points, creates no completion credit, releases a single-occurrence claim, and keeps weekly sign-ups, ongoing assignments, completed history, and the regular schedule. Morning and evening are separate occurrences: skipping morning leaves evening available at its normal time.

The next occurrence opens at the next regular boundary: midnight for daily work, noon/midnight for twice-daily, the next AM/PM shift, the next selected weekday, Sunday at 6 p.m. for flexible weekly work, or the next month for monthly work. A moved occurrence returns to the regular schedule. Old checklist checks and help notes stay recorded but do not carry into the next occurrence. Skips are recorded separately from completions. There is currently no Undo skip control. Completed, future, archived, and one-time chores have no Skip button; archive a one-time chore if it is no longer needed. **Skip if missed** remains a separate automatic policy.
