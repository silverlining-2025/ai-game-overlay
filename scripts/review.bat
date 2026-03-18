@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m backend.tools.review_labels training_data/palworld/auto_labeled --frames-dir training_data/palworld/frames
) else (
    python -m backend.tools.review_labels training_data/palworld/auto_labeled --frames-dir training_data/palworld/frames
)
pause
