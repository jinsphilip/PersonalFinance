@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Create a Desktop shortcut named "FinTracker" that launches the app.
REM  If a built dist\FinTracker.exe exists it points there; otherwise it points
REM  at run.bat (which sets up the venv and runs from source).
REM ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

if exist "dist\FinTracker.exe" (
    set "TARGET=%~dp0dist\FinTracker.exe"
) else (
    set "TARGET=%~dp0run.bat"
)

set "SC=%TEMP%\_mkshortcut.vbs"
> "%SC%" echo Set ws = CreateObject("WScript.Shell")
>> "%SC%" echo desktop = ws.SpecialFolders("Desktop")
>> "%SC%" echo Set lnk = ws.CreateShortcut(desktop ^& "\FinTracker.lnk")
>> "%SC%" echo lnk.TargetPath = "%TARGET%"
>> "%SC%" echo lnk.WorkingDirectory = "%~dp0"
>> "%SC%" echo lnk.Description = "Personal Finance Tracker"
>> "%SC%" echo lnk.Save
cscript //nologo "%SC%"
del "%SC%"

echo [done] Created "FinTracker" shortcut on your Desktop.
echo [done] Target: %TARGET%
pause
