@echo off
cd /d "%~dp0"
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
)
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing required packages...
pip install -r requirements.txt

echo.
echo Starting YouTube Downloader...
start "" pythonw downloader.py
