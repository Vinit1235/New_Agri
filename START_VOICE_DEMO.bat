@echo off
echo ========================================
echo   SoilEdge Voice Assistant - Quick Start
echo ========================================
echo.

cd /d "%~dp0backend"

echo [1/3] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found! Please install Python 3.8+
    pause
    exit /b 1
)

echo.
echo [2/3] Installing dependencies...
pip install google-genai
if errorlevel 1 (
    echo WARNING: Failed to install google-genai
    echo You may need to run: pip install google-genai
)

echo.
echo [3/3] Starting backend server...
echo.
echo ========================================
echo  Voice Assistant is starting...
echo  Open: http://localhost:8000/voice-assistant.html
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.

python -m uvicorn app.main:app --reload --port 8000

pause
