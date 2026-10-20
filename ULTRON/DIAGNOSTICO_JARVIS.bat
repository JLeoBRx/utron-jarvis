@echo off
setlocal EnableExtensions
chcp 65001 >nul
title JARVIS - Diagnostico
cd /d "%~dp0"

rem Modo de diagnostico: mostra o que esta instalado, o que falta e por que (sem alterar nada).

set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [AVISO] Ambiente .venv ausente: execute INSTALL_JARVIS.bat.
    echo Relatorio do Python do sistema:
    py -3 TEST_JARVIS.py --env 2>nul || python TEST_JARVIS.py --env
    pause
    exit /b 1
)
echo ==================== componentes ====================
"%VPY%" TEST_JARVIS.py --env
echo.
echo ==================== estado ====================
"%VPY%" main.py --status
echo.
echo ==================== saude e voz (8 etapas) ====================
"%VPY%" main.py --diagnose
echo.
echo ==================== backups ====================
"%VPY%" main.py --list-backups
echo.
echo Registro detalhado: %LOCALAPPDATA%\ULTRON\logs\ultron.log
echo Teste de voz falando: START_JARVIS.bat --voice-test
pause
