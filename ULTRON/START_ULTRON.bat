@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo O ambiente do ULTRON ainda nao foi instalado. Execute INSTALL_ULTRON.bat primeiro.
    pause
    exit /b 1
)

rem START_ULTRON.bat              HUB neural
rem START_ULTRON.bat --console    modo console (texto)
rem START_ULTRON.bat --diagnose   relatorio de saude
rem START_ULTRON.bat --autostart  liga o inicio automatico com o Windows ( --no-autostart desliga )

if /i "%~1"=="--console" (
    ".venv\Scripts\python.exe" main.py --headless
    exit /b %errorlevel%
)
if /i "%~1"=="--diagnose" (
    ".venv\Scripts\python.exe" main.py --diagnose
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--autostart" (
    ".venv\Scripts\python.exe" -m ultron.platform.autostart on
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--no-autostart" (
    ".venv\Scripts\python.exe" -m ultron.platform.autostart off
    pause
    exit /b %errorlevel%
)
start "" ".venv\Scripts\pythonw.exe" main.py %*
