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
git remote remove origin 2>nul
git remote add origin https://github.com/elderquinx/mindstat-care.git

echo [INFO] Pushing to GitHub...
echo        (If a GitHub sign-in box appears, click "Sign in with your browser")
echo.
git push -u origin main

if %errorlevel%==0 (
    echo.
    echo ============================================================================
    echo   [SUCCESS] Published to https://github.com/elderquinx/mindstat-care !
    echo   Now opening Streamlit Community Cloud (https://share.streamlit.io)
    echo   1. Click "Create app" -> Select "elderquinx/mindstat-care" -> Main file: app.py
    echo   2. Click "Deploy!" -> Your permanent cloud server will be live in 60s!
    echo ============================================================================
    start "" "https://share.streamlit.io"
) else (
    echo.
    echo [ERROR] Push did not complete. Please sign into GitHub when prompted and run again.
)
pause
