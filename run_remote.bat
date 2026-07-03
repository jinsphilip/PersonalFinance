@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  FinTracker - remote launcher (phone / any network)
REM  Starts the app locally AND opens a public Cloudflare Tunnel so you can reach
REM  it from your phone anywhere. Requires a login password to be set first.
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
set "VPY=venv\Scripts\python.exe"

REM Load local secrets (Claude API key + FINTRACKER_PASSWORD)
if exist "set_api_key.bat" (
    call "set_api_key.bat"
) else (
    echo [note] set_api_key.bat not found. Copy set_api_key.bat.example to
    echo        set_api_key.bat and set FINTRACKER_PASSWORD before exposing the app.
)

REM SAFETY: never tunnel a passwordless app to the internet.
if "%FINTRACKER_PASSWORD%"=="" (
    echo.
    echo [ABORT] FINTRACKER_PASSWORD is not set.
    echo         Exposing the app without a login would make all your finance data
    echo         public. Set FINTRACKER_PASSWORD in set_api_key.bat, then re-run.
    echo.
    pause
    exit /b 1
)
if "%FINTRACKER_PASSWORD%"=="choose-a-strong-password" (
    echo.
    echo [ABORT] FINTRACKER_PASSWORD is still the example default.
    echo         Change it to a real strong password in set_api_key.bat, then re-run.
    echo.
    pause
    exit /b 1
)

REM Check cloudflared is installed
where cloudflared >nul 2>nul
if not %errorlevel%==0 (
    echo.
    echo [ABORT] cloudflared is not installed.
    echo         Install it, then re-run:  winget install --id Cloudflare.cloudflared
    echo.
    pause
    exit /b 1
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

REM Start the Flask app in its own window (stays running).
echo [run] Starting FinTracker (login required) in a new window...
start "FinTracker" "%VPY%" app.py

REM Give the server a moment to come up, then open the public tunnel here.
timeout /t 3 >nul
echo.
echo [tunnel] Opening a public Cloudflare Tunnel to http://localhost:5000
echo [tunnel] Look for the  https://<something>.trycloudflare.com  URL below,
echo [tunnel] open it on your phone, and sign in with your password.
echo [tunnel] Press Ctrl+C to stop the tunnel (then close the FinTracker window).
echo.
cloudflared tunnel --url http://localhost:5000

pause
