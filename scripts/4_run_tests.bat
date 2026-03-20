@echo off
setlocal
chcp 65001 >nul 2>&1
title Tests - AI Gaming Companion
cd /d "%~dp0.."

echo.
echo  ============================================
echo  Test Suite
echo  ============================================
echo.

echo  [1/3] Python unit tests...
python -X utf8 -m pytest backend/tests/ -v --tb=short
set PY=%errorlevel%
echo.

echo  [2/3] Import chain...
python -X utf8 -c "import sys;sys.path.insert(0,'.');from backend.data.loader import *;from backend.tools.live_overlay import get_system_prompt;from backend.cv.event_detector import EventDetector;from backend.personality.engine import PersonalityEngine;from backend.memory.game_db import GameMemoryDB;from backend.ai.provider import create_provider_chain;print('  All imports OK')"
set IM=%errorlevel%
echo.

echo  [3/3] TypeScript...
cd frontend
call npx tsc --noEmit 2>&1
set TS=%errorlevel%
cd ..
echo.

echo  ============================================
echo  Results:
if %PY% EQU 0 (echo    [PASS] Python tests) else (echo    [FAIL] Python tests)
if %IM% EQU 0 (echo    [PASS] Import chain) else (echo    [FAIL] Import chain)
if %TS% EQU 0 (echo    [PASS] TypeScript) else (echo    [FAIL] TypeScript)
echo  ============================================
echo.
pause
