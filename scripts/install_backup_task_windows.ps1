[CmdletBinding()]
param(
    [ValidatePattern("^\d{2}:\d{2}$")]
    [string]$Time = "21:00",

    [string]$BackupDir = "",

    [ValidateRange(1, 365)]
    [int]$Keep = 30,

    [string]$TaskName = "Task Tracker Daily Backup"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackupScript = Join-Path $PSScriptRoot "backup_windows.ps1"

if (-not (Test-Path $BackupScript)) {
    throw "Не найден $BackupScript"
}

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $ProjectParent = Split-Path $ProjectDir -Parent
    $BackupDir = Join-Path $ProjectParent "backups\task-tracker"
}

$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$parsed = [DateTime]::ParseExact(
    $Time,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$runAt = [DateTime]::Today.Add($parsed.TimeOfDay)

$powershellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $powershellExe)) {
    $powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
}

$arguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "{0}" -BackupDir "{1}" -Keep {2}' -f
    $BackupScript,
    $BackupDir,
    $Keep
)

$action = New-ScheduledTaskAction `
    -Execute $powershellExe `
    -Argument $arguments `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -Daily -At $runAt

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Docker Desktop normally runs in the interactive user's session, therefore the
# task intentionally uses Interactive logon instead of trying to run at boot.
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily portable backup of Task Tracker PostgreSQL and media outside Docker volumes." `
    -Force | Out-Null

Write-Host ""
Write-Host "Ежедневный backup зарегистрирован." -ForegroundColor Green
Write-Host "Задача:       $TaskName"
Write-Host "Время:        $Time"
Write-Host "Каталог:      $BackupDir"
Write-Host "Хранить:      $Keep копий"
Write-Host ""
Write-Host "Важно: в это время Windows-пользователь должен быть вошедшим в систему,"
Write-Host "а Docker Desktop должен быть запущен."
Write-Host ""
Write-Host "Проверить задачу:"
Write-Host "  Get-ScheduledTask -TaskName `"$TaskName`""
Write-Host ""
Write-Host "Запустить прямо сейчас:"
Write-Host "  Start-ScheduledTask -TaskName `"$TaskName`""
