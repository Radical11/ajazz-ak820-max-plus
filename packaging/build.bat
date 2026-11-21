@echo off
setlocal
rem Build AK820 Studio into dist-app\AK820Studio\ (run from anywhere).
set "ROOT=%~dp0.."
pushd "%ROOT%"

echo [1/4] Activating virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Run install.bat first.
    goto :fail
)
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate the virtual environment.
    goto :fail
)

echo [2/4] Ensuring PyInstaller is installed...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] pip could not install pyinstaller.
        goto :fail
    )
)

echo [3/4] Building the UI...
pushd ui
call npm run build
if errorlevel 1 (
    popd
    echo [ERROR] npm run build failed.
    goto :fail
)
popd

echo [4/4] Running PyInstaller...
python -m PyInstaller --noconfirm --clean --distpath dist-app --workpath build-app packaging\ak820studio.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    goto :fail
)

if not exist "dist-app\AK820Studio\AK820Studio.exe" (
    echo [ERROR] Expected dist-app\AK820Studio\AK820Studio.exe was not produced.
    goto :fail
)

echo.
echo Build complete.
echo Output folder: %ROOT%\dist-app\AK820Studio
echo Next: iscc packaging\installer.iss   (requires Inno Setup 6)
popd
pause
exit /b 0

:fail
echo.
echo Build failed. See the error above.
popd
pause
exit /b 1
