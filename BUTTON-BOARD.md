# Sprig's button chore board

## Fresh controls without jumping through chat history — prepared update

**/chores** opens a fully private set of chore buttons at the current chat position. Only the caller sees the panel, lists, and confirmations. **!chores** also opens fresh buttons at the current position, but Discord text commands require an ordinary public starter message; every subsequent button action responds privately. It explicitly tells users to use /chores for zero public bot messages. Command messages and old panels are not deleted automatically.

Both entry points work in channels of the configured household server where the caller already has access to the canonical chores channel and message history. The existing pinned panel and !board link remain available. Fresh controls expire after ten minutes or a restart; open a new panel when needed.

After an approved deployment/restart, an administrator runs **!enableprivatechores** once in the household server to register /chores. Registration is explicit, not performed automatically at startup. It refuses to sync if doing so would remove unrelated existing server slash commands. The local slash-command handler is restored on restart without remote synchronization. All registration/posting approval rules remain in force for assistant actions.

**41 offline tests passed**, including fresh controls, private slash responses and follow-ups, existing channel access, and safe command registration. No live slash registration, push, or deployment has occurred for this prepared update.

## Find the board — prepared shortcut

Anyone in the household server can type `!board` from any channel to get a link to the saved existing panel. It does not repost the board or alter chores. The person must already be able to view the chores channel and its message history; it does not reveal another server's board. If setup is missing or pending, it asks the household to inspect setup without creating a duplicate.

This shortcut is a separate local update after deployed release f776dff. The complete suite now has 37 passing offline tests, including shortcut access, existing-message reuse, and pending setup.

## Editing and weekday / twice-daily schedules — latest prepared update

Everyone can use **Edit chore**: choose an active chore by name, then **Edit details** to change its name, instructions, or future points, or **Change schedule** to choose a replacement cadence and submit the prefilled form. Concurrent changes invalidate old forms. Editing retains existing assignments, claims, completion state, and earned points. A change to monthly/one-time is blocked while weekly sign-ups remain; release those first.

The schedule picker now includes **On a specific weekday** and **Twice daily** as well as Daily, Weekly, Monthly, and One time. Pick the weekday from a second dropdown. A weekday chore appears at midnight on the selected day, remains due if missed, and after completion returns the next selected weekday. It can be reserved in Weekly sign-ups before it is due. Times such as Wednesday night can be recorded in instructions; there are no automatic reminder messages or hour-specific deadlines.

Twice-daily chores have a morning slot (midnight to noon) and an afternoon/evening slot (noon to midnight), in the configured household timezone. Each slot awards points once; the second slot does not become available early. Missed slots do not accumulate. A weekly reservation keeps the same owner across slots. Dishwasher filling and emptying remain separate chores: choose Twice daily on each if wanted; this update does not create or change live chores automatically.

This release adds `chore_timing.py`, required beside `chore_board.py` and `sprig_bot.py`. Include that file in the approved commit and deployment. Run compilation for all three modules and `test_chore_board.py -q` in an isolated/test environment. **34 offline integration tests passed**, including weekday readiness and overdue behavior, noon/midnight resets, daylight-saving changes, editing without changing earned points, duplicate names, concurrent changes, and weekly-owner preservation. These changes are local only until explicitly approved for push and deployment.

## Add chores inside Discord — prepared update

Everyone who can use the configured household panel can use **Add chore**, choose Daily / Weekly / Monthly / One time, and fill in the chore name, optional instructions/timing, and optional points. Blank points means zero. New chores are shared, open for sign-up. Names are checked against existing chores, including completed ones, to avoid duplicate submissions. Personal chores need distinct names, such as Katie's laundry; the form does not automatically create a separate task for every household member or assign a specific member.

Everyone can also use **Remove chore**: choose a chore by name, then **Confirm removal**. This hides it from everyone's lists and weekly sign-ups while preserving the chore record, points, claims, and sign-up history. **Removed chores → choose chore → Restore** puts it back. Completed work remains completed for the current cycle; restoring does not reset points. Old open views cannot complete or reserve a removed chore. This is reversible removal from the board, not permanent deletion.

