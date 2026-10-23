[CmdletBinding()]
param(
    [string]$TaskName = "Task Tracker Daily Backup"
)

$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Задача '$TaskName' не найдена."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Задача '$TaskName' удалена." -ForegroundColor Green
