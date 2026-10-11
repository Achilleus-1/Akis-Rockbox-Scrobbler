@echo off
setlocal
cd /d "%~dp0"
if exist "dist\Akis-Rockbox-Scrobbler\Akis-Rockbox-Scrobbler.exe" (
    start "" "dist\Akis-Rockbox-Scrobbler\Akis-Rockbox-Scrobbler.exe"
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0app.py"
    exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0app.py"
    exit /b
)
echo Source requires Python 3.10+ with Tk support.
echo For the standalone app, download Setup or the portable ZIP from:
echo https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/releases/latest
pause
