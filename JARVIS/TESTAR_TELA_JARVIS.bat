@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" jarvis_lock.py
) else (
  python jarvis_lock.py
)
