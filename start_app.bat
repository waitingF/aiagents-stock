@echo off
REM AI股票分析系统启动脚本 - FastAPI + React

echo Starting AI stock analysis system...
echo ==================================================

if "%VIRTUAL_ENV%"=="" (
    echo Activating Python virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment is already active.
)

if not exist run.py (
    echo Error: run.py not found.
    pause
    exit /b 1
)

echo URL: http://localhost:8503
echo Press Ctrl+C to stop the server.
echo ==================================================

python run.py --host 127.0.0.1 --port 8503

if errorlevel 1 (
    echo.
    echo Server failed to start. Check the error output above.
    pause
)
