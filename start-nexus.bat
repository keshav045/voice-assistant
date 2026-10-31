@echo off
chcp 65001 >nul
title Nexus Agentic AI Assistant - Launcher

echo =====================================================================
echo        _   _  ______  __  __  _   _  _____ 
echo       ^| \ ^| ^|^|  ____^|^|\ \/ / ^| ^| ^| ^|/ ____^|
echo       ^|  \^| ^|^| ^|__    \  /  ^| ^| ^| ^| (___  
echo       ^| . ` ^|^|  __^|    /  \  ^| ^| ^| ^|\___ \ 
echo       ^| ^|\  ^|^| ^|____  / /\ \ ^| ^|_^| ^|____) ^|
echo       ^|_^| \_^|^|______^|/_/  \_^\\_____/^|_____/ 
echo.
echo           Autonomous Agentic AI Productivity Assistant
echo                     Windows 11 Native Engine
echo =====================================================================
echo.

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

:: 1. Verify Virtual Environment
if not exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
    echo [ERROR] Backend virtual environment not found in backend\.venv
    echo Run: python -m venv backend\.venv ^&^& backend\.venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

:: 2. Verify Node modules
if not exist "%ROOT_DIR%frontend\node_modules" (
    echo [INFO] Installing frontend npm dependencies...
    cd /d "%ROOT_DIR%frontend"
    call npm install
    cd /d "%ROOT_DIR%"
)

echo [1/3] Starting Nexus FastAPI Backend (Port 8000)...
start "Nexus Backend" cmd /k "cd /d "%ROOT_DIR%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/3] Starting Nexus Vite Web Dashboard (Port 5173)...
start "Nexus Frontend" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev"

echo [3/3] Starting Nexus Windows Desktop Companion Daemon...
start "Nexus Desktop Companion" cmd /k "cd /d "%ROOT_DIR%" && backend\.venv\Scripts\python.exe desktop-companion\main.py"

echo.
echo Waiting 4 seconds for services to bind sockets...
timeout /t 4 /nobreak >nul

echo Launching Executive Dashboard in default web browser...
start http://localhost:5173

echo.
echo =====================================================================
echo  [OK] Nexus is running!
echo  - Web Dashboard:     http://localhost:5173
echo  - API Swagger Docs:  http://localhost:8000/docs
echo  - Companion Daemon:  Active (WebSocket on ws://localhost:8000)
echo.
echo  To safely shut down all services at any time, run: stop-nexus.bat
echo =====================================================================
echo.
pause

