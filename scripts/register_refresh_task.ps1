# Register Windows Task Scheduler job for Climate Record weekly refresh.
#
# Principal/settings match MassiveStock Daily Pipeline (reliability):
#   LogonType Password, RunLevel Highest, WakeToRun, StartWhenAvailable
# Schedule stays weekly Sunday 2:00 AM (not daily).
#
# Usage:
#   .\scripts\register_refresh_task.ps1
#   .\scripts\register_refresh_task.ps1 -WhatIf

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "ClimateRecord-WeeklyRefresh",
    [string]$Time = "02:00",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$DayOfWeek = "Sunday",
    [string]$UserId = $env:USERNAME
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Bat = Join-Path $Root "run_refresh.bat"
if (-not (Test-Path $Bat)) {
    throw "Missing $Bat"
}

$Action = New-ScheduledTaskAction -Execute $Bat -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Password `
    -RunLevel Highest

Write-Host "Task: $TaskName"
Write-Host "Run:  $Bat"
Write-Host "When: $DayOfWeek at $Time (weekly, not daily like MassiveStock)"
Write-Host "User: $UserId | LogonType: Password | RunLevel: Highest | WakeToRun: Yes"
Write-Host "Log:  $(Join-Path $Root 'logs\refresh.log')"
Write-Host ""
Write-Host "Matches MassiveStock principal/settings; schedule stays weekly." -ForegroundColor DarkGray
Write-Host ""

if (-not $PSCmdlet.ShouldProcess($TaskName, "Register scheduled task")) {
    Write-Host "WhatIf: no task written."
    return
}

$msg = "Windows password for $UserId - same account as MassiveStock task"
$cred = Get-Credential -UserName $UserId -Message $msg
if (-not $cred) {
    throw "Credential cancelled."
}
$plain = $cred.GetNetworkCredential().Password
if ([string]::IsNullOrEmpty($plain)) {
    throw "Empty password - task not registered."
}

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -User $UserId `
        -Password $plain `
        -Description "Climate Record weekly refresh + phenom climate JSON (MassiveStock-style logon)" `
        -Force | Out-Null
}
finally {
    $plain = $null
}

Write-Host ""
Write-Host "Registered." -ForegroundColor Green
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
$p = (Get-ScheduledTask -TaskName $TaskName).Principal
Write-Host "LogonType: $($p.LogonType)  UserId: $($p.UserId)  RunLevel: $($p.RunLevel)"
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "NextRunTime: $($info.NextRunTime)"
Write-Host ""
Write-Host "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
