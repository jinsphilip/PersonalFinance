@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Build a standalone FinTracker.exe for Windows (no Python needed to run it).
REM  Output: dist\FinTracker.exe  — double-click it to launch the app.
REM ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 ( set "PY=py -3" ) else ( set "PY=python" )

REM Build inside a dedicated venv so PyInstaller picks up only what we need
if not exist "venv\Scripts\python.exe" (
    echo [build] Creating virtual environment...
    %PY% -m venv venv
)
set "VPY=venv\Scripts\python.exe"

echo [build] Installing dependencies + PyInstaller...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [error] Install failed.
    pause
    exit /b 1
)

echo [build] Packaging FinTracker.exe ...
REM --add-data "SRC;DEST"  bundles templates and static into the exe.
REM --hidden-import flask_sqlalchemy ensures the ORM is collected.
"%VPY%" -m PyInstaller --noconfirm --onefile --name FinTracker ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import flask_sqlalchemy ^
    --collect-submodules sqlalchemy ^
    app.py
if errorlevel 1 (
    echo [error] Build failed.
    pause
    exit /b 1
)

echo.
echo [done] Built: dist\FinTracker.exe
echo [done] Double-click it (or run it) to start the app; it opens your browser
echo        at http://localhost:5000 and stores data in finance.db beside the exe.
echo.
pause
