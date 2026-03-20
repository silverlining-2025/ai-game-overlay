@echo off
chcp 65001 >nul 2>&1
title AI Gaming Companion — Tests
cd /d "%~dp0.."

echo.
echo  ============================================
echo   AI Gaming Companion — Test Suite
echo  ============================================
echo.

REM Python tests
echo  [1/3] Python tests (pytest)...
echo  ----------------------------------------
python -X utf8 -m pytest backend/tests/ -v --tb=short
set PY_RESULT=%errorlevel%
echo.

REM Python import chain test
echo  [2/3] Import chain test...
echo  ----------------------------------------
python -X utf8 -c "import sys; sys.path.insert(0,'.'); from backend.data.loader import *; from backend.tools.live_overlay import get_system_prompt; from backend.cv.event_detector import EventDetector; from backend.personality.engine import PersonalityEngine; from backend.memory.game_db import GameMemoryDB; from backend.ai.provider import create_provider_chain; from backend.tts.engine import CHARACTER_VOICES; print('  All imports OK')"
set IMPORT_RESULT=%errorlevel%
echo.

REM TypeScript type check
echo  [3/3] TypeScript check...
echo  ----------------------------------------
cd frontend
call npx tsc --noEmit
set TS_RESULT=%errorlevel%
cd ..
echo.

REM Summary
echo  ============================================
echo   Results:
if %PY_RESULT% EQU 0 (echo    [PASS] Python tests) else (echo    [FAIL] Python tests)
if %IMPORT_RESULT% EQU 0 (echo    [PASS] Import chain) else (echo    [FAIL] Import chain)
if %TS_RESULT% EQU 0 (echo    [PASS] TypeScript) else (echo    [FAIL] TypeScript)
echo  ============================================
echo.
pause
