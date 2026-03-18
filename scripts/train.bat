@echo off
cd /d "%~dp0\.."
python -m backend.tools.train_classifier --data-dir training_data/palworld
pause
