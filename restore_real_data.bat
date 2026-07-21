@echo off
REM Restore your real data from the most recent finance-REAL backup. Stop the app first.
cd /d "%~dp0"
set "VPY=venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
"%VPY%" demo_data.py restore
echo.
echo Start the app (run.bat) to use your real data again.
pause
