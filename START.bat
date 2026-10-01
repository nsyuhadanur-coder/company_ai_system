@echo off
echo ============================================
echo    ExpensePro - Expense Management System
echo ============================================
echo.

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed!
    echo Please download and install from: https://nodejs.org/
    echo Choose the LTS version.
    pause
    exit /b 1
)

echo [1/4] Node.js found: 
node --version

echo.
echo [2/4] Installing backend dependencies...
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Backend install failed
    pause
    exit /b 1
)

echo.
echo [3/4] Installing frontend dependencies...
cd client
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Frontend install failed
    pause
    exit /b 1
)

:: Add Tailwind to frontend
call npm install -D tailwindcss postcss autoprefixer
cd ..

echo.
echo [4/4] Setup complete!
echo.
echo ============================================
echo    Starting ExpensePro...
echo ============================================
echo.
echo Backend:  http://localhost:5000
echo Frontend: http://localhost:3000
echo.
echo Default accounts:
echo   Admin:    admin@company.com / admin123
echo   Manager:  manager@company.com / manager123
echo   Employee: employee@company.com / employee123
echo.
echo Press Ctrl+C to stop
echo.

:: Start both servers
start "ExpensePro Backend" cmd /k "node server/index.js"
timeout /t 3 /nobreak
cd client
start "ExpensePro Frontend" cmd /k "npm start"
cd ..
