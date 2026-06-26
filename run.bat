@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  FinTracker - one-click launcher for Windows
REM  Creates a virtual environment, installs dependencies, seeds the database
REM  on first run, then starts the app at http://localhost:5000
REM ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

REM Pick a Python launcher: prefer the py launcher, fall back to python
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

REM Create the virtual environment if it does not exist yet
if not exist "venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    %PY% -m venv venv
    if errorlevel 1 (
        echo [error] Could not create the virtual environment. Is Python installed?
        pause
        exit /b 1
    )
)

REM Use the venv's Python from here on
set "VPY=venv\Scripts\python.exe"

echo [setup] Installing dependencies...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [error] Dependency installation failed.
    pause
    exit /b 1
)

REM Seed the database with sample data only on the very first run
if not exist "finance.db" (
    echo [setup] Initialising database with sample data...
    "%VPY%" init_db.py
)

echo.
echo [run] Starting FinTracker at http://localhost:5000
echo [run] Press Ctrl+C to stop.
echo.
start "" "http://localhost:5000"
"%VPY%" app.py

pause
