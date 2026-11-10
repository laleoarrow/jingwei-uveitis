@echo off
setlocal
cd /d "%~dp0" || (
  echo Could not open the CFP Crop folder. Extract it to a local folder and try again.
  pause
  exit /b 1
)
set "check_version=import sys; sys.exit(not ((3, 10) <= sys.version_info < (3, 14)))"
if exist ".venv" goto environment
for %%V in (3.13 3.12 3.11 3.10) do (
  py -%%V -c "%check_version%" >nul 2>&1
  if not errorlevel 1 (
    py -%%V -m venv .venv
    if errorlevel 1 goto failed
    goto environment
  )
)
for %%P in (python python3 python3.13 python3.12 python3.11 python3.10) do (
  %%P -c "%check_version%" >nul 2>&1
  if not errorlevel 1 (
    %%P -m venv .venv
    if errorlevel 1 goto failed
    goto environment
  )
)
echo Install Python 3.10-3.13, or use the standalone CFP Crop download.
goto failed
:environment
".venv\Scripts\python.exe" -c "%check_version%" >nul 2>&1
if errorlevel 1 (
  echo The existing .venv must use Python 3.10-3.13. It has been left unchanged.
  echo Move it aside and reopen this launcher, or use the standalone CFP Crop download.
  goto failed
)
".venv\Scripts\python.exe" -c "import PIL; assert PIL.__version__ == '11.3.0'" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Could not start CFP Crop. Supported Python versions: 3.10-3.13.
pause
exit /b 1
