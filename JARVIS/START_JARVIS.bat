@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [JARVIS] Ambiente .venv nao encontrado.
  echo Execute INSTALAR_JARVIS.bat primeiro.
  pause
  exit /b 1
)
start "JARVIS" ".venv\Scripts\python.exe" "main.py"
