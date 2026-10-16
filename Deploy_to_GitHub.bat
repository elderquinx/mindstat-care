@echo off
title MindStat Care - 1-Click GitHub & Cloud Publisher
cd /d "%~dp0"

echo ============================================================================
echo   MindStat Care - Publish to GitHub + Free Streamlit Community Cloud
echo ============================================================================
echo.
echo Step 1: A browser tab will open to create a new empty GitHub repository.
echo         (Name it e.g. "mindstat-care", keep it Public, do NOT add README)
echo.
set /p OPEN_GH="Open GitHub 'New Repository' page in browser now? (Y/N): "
if /i "%OPEN_GH%"=="Y" (
    start "" "https://github.com/new"
)
echo.
set /p REPO_URL="Step 2: Paste your GitHub Repository URL (e.g. https://github.com/yourname/mindstat-care.git): "

if "%REPO_URL%"=="" (
    echo [ERROR] No URL entered. Exiting.
    pause
    exit /b 1
)

echo.
echo [INFO] Staging and committing latest MindStat Care files...
git add -A
git commit -m "Update MindStat Care standalone cloud prototype" 2>nul
git branch -M main
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [INFO] Pushing to GitHub (a GitHub sign-in window may pop up)...
git push -u origin main

if %errorlevel%==0 (
    echo.
    echo ============================================================================
    echo   [SUCCESS] Published to GitHub!
    echo   Now opening Streamlit Community Cloud (https://share.streamlit.io)
    echo   1. Click "Create app" -> Select your repository -> Main file: app.py
    echo   2. Click "Deploy!" -> Your permanent cloud server will be live in 60s!
    echo ============================================================================
    start "" "https://share.streamlit.io"
) else (
    echo.
    echo [ERROR] Push failed. Please check the repository URL and your GitHub login.
)
pause
