@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m backend.tools.auto_label --input training_data/palworld/frames --output training_data/palworld/auto_labeled
) else (
    python -m backend.tools.auto_label --input training_data/palworld/frames --output training_data/palworld/auto_labeled
)
pause
