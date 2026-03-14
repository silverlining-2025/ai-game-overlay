@echo off
echo === AI Companion Overlay Setup ===
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

:: Clone or pull
if exist "ai-game-overlay" (
    echo Updating repo...
    cd ai-game-overlay
    git pull
) else (
    echo Cloning repo...
    git clone https://github.com/silverlining-2025/ai-game-overlay.git
    cd ai-game-overlay
)

:: Create venv if needed
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate venv
call .venv\Scripts\activate.bat

:: Install minimal deps (no torch/GPU needed — API only)
echo Installing dependencies...
pip install dxcam anthropic fastapi uvicorn sse-starlette opencv-python Pillow mss >nul 2>&1

:: Check for API key
if not exist "backend\.env" (
    echo.
    set /p APIKEY="Enter your Anthropic API key: "
    echo ANTHROPIC_API_KEY=%APIKEY%> backend\.env
    echo API key saved to backend\.env
)

:: Run
echo.
echo === Starting AI Companion ===
echo Open http://localhost:8080 in your browser
echo Press Ctrl+C to stop
echo.
python -m backend.tools.web_overlay --game maplestory --interval 3

pause
