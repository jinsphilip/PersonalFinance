@echo off
REM Back up your real data, then load dummy/sample data. Stop the app first.
cd /d "%~dp0"
set "VPY=venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
"%VPY%" demo_data.py dummy
echo.
echo Start the app (run.bat) to use the dummy data.
echo To get your real data back later, run restore_real_data.bat
pause
