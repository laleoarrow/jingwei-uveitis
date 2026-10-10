@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
set "jingwei_exit=%errorlevel%"
if not "%jingwei_exit%"=="0" if not defined CI pause
exit /b %jingwei_exit%
