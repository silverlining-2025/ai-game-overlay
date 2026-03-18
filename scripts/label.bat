@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m backend.tools.labeler training_data/palworld
) else (
    python -m backend.tools.labeler training_data/palworld
)
pause
