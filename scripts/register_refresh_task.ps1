# Register Windows Task Scheduler job for Climate Record weekly refresh.
#
# Principal/settings match MassiveStock Daily Pipeline (reliability):
#   LogonType Password, RunLevel Highest, WakeToRun, StartWhenAvailable
# Schedule stays weekly Sunday 2:00 AM (not daily).
#
# Usage (run in your own PowerShell - will ask for password in the console):
#   cd C:\Users\seand\GitProjects\ClimateRecordPlatform
#   .\scripts\register_refresh_task.ps1

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

Write-Host "Task: $TaskName"
Write-Host "Run:  $Bat"
Write-Host "When: $DayOfWeek at $Time (weekly, not daily like MassiveStock)"
Write-Host "User: $UserId | LogonType: Password | RunLevel: Highest | WakeToRun: Yes"
Write-Host "Log:  $(Join-Path $Root 'logs\refresh.log')"
Write-Host ""
Write-Host "Matches MassiveStock principal/settings; schedule stays weekly." -ForegroundColor DarkGray
Write-Host ""

# Console password (works when GUI Get-Credential dialog does not appear)
Write-Host "Enter Windows password for account '$UserId' (input hidden)." -ForegroundColor Cyan
$secure = Read-Host -AsSecureString "Password"
if (-not $secure -or $secure.Length -eq 0) {
    throw "Empty password - task not registered."
}
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
}
finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR) | Out-Null
}
if ([string]::IsNullOrEmpty($plain)) {
    throw "Empty password - task not registered."
}

try {
    # -User/-Password sets "run whether user is logged on" (Password logon type)
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -User $UserId `
        -Password $plain `
        -RunLevel Highest `
        -Description "Climate Record weekly refresh + phenom climate JSON (MassiveStock-style logon)" `
        -Force | Out-Null
}
finally {
    $plain = $null
    $secure = $null
}

Write-Host ""
Write-Host "Registered." -ForegroundColor Green
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
$p = (Get-ScheduledTask -TaskName $TaskName).Principal
Write-Host "LogonType: $($p.LogonType)  UserId: $($p.UserId)  RunLevel: $($p.RunLevel)"
$s = (Get-ScheduledTask -TaskName $TaskName).Settings
Write-Host "WakeToRun: $($s.WakeToRun)  StartWhenAvailable: $($s.StartWhenAvailable)"
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "NextRunTime: $($info.NextRunTime)"
Write-Host ""
Write-Host "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
