@echo off
setlocal EnableExtensions
chcp 65001 >nul
title JARVIS - Atualizacao
cd /d "%~dp0"

rem Uso: extraia a nova versao POR CIMA desta pasta (substituindo os arquivos do programa) e rode
rem este script. .venv, modelos em assets e seus dados em %%LOCALAPPDATA%%\ULTRON sao preservados.

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente nao instalado: execute INSTALL_JARVIS.bat.
    pause
    exit /b 1
)
set "VPY=.venv\Scripts\python.exe"

echo 1/4 Encerrando o JARVIS em execucao (se houver) ...
"%VPY%" main.py --stop
if errorlevel 1 (
    echo [ERRO] O JARVIS continua aberto. Feche pela bandeja ^(Sair^) e rode este script de novo.
    pause
    exit /b 1
)
echo.
echo 2/4 Backup do banco antes de atualizar ...
"%VPY%" main.py --backup
if errorlevel 1 (
    echo [ERRO] O backup falhou; a atualizacao foi interrompida para proteger seus dados.
    pause
    exit /b 1
)
echo.
echo 3/4 Atualizando dependencias ...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install --upgrade -r requirements.txt
echo.
echo 4/4 Diagnostico ...
"%VPY%" main.py --diagnose
echo.
echo Atualizacao concluida. Inicie com START_JARVIS.bat
echo Para voltar ao estado anterior: START_JARVIS.bat --stop e depois
echo   .venv\Scripts\python.exe main.py --list-backups   e   --restore-backup ARQUIVO
pause
exit /b 0
