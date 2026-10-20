@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem START_JARVIS.bat                 HUB principal (JARVIS CORE; TARDIS pelo botao ou F2)
rem START_JARVIS.bat --console       modo console (texto)
rem START_JARVIS.bat --diagnose      saude completa + voz (8 etapas) e sai
rem START_JARVIS.bat --voice-test    teste de voz falando ("Jarvis, que horas sao?")
rem START_JARVIS.bat --mics          lista os microfones
rem START_JARVIS.bat --status        diz se o JARVIS esta em execucao
rem START_JARVIS.bat --stop          encerra o JARVIS em execucao (normalmente, sem forcar)
rem START_JARVIS.bat --backup        backup do banco (memorias, lembretes, rede)
rem START_JARVIS.bat --autostart     liga o inicio automatico com o Windows ( --no-autostart desliga )

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente do JARVIS ainda nao foi instalado. Execute INSTALL_JARVIS.bat primeiro.
    pause
    exit /b 1
)
set "VPY=.venv\Scripts\python.exe"
set "VPYW=.venv\Scripts\pythonw.exe"

if /i "%~1"=="--console" (
    "%VPY%" main.py --headless
    exit /b %errorlevel%
)
if /i "%~1"=="--diagnose" (
    "%VPY%" main.py --diagnose
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--voice-test" (
    "%VPY%" main.py --voice-test
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--mics" (
    "%VPY%" main.py --list-mics
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--status" (
    "%VPY%" main.py --status
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--stop" (
    "%VPY%" main.py --stop
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--backup" (
    "%VPY%" main.py --backup
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--autostart" (
    "%VPY%" -m ultron.platform.autostart on
    pause
    exit /b %errorlevel%
)
if /i "%~1"=="--no-autostart" (
    "%VPY%" -m ultron.platform.autostart off
    pause
    exit /b %errorlevel%
)
if not exist "%VPYW%" set "VPYW=%VPY%"
start "" "%VPYW%" main.py %*
