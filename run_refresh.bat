@echo off
setlocal EnableExtensions
REM Climate Record automated refresh (Task Scheduler entry point).
REM Default: FULL cohort refresh. For a safe smoke test use run_refresh_smoke.bat
REM
REM Task Scheduler example:
REM   Program:  C:\Users\seand\GitProjects\ClimateRecordPlatform\run_refresh.bat
REM   Start in: C:\Users\seand\GitProjects\ClimateRecordPlatform
REM   Trigger:  Weekly Sunday 02:00 (or monthly — full gold rebuild is long)

cd /d "%~dp0"
if not exist "logs" mkdir logs

echo ========================================
echo  Climate Record refresh (FULL)
echo  %DATE% %TIME%
echo  Root: %CD%
echo ========================================

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found. Create: python -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

".venv\Scripts\python.exe" run_refresh.py --full --copy-to-dunleavy
set ERR=%ERRORLEVEL%

if %ERR% neq 0 (
  echo.
  echo FAILED: refresh. See logs\refresh.log and data\meta\refresh_manifest.json
  exit /b %ERR%
)

echo.
echo ========================================
echo  Refresh completed successfully
echo  Live case study: https://www.dunleavyorganization.com/project-climate-record.html
echo ========================================
exit /b 0
