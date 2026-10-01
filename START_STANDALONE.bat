@echo off
setlocal
title Nusantara Expense & Procurement System (Standalone)
cd /d "%~dp0"

where node >nul 2>&1
if %errorlevel% neq 0 (
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64;%PATH%"
)

echo ======================================================================
echo    Nusantara Enterprise Solutions Sdn. Bhd.
echo    Malaysian Expense Management & Procurement ERP System (MYR / RM)
echo ======================================================================
echo.
echo Launching server at http://localhost:5000 ...
echo.
echo Default Logins:
echo   Admin:    admin@company.com   / admin123
echo   Manager:  manager@company.com / manager123
echo   Staff:    employee@company.com / employee123
echo.
echo Press Ctrl+C in this window to stop the server.
echo.

node server/index.js
pause
