@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo Run: python -m venv .venv ^&^& .venv\Scripts\activate.bat ^&^& pip install -r requirements.txt
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python server.py
pause
