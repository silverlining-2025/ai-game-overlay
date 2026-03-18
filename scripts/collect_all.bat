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

REM Step 1: Download (if a download script exists)
if exist "scripts\download.bat" (
    echo [1/4] Downloading training data...
    call scripts\download.bat
    if errorlevel 1 (
        echo ERROR: Download failed.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Skipping download (no download.bat found)
    echo       Place frames in training_data/palworld/frames/
)
echo.

REM Step 2: Extract frames (if an extract script exists)
if exist "scripts\extract.bat" (
    echo [2/4] Extracting frames...
    call scripts\extract.bat
    if errorlevel 1 (
        echo ERROR: Extraction failed.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Skipping extraction (no extract.bat found)
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
