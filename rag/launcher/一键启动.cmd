@echo off
setlocal
title C-side VOC, B-side platform, RAG Hub, and RAG Frontend Launcher
pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\start-local-pipeline.ps1" -OpenBrowser
set "LAUNCH_EXIT=%ERRORLEVEL%"
echo.
if not "%LAUNCH_EXIT%"=="0" (
    echo Startup failed. Check local .env files, Python, Docker Desktop, and Ollama.
) else (
    echo C-side VOC, B-side platform, RAG Hub, and RAG frontend are ready.
)
echo.
popd
pause
exit /b %LAUNCH_EXIT%
