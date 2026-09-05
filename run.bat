@echo off
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Please run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

if "%1"=="--debug" (
    python main.py --debug
) else (
    python main.py
)
