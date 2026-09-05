@echo off
echo Creating Python virtual environment...
python -m venv venv

echo Activating venv and installing requirements...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo Building Svelte frontend...
cd ui
call npm install
call npm run build
cd ..

echo Installation complete! You can now run run.bat.
pause
