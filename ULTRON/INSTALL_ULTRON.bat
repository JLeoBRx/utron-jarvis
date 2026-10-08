@echo off
setlocal EnableExtensions
chcp 65001 >nul
title ULTRON - Instalacao
cd /d "%~dp0"

echo ============================================================
echo   ULTRON - instalacao local (Windows 10/11, 64 bits)
echo ============================================================
echo.

rem ---------------------------------------------------------------- 1. Python
set "PY="
py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ERRO] Python 3.10 ou superior nao encontrado.
    echo        Instale o Python 3.11 de https://www.python.org/downloads/
    echo        marcando "Add python.exe to PATH" e rode esta instalacao de novo.
    pause
    exit /b 1
)
echo Python encontrado:
%PY% --version

rem ---------------------------------------------------------------- 2. ambiente virtual e dependencias
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Criando o ambiente virtual .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente virtual.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"
echo.
echo Instalando dependencias (requirements.txt) ...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [AVISO] Alguma dependencia falhou. O ULTRON inicia em modo degradado e
    echo         o diagnostico abaixo mostra exatamente o que falta.
)

rem ---------------------------------------------------------------- 3. Ollama e modelos locais
echo.
where ollama >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama nao encontrado. Instale de https://ollama.com/download
    echo         e depois rode: ollama pull qwen2.5:3b  e  ollama pull qwen2.5vl:3b
) else (
    choice /c SN /m "Baixar agora os modelos locais qwen2.5:3b (texto) e qwen2.5vl:3b (visao)? Cerca de 5 GB"
    if not errorlevel 2 (
        ollama pull qwen2.5:3b
        ollama pull qwen2.5vl:3b
    )
)

rem ---------------------------------------------------------------- 4. inicio automatico (opcional)
echo.
choice /c SN /m "Iniciar o ULTRON automaticamente com o Windows (orbe recolhido)?"
if errorlevel 2 (
    "%VPY%" -m ultron.platform.autostart off
) else (
    "%VPY%" -m ultron.platform.autostart on
)

rem ---------------------------------------------------------------- 5. diagnostico
echo.
echo Diagnostico do sistema:
"%VPY%" main.py --diagnose
echo.
echo Instalacao concluida. Inicie com START_ULTRON.bat
echo Calibrar a palavra de ativacao para a sua voz:  .venv\Scripts\python.exe -m ultron.voice.calibrate
pause
