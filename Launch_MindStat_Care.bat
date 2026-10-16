@echo off
title MindStat Care - Standalone Platform Server
cd /d "%~dp0"

echo ============================================================================
echo   MindStat Care - Proactive Mental Wellbeing & Support Platform
echo   Starting Standalone Local Server + Public 4G/5G QR Tunnel...
echo ============================================================================
echo.

:: Check if port 8501 is already listening
netstat -ano | findstr ":8501 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [INFO] MindStat Care server is already running on http://localhost:8501
) else (
    echo [INFO] Launching MindStat Care Engine...
    start "MindStat Care Server" /min "%~dp0.venv\Scripts\streamlit.exe" run "%~dp0app.py" --server.port 8501 --server.runOnSave true --server.headless true
    timeout /t 4 /nobreak >nul
)

echo [INFO] Opening MindStat Care Standalone App Window...
where msedge >nul 2>nul
if %errorlevel%==0 (
    start "" msedge --app=http://localhost:8501
) else (
    start "" http://localhost:8501
)

echo.
echo [SUCCESS] MindStat Care is running!
echo - Desktop Admin & QR Hub : http://localhost:8501
echo - Mobile Student View    : http://localhost:8501/?view=mobile
echo.
