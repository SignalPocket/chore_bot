# Sprig household chore guide

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
| Needs help | Shared active obstacles: Stuck, Need supplies, or Need help, with notes and resolution. |
| Reminders | Your own opt-in reminder times and off switch. |
| Notifications | Opt in to private trade notifications for your own account. |
| Help | Short task-oriented explanations, including the color legend. |
| Review inbox | Ginaria’s queue of household feedback. This button is visible only to ginaria. |
| Household setup | Administrator-only selection of Kas and Zel’s Discord accounts. |

The saved shared dashboard has six entry buttons. Each opens private controls. Your private dashboard includes personal counts and permitted owner/setup tools. **Back** returns to the previous screen; **Dashboard** goes home. Most navigation edits the current private message. Validation errors may appear as a separate private message.

Private controls expire after ten minutes of inactivity or a bot restart. Reopen /chores when that happens. A screen does not update live when someone else changes a chore; use Refresh or reopen it. A stale action may be rejected so it cannot apply to changed work.

## Read a chore card

Lists use Discord Components V2 with five chores per page. Previous and Next sit directly below the page numbers, above the chore picker and view tabs. Each row has Done beside work you own and can complete now; otherwise it has Details. Away-day Done buttons are disabled. Pressing Done refreshes the same private list. Details opens the chore card for instructions and other actions. Discord controls the actual width on each device.

Select a chore from My chores, Pick up chores, or Household. Each route opens the same card:

- **Responsibility.** Who owns it and for how long.
- **When.** Its regular schedule, current occurrence, and missed-work setting.
- **Points and room.** Points earned for one completion and the optional room.
- **Instructions.** What counts as done.
- **Actions.** Appropriate buttons and a More actions menu.

The three responsibility durations are **Just this time**, **This week / Next week**, and **Every week · ongoing**. A chore’s name does not assign it: a chore called “Kas: laundry” still needs an actual Discord-account assignment or sign-up.

## Separate morning and evening responsibilities

Use **Daily · AM** and **Daily · PM** when different people should handle morning and afternoon/evening work. Each shift has its own sign-ups, weekly owner, completion, and points. AM opens at midnight; PM opens at noon, Eastern time. Each shift follows its own Keep overdue or Skip if missed setting.

For an existing twice-daily chore, open its card → **More actions → Separate AM and PM sign-ups**, then confirm. The existing chore becomes AM and a separate PM chore appears. Existing weekly reservations and ongoing ownership stay with AM; PM starts open, except an existing single PM claim follows the PM shift. Both keep the original points and instructions. Already-earned points and completion history are preserved, and an already-completed shift cannot earn points again that day. Splitting after noon starts an unfinished AM shift the following morning.

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

Open a chore card → **More actions → Estimate / checklist**. Anyone in the household can edit these. Enter estimated minutes for one completion (1–1440), and up to 12 checklist steps, one per line, each up to 80 characters. Blank fields clear the estimate or checklist. Estimates are approximate and do not change points. A twice-daily chore has this estimate for each of its two completions.

Lists show the estimate and checklist progress. An inline **Checklist** button replaces Done when steps remain. Only the person responsible for the current, due occurrence can check or uncheck its steps. Progress follows the occurrence when it is reassigned. Finish the steps, then press **Done**; checking boxes alone awards no points. A complete checklist offers Done directly. Other people can read its progress.

The next occurrence starts unchecked. An unfinished Keep overdue occurrence retains progress; Skip if missed starts a fresh checklist when it advances. Changing checklist wording clears active progress, even when old wording is restored later. Changing only the estimate keeps progress. Completion Undo restores access to the prior occurrence’s saved progress when the usual safety checks allow it. AM/PM splitting copies the estimate and steps into both resulting chores.

## Personal chore reminders

Open **Dashboard → Reminders**. Reminders start **off** for everyone. Turn on authorizes private Discord DMs to your own account only. **Change times** accepts one to three 24-hour times separated by commas, such as `09:00, 17:00`. Defaults are 9 a.m. and 5 p.m. Eastern. Changing times keeps your current on/off choice; **Turn off** stops future reminders. Nobody can opt another person in through these controls.

Each reminder lists your currently due, unfinished responsibilities, with estimates and progress. Unassigned work, archived chores, completed work, and upcoming work are excluded. No reminder is sent while you are away or have nothing due. Use the household-channel link in the DM, then /chores, to act on it.

