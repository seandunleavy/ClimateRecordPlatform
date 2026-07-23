# Register ClimateRecord-WeeklyRefresh with MassiveStock-style logon settings.
# Schedule: weekly Sunday 2:00 AM
#
# If a previous run is stuck: close that PowerShell window (X), or Task Manager
# end "Windows PowerShell" / pwsh. Ctrl+C often does not work on password prompts.
#
# Usage:
#   cd C:\Users\seand\GitProjects\ClimateRecordPlatform
#   .\scripts\register_refresh_task.ps1
#   (type password, Enter)

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

Write-Host ""
Write-Host "If this window ever hangs on Password: close the window with X (Ctrl+C may not work)." -ForegroundColor Yellow
Write-Host ""
Write-Host "Task: $TaskName"
Write-Host "Run:  $Bat"
Write-Host "When: $DayOfWeek at $Time weekly"
Write-Host "User: $UserId  (Password logon + Highest + WakeToRun)"
Write-Host ""

# Plain console prompt - one line, then Enter
Write-Host "Type password for $UserId then press Enter (characters hidden):" -ForegroundColor Cyan
$secure = Read-Host -AsSecureString
if ($null -eq $secure -or $secure.Length -lt 1) {
    throw "No password entered. Closed without registering."
}

$BSTR = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($BSTR)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR) | Out-Null
}

$Action = New-ScheduledTaskAction -Execute $Bat -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

try {
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
Write-Host "OK - registered." -ForegroundColor Green
$p = (Get-ScheduledTask -TaskName $TaskName).Principal
$s = (Get-ScheduledTask -TaskName $TaskName).Settings
Write-Host ("LogonType={0}  RunLevel={1}  WakeToRun={2}" -f $p.LogonType, $p.RunLevel, $s.WakeToRun)
Write-Host ("NextRunTime={0}" -f (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)
