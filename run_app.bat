@echo off
title Astra HR & Operations AI Assistant Server
echo ===================================================================
echo    Astra HR & Internal Operations AI Assistant
echo ===================================================================
echo.
cd /d "%~dp0"

echo Opening http://127.0.0.1:8000 in your default browser...
start http://127.0.0.1:8000

echo.
echo Starting Python backend server on http://127.0.0.1:8000 ...
echo (Keep this window open while using the chatbot)
echo.
python app.py
pause