Delivery is checked each minute with a 15-minute grace window. Older missed reminders are discarded after downtime. A daylight-saving time that does not exist is skipped; a repeated clock time sends at most once. Discord may block DMs: the last delivery result appears in Reminders. Failed or uncertain delivery is not automatically retried, to avoid duplicates. Turning off cannot recall a message already being sent.

## Calendar

Open **Dashboard → Calendar**. Switch **Week / Month** or **My calendar / Household**, and use Previous, Today, and Next. Week view uses colored weekday headings with dates, counts, and known estimated minutes. Month view shows a Monday-first grid and two date pickers. Choose a day to open its chore list, including responsibility and away warnings. Each day shows Page X of Y and the chore range. Previous page / Next page sit directly below that count; Previous day / Today / Next day move between dates without returning to the calendar. Date changes start at page one. Personal/household scope and Week/Month mode are retained, including when returning from a chore card.

**No fixed day** keeps flexible weekly/monthly/one-time chores separate rather than inventing a date. Move an occurrence or choose a regular day to put it on a date. Its owners are shown for the selected date’s household week. Daily AM and PM appear as separate chores; a twice-daily chore’s known workload counts both completions.

This is a schedule preview inside Discord, not an external calendar sync, historical activity report, or drag-and-drop rescheduler. Past dates do not reconstruct every earlier assignment. Sunday ownership is shown before the 6 p.m. handoff and can change that evening. Overdue chores remain in Due now. Selecting a future date does not create a claim or let someone complete future work; **Open current chore** explicitly returns to the actual current chore controls.

## Stuck, supplies, and help

Open the chore card → **Stuck / need help**. The person responsible for the current due, unfinished occurrence can choose **Stuck**, **Need supplies**, or **Need help**, then add a note. Notes are shared household information, even though controls are private. They do not drop responsibility, mark the chore Done, change points, or send an automatic DM. An away person can still explain why their due responsibility needs help.

The current status appears on chore lists and the card. **Dashboard → Needs help** collects active issues so everyone can see what needs attention. The status follows the unfinished occurrence if it is reassigned or moved; the new responsible person can update it. Editing checklist steps or the time estimate does not remove the help note.

Anyone using their own household controls can **Mark resolved**, with confirmation, after the obstacle is handled. This clears only the active status. Updated and resolved notes remain in **Status history**, including who reported or resolved them. Cancel leaves the status unchanged. A completed, archived, or advanced occurrence no longer appears as actively needing help. If a completion is safely undone, its previous occurrence’s unresolved status is visible again. Normal Done and checklist requirements still apply.

## Duplicate a chore

Open a chore card → **More actions → Duplicate chore**. Enter a distinct new name, review the confirmation, then save. Everyone can do this; it is not owner-only. Repeated clicks or a retry after an uncertain response reopen the same saved copy rather than creating another.

The copy keeps the source’s instructions, regular schedule, points per completion, room, difficulty, time estimate, checklist steps, and Keep overdue / Skip if missed policy. It starts **unassigned, unfinished, and unchecked**, with fresh recurrence timing. Assignments, claims, weekly reservations, completion records, earned points, help notes, and one-off occurrence moves are not copied. For example, copying Kas’s laundry does not give the new chore to Kas automatically. Rename it and assign it deliberately.

Duplicate names are rejected even if the existing chore is archived. If source settings change while the form is open, reopen Duplicate chore and review the current version. If a copy is no longer needed, archive it; the original remains unchanged.

## Take work and finish it

From an available chore’s card:

- **Just this time.** Claim the current occurrence.
- **Take this week / Take next week.** Reserve its repeating responsibility for that household week.
- **Every week · ongoing.** Confirm an assignment that continues until dropped or reassigned. This is offered when it does not conflict with weekly reservations.

Open your chore card and press **Done** when the work is finished. Points are awarded once for the occurrence. An ongoing assignment or weekly reservation stays yours after completion. Daily work returns the next day; twice-daily work returns in its next slot.

## Drop, reassign, or trade

Use the chore card’s **More actions** menu.

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

Open a chore card → More actions → Edit chore. Edit details changes the name, instructions, points, and room. Change schedule replaces the cadence. Existing claims, reservations, and earned points remain. A switch to monthly/one-time can require releasing incompatible weekly reservations first.

**Archive chore** hides a chore after confirmation. **Archived chores → Restore** brings it back with its saved state. The older !deletequest command now archives too. The older !resetquest command directs you to safe Undo rather than reopening work without correcting its points. Older add/edit commands share the same validation where supported; routine household use should start with /chores.

## If something goes wrong

- **Old or expired buttons.** Open /chores again.
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
