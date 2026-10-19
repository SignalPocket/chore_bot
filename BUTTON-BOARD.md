# Sprig's button chore board

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
