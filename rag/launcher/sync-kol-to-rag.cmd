@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-kol-to-rag.ps1" %*
exit /b %ERRORLEVEL%
