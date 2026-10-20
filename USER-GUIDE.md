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
| Notifications | Opt in to private trade notifications for your own account. |
| Help | Short task-oriented explanations, including the color legend. |
| Review inbox | Ginaria’s queue of household feedback. This button is visible only to ginaria. |
| Household setup | Administrator-only selection of Kas and Zel’s Discord accounts. |

The saved shared dashboard has six entry buttons. Each opens private controls. Your private dashboard includes personal counts and permitted owner/setup tools. **Back** returns to the previous screen; **Dashboard** goes home. Most navigation edits the current private message. Validation errors may appear as a separate private message.

Private controls expire after ten minutes of inactivity or a bot restart. Reopen /chores when that happens. A screen does not update live when someone else changes a chore; use Refresh or reopen it. A stale action may be rejected so it cannot apply to changed work.

## Read a chore card

Select a chore from My chores, Pick up chores, or Household. Each route opens the same card:

- **Responsibility.** Who owns it and for how long.
- **When.** Its regular schedule, current occurrence, and missed-work setting.
- **Points and room.** Points earned for one completion and the optional room.
- **Instructions.** What counts as done.
- **Actions.** Appropriate buttons and a More actions menu.

The three responsibility durations are **Just this time**, **This week / Next week**, and **Every week · ongoing**. A chore’s name does not assign it: a chore called “Kas: laundry” still needs an actual Discord-account assignment or sign-up.

## See your work and find chores

**My chores** has Due now, This week, Next week, Upcoming, and Done tabs. Being away does not erase your responsibilities. Upcoming work stays visible, but cannot be completed before it becomes available. Done lists chores with recorded completions by you; open the card’s Completion history for individual records.

**Pick up chores** offers Due now, This week, Next week, and All chores. Weekly reservations are available only for eligible recurring chores. Monthly and one-time work can be taken when its occurrence is available or assigned on an ongoing basis where applicable.

**Household** offers the same time views, plus By person / By chore / By day and an Unclaimed only filter. A two-day chore appears on both scheduled days; totals count the chore once. Daily work has an Every day group. Flexible work keeps its weekly/monthly label without an invented weekday. The view warns when an owner is away for scheduled work.

Use **Search** for a name or words in instructions. **Filters** can select a person, room, or exact date. The date filter shows dated occurrences; flexible weekly/monthly work has no exact day until a day or occurrence move is chosen. Clear filters to return to the full list. View preferences are remembered for your account while the bot is running.

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

Notes such as “afternoon” or “Wednesday night” are instructions. They do not create timed reminder messages. Missed occurrences do not build up a separate backlog of copies.

## Trips and traded days

Open **Who’s home?** and choose one or more people. Select Mark home, Mark away, or a quick date shortcut. Dates accept YYYY-MM-DD, MM/DD/YYYY, MM/DD in the current year, today, or tomorrow. The last day is included. Check the readable preview before confirming.

Select a saved exception to **Edit dates** directly or **Cancel exception**. Editing retains the old record as inactive history. An overlap with a different exception is rejected; open the existing exception to revise it. A group trip is saved for all selected people together or none if any conflicts remain.

Exceptions cover full Eastern calendar days. They temporarily override attendance, then normal rotation resumes. They preserve chores and reservations; check Household for coverage warnings and reassign or trade work as needed. Fixed-day reservations require the person home on the scheduled days. Partial-week daily responsibilities may need coverage.

Kas and Zel’s base rotation changes Sunday at 6 p.m.; October 18, 2026 begins an away week. An administrator must select their actual accounts in Household setup. Their base home/away chore schedules, such as recycling, do not move automatically with individual trip exceptions.

## Feedback, effort scores, and the owner inbox

From a chore card choose **Give feedback**. Add comments, a better day/time, suggested points, or any combination. Common effort scores are 0, 1, 2, 3, 5, 8, 13, and 21; other nonnegative whole numbers are accepted. Leave points blank for a comment without a vote. The latest point suggestion per person appears once; earlier reviews stay saved.

Feedback is household information displayed through private controls. It is not an anonymous or confidential message to the owner. New feedback is also DMed to ginaria. If Discord blocks the DM, it remains saved in the inbox. Older feedback appears in the inbox without a DM backlog.

Ginaria’s **Review inbox** opens each review directly. **Resolve and next** advances the queue. **Edit chore** opens the relevant settings. Only ginaria can resolve reviews; everyone can contribute and read the individual chore discussion. Resolving a review does not apply a suggestion or delete it. Edits change future point awards and schedules deliberately.

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
