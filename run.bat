@echo off
setlocal EnableDelayedExpansion
title Lead Gen Pipeline

cd /d "%~dp0"

echo.
echo ================================================
echo   IT Staffing Lead Gen Pipeline
echo   %DATE% %TIME%
echo ================================================
echo.

REM ── Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
  pause & exit /b 1
)

REM ── Check dependencies ────────────────────────────────────────────────────
python -c "import requests, bs4" >nul 2>&1
if %errorlevel% neq 0 (
  echo [INFO] Installing dependencies...
  pip install requests beautifulsoup4 --quiet
  if !errorlevel! neq 0 (
    echo [ERROR] pip install failed. Run manually: pip install requests beautifulsoup4
    pause & exit /b 1
  )
  echo [INFO] Dependencies installed.
  echo.
)

REM ── Phase 1: Scraper ──────────────────────────────────────────────────────
echo [1/3] Running scraper.py ...
echo       Scraping Greenhouse, Remotive, BuiltinNYC, Dice, Indeed
echo.
python scraper.py
if %errorlevel% neq 0 (
  echo [WARNING] Scraper exited with errors. Continuing to filters...
) else (
  echo [OK] Scraper complete.
)
echo.

REM ── Phase 2: Filters ──────────────────────────────────────────────────────
echo [2/3] Running filters.py ...
echo.
python filters.py
if %errorlevel% neq 0 (
  echo [WARNING] Filters exited with errors. Continuing to scorer...
) else (
  echo [OK] Filters complete.
)
echo.

REM ── Phase 3: Scorer + Dashboard ───────────────────────────────────────────
echo [3/3] Running scorer.py ...
echo       Scoring leads and generating dashboard.html
echo.
python scorer.py
if %errorlevel% neq 0 (
  echo [WARNING] Scorer exited with errors.
) else (
  echo [OK] Scorer complete.
)
echo.

REM ── Done ──────────────────────────────────────────────────────────────────
echo ================================================
echo   Pipeline complete!
echo   Open dashboard.html in your browser.
echo ================================================
echo.

REM Auto-open dashboard in default browser
if exist dashboard.html (
  start "" dashboard.html
)

pause
