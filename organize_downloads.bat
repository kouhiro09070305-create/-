@echo off
rem Double-click to organize the Downloads folder.
rem Uses the "py" launcher if available, otherwise "python".
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 organize_downloads.py %*
) else (
    python organize_downloads.py %*
)
pause
