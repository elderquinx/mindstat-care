@echo off
title MindStat Care - 1-Click GitHub & Cloud Publisher
cd /d "%~dp0"

echo ============================================================================
echo   MindStat Care - Publishing to https://github.com/elderquinx/mindstat-care
echo ============================================================================
echo.

git add -A
git commit -m "Update MindStat Care standalone cloud prototype" 2>nul
git branch -M main
git push -u origin main

if %errorlevel%==0 (
    echo.
    echo ============================================================================
    echo   [SUCCESS] Published to https://github.com/elderquinx/mindstat-care !
    echo   Opening Streamlit Community Cloud (https://share.streamlit.io)
    echo ============================================================================
    start "" "https://share.streamlit.io"
) else (
    echo.
    echo [ERROR] Push did not complete.
)
pause
