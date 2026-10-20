# Sprig household chore bot

Sprig provides private Discord buttons for choosing chores, weekly responsibilities, completion and points, trades, household schedules, attendance exceptions, chore feedback, checklists, time estimates, personal reminders, calendar previews, shared help statuses, and chore duplication.

Start with **/chores** in the household server.

- [Household user guide](USER-GUIDE.md).
- [Implementation, tests, and deployment](BUTTON-BOARD.md).

Run the offline regression suite with `python test_chore_board.py -q`. It uses temporary databases and mocked Discord delivery. Deploy all eight runtime modules together (including chore_recovery.py), preserving the existing server database and environment.

Daily server database backups run independently of Sprig at 03:15 Eastern, with catch-up checks and integrity manifests. See BUTTON-BOARD.md for paths, verification, and the standalone backup helper.


## Laptop backup and failure-alert tools

See [BACKUP-RECOVERY.md](BACKUP-RECOVERY.md) for the installed server/laptop schedules, protected storage, verification, private ginaria alerts, restore commands, limitations, and tests. `backup_monitor.py` runs independently of the bot; `laptop_backup.py` downloads over SSH and encrypts with Windows CurrentUser DPAPI. `install_laptop_backup.ps1` and `run_laptop_backup.ps1` set up the hidden per-user Windows task. These tools do not modify chore records or require a bot restart. Tests: `python -m unittest test_backup_transport -q`, plus `test_backup_database` on Linux. Do not put credentials, snapshots, or local monitor state in Git.


Private screens offer **Refresh / Resume** and `/chores` offers **Continue where I left off**. Expired controls restore saved navigation without replaying their old action. See USER-GUIDE.md for behavior and limits, and BUTTON-BOARD.md for recovery routing and deployment.
