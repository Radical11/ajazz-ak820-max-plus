@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo [ERROR] The virtual environment is missing. Run install.bat first.
    pause
    exit /b 1
)

if not exist "ui\dist\index.html" (
    echo [ERROR] The UI has not been built. Run install.bat first.
    pause
    exit /b 1
)

if "%~1"=="--debug" (
    venv\Scripts\python.exe main.py --debug
    goto :eof
)

start "" venv\Scripts\pythonw.exe main.py %*
