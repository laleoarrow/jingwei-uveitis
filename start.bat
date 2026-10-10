@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please install the environment first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launch.py %*
if errorlevel 1 pause