Specific days and times entered in notes are descriptive; this form does not implement automatic weekday reminders or twice-daily resets. Daily resets at midnight, weekly Sunday at 6 p.m., and monthly at the start of the month.

This update adds **Add chore** plus the administrator command `!refreshchoreboard`, which edits the saved panel in its existing channel without posting another board or changing its chores/sign-ups. After deploying and restarting the approved update, an administrator runs that command once to reveal the new button. Editing the live panel requires the normal delivery approval if performed by an assistant. The old deployed release adfe8c2 does not contain this update.

Twenty-six offline tests passed for the prepared update, including non-administrator submission, invalid input, duplicate prevention, view ownership and channel checks, removal confirmation, restoration without data loss, stale completion/removal buttons, and refreshing the existing panel. These are separate from the 17 server tests for adfe8c2 recorded below.

Family members use a single shared message:

**Open chores** → choose a chore by name → **Claim**.

**My chores** → choose a chore → **Done** (or **Release** to put a claimed chore back).

**Weekly sign-ups** → **This week** or **Next week** → choose a chore → **Sign up for week**.

A week runs Sunday at 6 p.m. through the next Sunday at 6 p.m., America/New_York. Signing up for a daily chore keeps it yours after each daily completion; it returns to My chores the next day without claiming again. Weekly chores still need only one completion. Use **Release week** in Weekly sign-ups to relinquish the responsibility; prior completions and points stay recorded. Preassigned, monthly, and one-time chores are not offered for week-long sign-ups.

Different people can reserve the same chore in different weeks. Current-week sign-ups respect existing occurrence claims. Next-week ownership activates automatically at the handoff and takes precedence over an unfinished previous occurrence claim. Old buttons opened before the handoff cannot silently act on the new week.

## Kas and Z

During initial activation, a server administrator uses **Household setup**, selects Kas and Z's two actual Discord accounts, checks the displayed names, then taps **Save household**. Display names are not used to guess identity. The local source contains no invented account IDs; this configuration is required before their schedule can be enforced.

The anchor is Sunday, October 18, 2026 at 6 p.m., the start of an away week. Their next home week is October 25 at 6 p.m. through November 1 at 6 p.m. The pattern repeats every two weeks and follows Eastern wall-clock time through daylight-saving changes.

During away weeks they cannot claim or complete chores or reserve that away week. They can reserve next week's chores when that is a home week. Other household members are available every week. Existing individual occurrence claims belonging to an away member are reopened; chore records, completed work, points, and past weekly sign-ups remain. Preassigned chores are not automatically reassigned to someone else.

Configure the accounts before taking weekly sign-ups. Changing the alternating accounts while current or future sign-ups exist is blocked, to avoid unexpectedly invalidating reservations. Complete/release those reservations before reconfiguring.

The personal lists are visible only to the person who opened them. Claims and completion are shared in the existing database. A claimed chore disappears from everyone else's open list. Preassigned chores go straight into the assigned person's My chores list. The board shows 20 chores per page, with Previous, Next, and Refresh controls.

## Prepared changes

- `chore_board.py` adds the interface and reuses the existing claim, unclaim, and completion logic, including points and streaks.
- `sprig_bot.py` installs that interface before starting the bot.
- A new `chore_board` table remembers the shared message location. Existing chore records are retained.
- The shared buttons are registered at startup and survive restarts. Private lists last ten minutes; open a fresh list from the shared message after expiration or restart.
- Old selections are checked against current ownership and completion history before saving. Double completion does not award points twice.
- Existing text commands continue to work.

## Activation steps — not performed

1. Back up the actual server code and `sprig.db` while the bot is stopped. Keep configuration and credentials on the server.
2. Put `sprig_bot.py` and `chore_board.py` together in the existing bot directory. The review copy's requirements list discord.py 2.4 or newer, below 3, python-dotenv, and tzdata; check the server environment before updating dependencies.
3. Start the bot with the existing service and environment, preserving the existing database location.
4. A household server administrator runs `!choreboard` once in the intended chores channel. It posts the shared panel. Pin that message using Discord's menu. Family members do not need to type commands. If upgrading a panel already posted by the earlier version, use its Open chores and My chores buttons as before; after deploying this version, the existing panel would need a deliberate administrator edit to show the new Weekly sign-ups and Household setup buttons. This project has not posted a panel yet.
5. Open Household setup and explicitly select/save Kas and Z's accounts before household sign-ups begin.
6. Check with two household accounts: claim, see it disappear from the other person's open list, mark Done, sign up for this week and next week, and reopen after a bot restart.

