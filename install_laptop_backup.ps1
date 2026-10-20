param([switch]$UpdateExisting)
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:USERPROFILE 'SprigBackups'
$tools = Join-Path $base 'tools'
$taskName = 'Sprig Laptop Backup'
$previousTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($previousTask -and -not $UpdateExisting) {
    throw 'Task already exists. Inspect its current configuration before changing it.'
}
if (Test-Path -LiteralPath $base) {
    $existing = @(Get-ChildItem -LiteralPath $base -Force)
    if ($existing.Count -ne 1 -or $existing[0].FullName -ne $tools -or @(Get-ChildItem -LiteralPath $tools -Force).Count -ne 0) {
        throw 'Sprig laptop directory contains files. Inspect before retrying installation.'
    }
}
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $identity.User.Value
& icacls.exe $base /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE) { throw 'Could not protect the laptop backup directory.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'laptop_backup.py') -Destination (Join-Path $tools 'laptop_backup.py')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'run_laptop_backup.ps1') -Destination (Join-Path $tools 'run_laptop_backup.ps1')
$python = 'C:\Users\katie\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The configured Python runtime is unavailable.' }
$action = New-ScheduledTaskAction -Execute 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $tools 'run_laptop_backup.ps1') + '"')
$daily = New-ScheduledTaskTrigger -Daily -At '04:00'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$catchup = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger @($daily,$logon,$catchup) -Settings $settings -Principal $principal -Description 'Download and verify Sprig daily snapshots over SSH, encrypt for this Windows account, and report verified receipts to the backup monitor. Catches up at sign-in and hourly while signed in.'
if ($previousTask) {
    if (-not $previousTask.Description.StartsWith('Download and verify Sprig daily snapshots over SSH')) { throw 'Unexpected existing task; inspect before replacing.' }
    Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $base 'task.before.xml') -Encoding utf8
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Select-Object TaskName,State
} else {
    Register-ScheduledTask -TaskName $taskName -InputObject $task | Select-Object TaskName,State
}
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $base 'task.xml') -Encoding utf8
Write-Output ('Laptop backup folder: ' + (Join-Path $base 'backups'))
