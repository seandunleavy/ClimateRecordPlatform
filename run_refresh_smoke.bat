@echo off
setlocal EnableExtensions
REM Safe daytime smoke: re-pull 3 stations, silver+QC only. Never rebuilds gold.

cd /d "%~dp0"
if not exist "logs" mkdir logs

echo ========================================
echo  Climate Record refresh (SMOKE)
echo  %DATE% %TIME%
echo ========================================

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found.
  exit /b 1
)

".venv\Scripts\python.exe" run_refresh.py --smoke --limit 3 --reprocess-all
set ERR=%ERRORLEVEL%
if %ERR% neq 0 (
  echo FAILED smoke. See logs\refresh.log
  exit /b %ERR%
)
echo SMOKE OK
exit /b 0
