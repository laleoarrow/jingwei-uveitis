@echo off
setlocal
rem Let Windows PowerShell load its own modules, including when called from PowerShell 7.
set "PSModulePath="
set "PYTHONUTF8=1"
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "jingwei_exit=%errorlevel%"
if not "%jingwei_exit%"=="0" if not defined CI pause
exit /b %jingwei_exit%