Repeated setup returns the existing message link. If setup delivery times out, the saved location remains pending and prevents duplicate posting. Inspect the destination first; an administrator can then repair the stored message ID using the actual posted message, or confirm no message exists before clearing a pending setup. There is deliberately no automatic repost or delete.

The new panel is limited to its configured server and channel. The older text commands' existing permissions are unchanged; they are not a substitute for a household/server authorization boundary.

## Remaining schedule limits

This change improves interaction only. It preserves the existing daily midnight, weekly Sunday 6 p.m., and monthly first-day resets in America/New_York (or QUEST_TIMEZONE). These resets do not implement all the day-specific schedules in the new household list.

Week-long sign-ups and alternating-week availability are implemented. Twice-daily occurrences and the individual Monday/Wednesday/Sunday due-day rules from chat are not implemented. The chores discussed in chat have not been imported.

## Verification

Seventeen offline integration tests use a temporary database and dummy token, without connecting to Discord. They cover the original claim/done interface, competing claims, repeated completion, assigned ownership, release, pagination, persistent launcher registration, channel restrictions, duplicate/interrupted setup, weekly competition and release, midnight recurrence with the same weekly owner, exact Sunday handoff, daylight-saving changes, alternating eligibility, account setup, persistent weekly data, and legacy-command enforcement. Live rendering and delivery still require the approved activation and account checks above.

## Button help

Every launcher includes **Help**, which opens a private guide to claims, Done, weekly sign-ups, alternating weeks, schedules, and shared chore management. The dashboard text explains Help and !help. After deployment, an administrator runs `!refreshchoreboard` in the existing chores channel to update the same saved dashboard text and buttons. Fresh `!chores` and `/chores` panels include help automatically.

## Extended schedules

**Twice a week** lets you choose two weekdays. **Every other week** lets you choose a weekday and Kas/Z home or away weeks (away anchor Sunday October 18, 2026 at 6 p.m. Eastern). This supports biweekly dusting/yard checks and away-week Monday recycling. Occurrences become due at midnight and stay due until done, even across a home/away handoff. A late completion moves to the next matching date; missed occurrences do not accumulate. Weekly sign-ups show scheduled weeks, plus overdue chores in the current week. Every-other-week Sunday means midnight before the evening handoff. These schedules are available for both Add and Edit. No existing chore is changed automatically.

## Who’s doing what?

The private household overview shows This week / Next week, people’s assigned chores and weekly sign-ups, current single claims, and Nobody signed up. Completed recurring chores retain their weekly owner. Single claims do not reserve next week. Archived chores are excluded; alternating schedules respect the selected week, with overdue chores included this week. Outstanding monthly and one-time chores are included. Refresh and page buttons update the same private message. After deployment, !refreshchoreboard adds the new button to the existing saved dashboard.

New chores start at **5 points**. The Add form is prefilled with 5; a blank points field in Add or Edit means 5. An explicit 0 is still allowed. Editing a chore keeps its existing point value prefilled. Changes affect future completions, not points already earned.

The responsibility overview resolves display names using the existing command lookup: cached guild member, fetched guild member (server nickname), then cached/fetched Discord user. It waits privately while looking up uncached names. Only failed Discord lookups show an Unknown user fallback.

## Dashboard layout

The saved dashboard and fresh panels use the same three rows: My chores / Open chores / Weekly sign-ups; Who’s doing what? / Help; Add chore / Edit chore / Remove chore / Household setup. My chores is blue; other entry buttons are neutral gray. The existing button IDs, privacy, and permissions are preserved. After deployment, !refreshchoreboard applies the layout and welcome text to the existing saved message; /chores opens the new layout immediately.
