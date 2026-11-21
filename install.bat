@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  AK820 Studio - installer
echo ============================================
echo.
echo Before you continue:
echo   - Close the official AJAZZ software.
echo   - Turn off its Auto Run setting, or it will compete with AK820 Studio for the keyboard.
echo.

echo [1/5] Preparing the Python virtual environment...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment. Check that Python 3.11+ is installed and on PATH.
        goto :fail
    )
)

echo [2/5] Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Could not upgrade pip. Check your internet connection.
    goto :fail
)

echo [3/5] Installing Python requirements...
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip could not install requirements.txt.
    goto :fail
)

echo [4/5] Installing frontend packages...
cd ui
call npm install
if errorlevel 1 (
    echo [ERROR] npm install failed. Check that Node.js 18+ is installed.
    cd ..
    goto :fail
)

echo [5/5] Building the UI...
call npm run build
if errorlevel 1 (
    echo [ERROR] npm run build failed.
    cd ..
    goto :fail
)
cd ..

echo.
echo Installation complete. Run run.bat to start AK820 Studio.
pause
exit /b 0

:fail
echo.
echo Installation failed. Fix the error above and run install.bat again.
pause
exit /b 1
