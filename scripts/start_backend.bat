@echo off
echo [AI Game Overlay] Starting backend...
cd /d "%~dp0..\backend"

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo Starting capture + WS server on port 9600...
python main.py --game minesweeper --debug
pause
