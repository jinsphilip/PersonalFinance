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

REM Load the Claude API key (needed for the Portfolio Analysis page) from a local,
REM untracked file so the secret never gets committed. Copy set_api_key.bat.example
REM to set_api_key.bat and put your real key in it.
if exist "set_api_key.bat" (
    call "set_api_key.bat"
    echo [setup] Loaded ANTHROPIC_API_KEY from set_api_key.bat
) else (
    echo [note] set_api_key.bat not found - AI Portfolio Analysis will be disabled.
    echo [note] Copy set_api_key.bat.example to set_api_key.bat and add your key.
)

echo [setup] Installing dependencies...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [error] Dependency installation failed.
    pause
    exit /b 1
)

REM Seed sample data ONLY on a genuinely fresh install (no DB in either
REM location). init_db.py also self-guards and refuses to wipe existing data.
set "HASDB="
if exist "instance\finance.db" set "HASDB=1"
if exist "finance.db" set "HASDB=1"
if not defined HASDB (
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
