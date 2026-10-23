@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

set "BACKEND_PORT=8000"
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%BACKEND_PORT% .*LISTENING"') do set "PORT_PID=%%P"

if defined PORT_PID (
  set "HEALTH_STATUS="
  for /f "delims=" %%S in ('curl.exe -sS -o NUL -w "%%{http_code}" http://127.0.0.1:%BACKEND_PORT%/health 2^>NUL') do set "HEALTH_STATUS=%%S"
  if "!HEALTH_STATUS!"=="200" (
    curl.exe -fsS --max-time 3 http://127.0.0.1:%BACKEND_PORT%/health 2>NUL | findstr /C:"ecnu-env-v1" >NUL
    if errorlevel 1 (
      echo [ERROR] Existing backend PID !PORT_PID! has not loaded ECNU configuration support.
      echo Stop the old backend before starting again.
      echo Run in PowerShell: Stop-Process -Id !PORT_PID!
      echo Then run scripts\start.cmd again.
      exit /b 1
    )
    echo PersonaWeaver backend is already running on http://127.0.0.1:%BACKEND_PORT% ^(PID !PORT_PID!^).
    exit /b 0
  )

  echo [ERROR] Port %BACKEND_PORT% is already occupied by process !PORT_PID!.
  tasklist /FI "PID eq !PORT_PID!"
  echo Stop that process or configure it to use another port before starting PersonaWeaver.
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT% %*
) else (
  conda run --no-capture-output -n mercury312 python -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT% %*
)
