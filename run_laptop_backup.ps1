$ErrorActionPreference = 'Stop'
$base = Join-Path $env:USERPROFILE 'SprigBackups'
$log = Join-Path $base 'task-run.log'
try {
    ('Started ' + (Get-Date -Format o)) | Set-Content -LiteralPath $log -Encoding utf8
    & 'C:\Users\katie\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' (Join-Path $PSScriptRoot 'laptop_backup.py') 2>&1 | Out-File -LiteralPath $log -Append -Encoding utf8
    exit $LASTEXITCODE
} catch {
    ('Task failed: ' + $_.Exception.Message) | Out-File -LiteralPath $log -Append -Encoding utf8
    exit 1
}
