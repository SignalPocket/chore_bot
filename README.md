# Sprig household chore bot

Sprig provides private Discord buttons for choosing chores, weekly responsibilities, completion and points, trades, household schedules, attendance exceptions, and chore feedback.

Start with **/chores** in the household server.

- [Household user guide](USER-GUIDE.md).
- [Implementation, tests, and deployment](BUTTON-BOARD.md).

Run the offline regression suite with `python test_chore_board.py -q`. It uses temporary databases and mocked Discord delivery. Deploy all six runtime modules together, preserving the existing server database and environment.
