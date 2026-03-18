@echo off
cd /d "%~dp0\.."
python -m backend.tools.labeler training_data/palworld
pause
