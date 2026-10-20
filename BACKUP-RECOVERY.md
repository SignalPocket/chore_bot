# Sprig backups and recovery

## What runs automatically

The server creates a verified SQLite snapshot once per Eastern date, beginning at 03:15. The cron check runs hourly at minute 15 and after reboot. The independent monitor both runs the existing snapshot helper and checks snapshot health and the laptop receipt. It works while the Discord bot service is stopped.

The laptop task **Sprig Laptop Backup** runs daily at 04:00 Windows local time, at Katherine's sign-in, and hourly while she is signed in. It catches up when the laptop is awake and SSH is available. It runs hidden, without administrator rights or a saved Windows password. It does not wake the laptop. Windows start-when-available is enabled. SSH uses the existing trusted server host key and ssh-agent; prompts and accepting unknown host keys are disabled.

The task downloads up to the newest 30 available server dates and verifies the manifest, SHA-256, SQLite integrity, and quests/users row counts. Copies are encrypted using Windows CurrentUser DPAPI and decrypted again for verification before a success receipt is sent. Repeat runs verify existing copies without overwriting them. Existing backups are retained; no automatic deletion or pruning is configured.

The database contains household records; the laptop folder is outside OneDrive. The Discord token stays on the server. No inbound connection or open port on the laptop is required.

## Locations

- Laptop installation: `C:\Users\katie\SprigBackups`.
- Encrypted copies: `C:\Users\katie\SprigBackups\backups\YYYY-MM-DD\sprig.db.dpapi`, with `manifest.json` beside each copy.
- Latest laptop result: `C:\Users\katie\SprigBackups\status.json`.
- Latest task execution log: `C:\Users\katie\SprigBackups\task-run.log`.
- Installed laptop tools: `C:\Users\katie\SprigBackups\tools`.
- Server copies: `/home/discordbot/sprig-backups/daily/YYYY-MM-DD/sprig.db`.
- Server monitor: `/home/discordbot/sprig-backup-tools/backup_monitor.py` and `backup_database.py`.
- Server health and laptop receipt: `/home/discordbot/sprig-backups/monitor/health.json` and `laptop.json`.
- Server backup/monitor log: `/home/discordbot/sprig-backups/daily/backup.log`.
- Pre-monitor schedule: `/home/discordbot/sprig-backup-tools-20261020-1935/crontab.before.txt`.

An early installation copy also exists under Codex's redirected AppData cache. It is not the scheduled destination. The active task uses the direct user-folder paths above. Existing copies were preserved.

## Discord alerts

ChoreSprite sends private backup alerts only to ginaria, Discord account `301104023405199361`, using its existing bot identity. Alerts cover server backup creation/integrity failures, a missing expected server snapshot, an explicitly reported laptop-transfer failure, and no current verified laptop copy within 48 hours. The missing-day check allows until 04:15 Eastern; laptop monitoring has a 48-hour initial grace period. Checks run hourly, so detection can take up to an additional hour.

The first failure state sends one alert; unchanged failures do not repeat. A changed problem set sends an update. A return to healthy sends one recovery notice. Commit-before-send deduplication avoids resending after an ambiguous network timeout. Failed/uncertain Discord delivery is recorded in health.json and is not automatically retried. Check the monitor log if DMs are blocked. These messages contain no chore records, database contents, or credentials.

These checks run on the server. They cannot report a total server outage while that server is unavailable. If the server is unavailable, the laptop writes a local failure result; no separate external uptime monitor is installed.

## Check or run a laptop backup

Open Task Scheduler and select **Sprig Laptop Backup**. **Run** starts a check; Last Run Result `0x0` means success. Read `status.json` to see the verified snapshot date. A successful task registration alone does not prove the backup ran.

PowerShell alternatives:

```powershell
Start-ScheduledTask -TaskName 'Sprig Laptop Backup'
Get-ScheduledTaskInfo -TaskName 'Sprig Laptop Backup'
Get-Content -LiteralPath 'C:\Users\katie\SprigBackups\status.json'
```

If SSH fails, confirm the laptop has internet and ssh-agent is running with the existing identity loaded. Add the existing key interactively if needed; never put the passphrase in a script. Keep strict host-key verification. After a Windows reinstall or runtime move, review the task's account, tool paths, and Python path before relying on it.

## Restore an encrypted laptop copy

DPAPI encryption belongs to Katherine's Windows account/profile. Preserve that profile and account recovery credentials. Copying only the encrypted file to a new account or reinstalling Windows does not guarantee decryption; no separate portable recovery key has been created. The server copies remain independently readable by the protected server account.

On this laptop, use a **new, unused output filename**. This decrypts and verifies a separate SQLite database; it never replaces the live server database:

```powershell
& 'C:\Users\katie\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\katie\SprigBackups\tools\laptop_backup.py' --restore 'C:\Users\katie\SprigBackups\backups\YYYY-MM-DD\sprig.db.dpapi' --output 'C:\Users\katie\SprigBackups\restored-sprig.db'
```

Replace `YYYY-MM-DD` with the chosen folder date. The plaintext output contains private household records. Keep it private and remove it deliberately after use. An existing output file is refused. Restoring the live server is a separate approved operation: stop Sprig, back up its current state, verify the chosen restore against compatible code, replace only the intended database, then start and verify. Do not overwrite `.env` or deploy a second bot instance.

## Pause and resume

Use Task Scheduler's **Disable** / **Enable**, or `Disable-ScheduledTask` / `Enable-ScheduledTask` with the task name. Disabling preserves all copies. An intentionally paused laptop still causes the server's 48-hour stale-copy alert. The server's ordinary snapshot schedule should remain enabled. Alert deduplication state should not be deleted simply to retry a message; inspect uncertain delivery first.

## Tests and installation evidence

`python -m unittest test_backup_transport -q` tests encrypted-copy publication, checksums and restore counts, corruption preservation, retry idempotence, real Windows encryption/restore (Windows only), simulated failure/recovery alerts, missed snapshots, stale laptop copies, and Linux server receipts/health (Linux only). All SSH and Discord calls in tests are mocked. `python -m unittest test_backup_transport test_backup_database -q` includes the seven Linux snapshot tests. Each platform skips the one test specific to the other platform.

On October 20, 2026, the Windows transport suite passed (13 executed, one Linux-only skip), and Linux passed 20 executed tests with one Windows-only skip including the seven existing snapshot tests. The first actual scheduled laptop invocation succeeded after fixing the installation path. Its snapshot was downloaded, encrypted, independently decrypted, integrity checked, and acknowledged by the server. Server and owner Discord identities and the private DM channel were verified without sending a fake failure message. Actual failure-DM delivery and the next unattended overnight run remain unverified until they occur.

The bot stayed active throughout this installation. These are standalone tools; no bot restart is required. The tested installation sources, documentation, and tests are versioned in SignalPocket/chore_bot. Installed standalone copies are managed separately from bot deployments.

Discord REST calls follow the official [Create DM](https://github.com/discord/discord-api-docs/blob/main/developers/resources/user.mdx#create-dm) and [Create Message](https://github.com/discord/discord-api-docs/blob/main/developers/resources/message.mdx#create-message) documentation.
