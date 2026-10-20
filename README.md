# Sprig household chore bot

Sprig provides private Discord buttons for choosing chores, weekly responsibilities, completion and points, trades, household schedules, attendance exceptions, chore feedback, checklists, time estimates, personal reminders, calendar previews, shared help statuses, and chore duplication.

Start with **/chores** in the household server.

- [Household user guide](USER-GUIDE.md).
- [Implementation, tests, and deployment](BUTTON-BOARD.md).

Run the offline regression suite with `python test_chore_board.py -q`. It uses temporary databases and mocked Discord delivery. Deploy all seven runtime modules together, preserving the existing server database and environment.

Daily server database backups run independently of Sprig at 03:15 Eastern, with catch-up checks and integrity manifests. See BUTTON-BOARD.md for paths, verification, and the standalone backup helper.
