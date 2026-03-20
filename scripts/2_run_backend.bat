@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Backend - AI Gaming Companion
cd /d "%~dp0.."

echo.
echo  ============================================
echo  Backend Mode - http://localhost:8080
echo  ============================================
echo.

if not defined ANTHROPIC_API_KEY if not defined GEMINI_API_KEY if not defined OPENAI_API_KEY (
    echo  No API key found.
    echo.
    echo  Get a free Gemini key:
    echo  https://aistudio.google.com/apikey
    echo.
    set /p "GEMINI_API_KEY=Paste Gemini API key: "
    if "!GEMINI_API_KEY!"=="" (
        echo  No key entered. Exiting.
        pause
        exit /b 1
    )
)

if defined GEMINI_API_KEY echo  [OK] Gemini key set
if defined ANTHROPIC_API_KEY echo  [OK] Anthropic key set
if defined OPENAI_API_KEY echo  [OK] OpenAI key set

set GAME=palworld
set CHAR=nozomi
set TIER=free
set LOCALE=ko

if not "%~1"=="" set GAME=%~1
if not "%~2"=="" set CHAR=%~2
if not "%~3"=="" set TIER=%~3
if not "%~4"=="" set LOCALE=%~4

echo.
echo  Game: %GAME%  Character: %CHAR%  Tier: %TIER%  Locale: %LOCALE%
echo  Press Ctrl+C to stop
echo.

python -X utf8 -m backend.tools.web_overlay --game %GAME% --character %CHAR% --tier %TIER% --locale %LOCALE% --port 8080 --interval 3

if errorlevel 1 (
    echo.
    echo  [ERROR] Backend exited with error. Check output above.
    pause
)
