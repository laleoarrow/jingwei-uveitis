@echo off
setlocal
rem Let Windows PowerShell load its own modules, including when called from PowerShell 7.
set "PSModulePath="
set "PYTHONUTF8=1"
cd /d "%~dp0" || (
  echo Could not open the JingWei Crop folder. Extract it to a local folder and try again.
  if not defined CI pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "clip_exit=%errorlevel%"
if not "%clip_exit%"=="0" if not defined CI pause
exit /b %clip_exit%
