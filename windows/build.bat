@echo off
rem Double-click to build windows\dist\WinISO-Downloader.exe
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
pause
