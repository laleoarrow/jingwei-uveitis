@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import PIL; assert PIL.__version__ == '11.3.0'" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Could not start CFP Crop. Use Python 3.10 or later, or the standalone download.
pause
exit /b 1

