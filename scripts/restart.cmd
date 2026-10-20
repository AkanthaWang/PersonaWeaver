@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
set "START_SCRIPT=%PROJECT_ROOT%\scripts\start.cmd"

if not exist "%START_SCRIPT%" (
  echo [ERROR] Start script not found:
  echo         "%START_SCRIPT%"
  exit /b 1
)

echo Stopping PersonaWeaver services...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$titles = @('PersonaWeaver Backend', 'PersonaWeaver Frontend'); Get-Process | Where-Object { $titles -contains $_.MainWindowTitle } | ForEach-Object { taskkill.exe /PID $_.Id /T /F | Out-Null }"

timeout /t 1 /nobreak >NUL

echo Starting PersonaWeaver services...
call "%START_SCRIPT%"

endlocal
