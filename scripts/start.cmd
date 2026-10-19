@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
set "FRONTEND_START=%PROJECT_ROOT%\frontend\start.cmd"
set "BACKEND_START=%PROJECT_ROOT%\backend\start.cmd"

if not exist "%FRONTEND_START%" (
  echo [ERROR] Frontend start script not found:
  echo         "%FRONTEND_START%"
  exit /b 1
)

if not exist "%BACKEND_START%" (
  echo [ERROR] Backend start script not found:
  echo         "%BACKEND_START%"
  exit /b 1
)

echo Starting PersonaWeaver backend and frontend...
start "PersonaWeaver Backend" cmd /k call "%BACKEND_START%"
start "PersonaWeaver Frontend" cmd /k call "%FRONTEND_START%"

echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Close the two opened windows to stop the services.
endlocal
