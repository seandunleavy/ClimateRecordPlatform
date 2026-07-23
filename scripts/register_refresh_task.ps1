<#
.SYNOPSIS
  Register a Windows Task Scheduler job for Climate Record weekly refresh.

.DESCRIPTION
  Creates (or updates) task "ClimateRecord-WeeklyRefresh" that runs run_refresh.bat.
  Full nationwide gold rebuild is long — default Sunday 2:00 AM.

.EXAMPLE
  # Preview only
  .\scripts\register_refresh_task.ps1 -WhatIf

.EXAMPLE
  # Create/update the task (may need elevation depending on policy)
  .\scripts\register_refresh_task.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "ClimateRecord-WeeklyRefresh",
    [string]$Time = "02:00",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$DayOfWeek = "Sunday"
)

$Root = Split-Path -Parent $PSScriptRoot
$Bat = Join-Path $Root "run_refresh.bat"
if (-not (Test-Path $Bat)) {
    throw "Missing $Bat"
}

$Action = New-ScheduledTaskAction -Execute $Bat -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Write-Host "Task: $TaskName"
Write-Host "Run:  $Bat"
Write-Host "When: $DayOfWeek at $Time"
Write-Host "Log:  $(Join-Path $Root 'logs\refresh.log')"

if ($PSCmdlet.ShouldProcess($TaskName, "Register scheduled task")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "Climate Record Platform NOAA GHCNd weekly refresh (full pipeline)" `
        -Force | Out-Null
    Write-Host "Registered. View in Task Scheduler or: Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
}
else {
    Write-Host "WhatIf: no task written."
}
