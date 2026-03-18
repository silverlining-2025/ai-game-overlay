@echo off
REM Full training data pipeline: download -> extract -> auto_label -> review
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo ============================================================
echo  AI Game Overlay - Training Data Pipeline
echo ============================================================
echo.

REM Step 1: Download training videos (if youtube dir exists)
if exist "training_data\palworld\youtube" (
    echo [1/4] Downloading training videos...
    %PYTHON% -m backend.tools.download_videos --output training_data/palworld/youtube
    if errorlevel 1 (
        echo WARNING: Download had errors, continuing...
    )
) else (
    echo [1/4] Skipping download (no training_data\palworld\youtube directory)
    echo       Place videos in training_data/palworld/youtube/
)
echo.

REM Step 2: Extract frames from videos
echo [2/4] Extracting frames...
%PYTHON% -m backend.tools.extract_frames --input training_data/palworld/youtube --output training_data/palworld/frames
if errorlevel 1 (
    echo WARNING: Frame extraction had errors, continuing...
)
echo.

REM Step 3: Auto-label with CLIP
echo [3/4] Auto-labeling with CLIP...
%PYTHON% -m backend.tools.auto_label --input training_data/palworld/frames --output training_data/palworld/auto_labeled --resume
if errorlevel 1 (
    echo ERROR: Auto-labeling failed.
    pause
    exit /b 1
)
echo.

REM Step 4: Human review
echo [4/4] Opening review tool...
%PYTHON% -m backend.tools.review_labels training_data/palworld/auto_labeled --frames-dir training_data/palworld/frames
if errorlevel 1 (
    echo ERROR: Review tool failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Pipeline complete!
echo ============================================================
pause
