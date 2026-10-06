@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% equ 0 (
    python scrobbler.py
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/
        echo Enable "Add Python to PATH" during installation, then run this launcher again.
    ) else (
        py -3 scrobbler.py
    )
)
if errorlevel 1 (
    echo.
    echo Aki's Rockbox Scrobbler could not start. See the message above for details.
    pause
)
endlocal
