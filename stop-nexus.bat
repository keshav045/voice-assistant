@echo off
chcp 65001 >nul
title Nexus Assistant - Teardown

echo =====================================================================
echo           Stopping Nexus Agentic AI Assistant Services...
echo =====================================================================
echo.

:: 1. Terminate process on Port 8000 (FastAPI Backend)
echo [1/3] Terminating Backend on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo   - Killing PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: 2. Terminate process on Port 5173 (Vite Frontend)
echo [2/3] Terminating Frontend on port 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo   - Killing PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

:: 3. Terminate Desktop Companion process
echo [3/3] Terminating Windows Desktop Companion...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*desktop-companion*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo =====================================================================
echo  [OK] All Nexus assistant processes have been safely stopped!
echo =====================================================================
echo.
timeout /t 2 /nobreak >nul
