@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Please install Python 3.10 or newer, then run this file again.
  echo Download: https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating the local Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

echo [2/3] Installing/checking dependencies...
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/3] Starting the platform...
echo The browser will open at http://127.0.0.1:8000
echo Keep this window open while viewing the platform.
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
goto :end

:error
echo.
echo Startup failed. Please take a screenshot of this window for troubleshooting.
pause

:end
endlocal
