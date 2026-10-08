@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" jarvis_lock_setup.py on
) else (
  python jarvis_lock_setup.py on
)
pause
