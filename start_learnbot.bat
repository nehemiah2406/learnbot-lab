@echo off
rem Start LearnBot on this laptop and open it in the browser (http://127.0.0.1:8765).
rem Close this window to stop LearnBot.
cd /d "%~dp0"
title LearnBot
if not exist ".venv\Scripts\python.exe" (
  echo LearnBot's Python was not found in "%~dp0.venv". Please set up the .venv first.
  pause
  exit /b 1
)
.venv\Scripts\python scripts\run_app.py --open
if errorlevel 1 pause
