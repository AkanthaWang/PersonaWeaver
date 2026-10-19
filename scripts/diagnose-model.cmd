@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m backend.scripts.check_model_connection
) else (
  python -m backend.scripts.check_model_connection
)
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
