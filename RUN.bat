@echo off
setlocal
title Nusantara Expense & Procurement System
cd /d "%~dp0"

:: Set Node 24 path if not already in system PATH
where node >nul 2>&1
if %errorlevel% neq 0 (
    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64;%PATH%"
)

echo ======================================================================
echo    Nusantara Enterprise Solutions Sdn. Bhd.
echo    Malaysian Expense Management & Procurement ERP System (MYR / RM)
echo ======================================================================
echo.
echo Starting backend server on http://localhost:5000 ...
start "Nusantara ERP - Backend (Port 5000)" cmd /k "node server/index.js"

timeout /t 2 /nobreak >nul

echo Starting frontend dev server on http://localhost:3000 ...
cd client
start "Nusantara ERP - Frontend (Port 3000)" cmd /k "npm start"
cd ..

echo.
echo Systems launched successfully!
echo   App URL:        http://localhost:3000 (or http://localhost:5000)
echo   Default Admin:   admin@company.com / admin123
echo   Finance Manager: manager@company.com / manager123
echo   Staff Member:    employee@company.com / employee123
echo.
pause
