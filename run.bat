@echo off
cd /d "%~dp0"

echo Which server do you want to start?
echo   1) Travel Cost Chatbot (Python - port 8000)
echo   2) Sheets/PDF Analyzer  (Node.js - port 3000)
echo.
set /p CHOICE="Enter 1 or 2: "

if "%CHOICE%"=="1" (
    echo.
    echo Starting Travel Cost Chatbot at http://localhost:8000
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) else if "%CHOICE%"=="2" (
    echo.
    echo Starting Sheets/PDF Analyzer at http://localhost:3000
    node src/server.js
) else (
    echo Invalid choice.
)
pause
