@echo off
REM FileMatcher - Build Windows Setup.exe
REM This script builds a professional Windows installer

setlocal enabledelayedexpansion

cd /d "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

echo.
echo ============================================
echo     FileMatcher Setup.exe Builder
echo ============================================
echo.

REM Check if Node is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Download from: https://nodejs.org/
    pause
    exit /b 1
)

REM Check if npm is installed
npm --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm is not installed
    pause
    exit /b 1
)

echo.
echo Step 1/4: Installing dependencies...
echo.
call npm install
if errorlevel 1 (
    echo ERROR: npm install failed
    pause
    exit /b 1
)

echo.
echo Step 2/4: Building frontend assets...
echo.
call npm run build
if errorlevel 1 (
    echo ERROR: npm build failed
    pause
    exit /b 1
)

echo.
echo Step 3/4: Building Windows installer...
echo This may take 2-5 minutes...
echo.
call npm run electron:build
if errorlevel 1 (
    echo ERROR: electron:build failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo          BUILD COMPLETED!
echo ============================================
echo.

REM Find the installer file
for /f "delims=" %%i in ('dir /b release\FileMatcher-*-win-x64.exe 2^>nul') do (
    set INSTALLER=%%i
    goto :found
)

:found
if defined INSTALLER (
    echo Installer created: release\%INSTALLER%
    echo.
    echo File size:
    for %%A in ("release\%INSTALLER%") do echo %%~zA bytes
    echo.
    echo To test the installer:
    echo   1. Navigate to: release folder
    echo   2. Double-click: %INSTALLER%
    echo   3. Follow installation steps
    echo.
    echo To publish to GitHub:
    echo   1. Go to: https://github.com/sumitessgee01/excelmatcher-pro/releases
    echo   2. Create new release
    echo   3. Upload: release\%INSTALLER%
    echo   4. Publish
) else (
    echo Warning: Could not find installer file
    echo Check release folder manually
)

echo.
pause
