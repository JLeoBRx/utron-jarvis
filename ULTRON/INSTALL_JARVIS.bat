@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title JARVIS - Instalacao
cd /d "%~dp0"

echo ============================================================
echo   JARVIS - instalacao local (Windows 10/11, 64 bits)
echo   Nada e apagado: .venv, modelos em assets e seus dados ficam.
echo ============================================================
echo.

rem ---------------------------------------------------------------- 1. Python (3.11 recomendado)
set "PY="
py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
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
    echo [AVISO] Alguma dependencia falhou. O JARVIS inicia em modo degradado e
    echo         o diagnostico abaixo mostra exatamente o que falta.
)

rem ---------------------------------------------------------------- 3. modelos locais de fala e de voz
set "STT_OK="
if exist "assets\stt\vosk-model-small-pt-0.3\final.mdl" set "STT_OK=1"
if exist "assets\stt\vosk-model-pt-fb-v0.1.1-20220516_2113\am\final.mdl" set "STT_OK=1"
set "VOICE_OK="
if exist "assets\voices\pt_BR-faber-medium.onnx" set "VOICE_OK=1"
if defined STT_OK if defined VOICE_OK goto models_ok
echo.
echo [AVISO] Modelos locais ausentes em assets (o pacote nao inclui modelos grandes).
echo         Se voce ja tem uma instalacao anterior (ULTRON ou JARVIS), informe a pasta dela
echo         para COPIAR os modelos (apenas arquivos que faltam; nada e sobrescrito ou apagado).
set "OLD="
set /p OLD="Pasta da instalacao anterior (Enter para pular): "
if defined OLD (
    if exist "!OLD!\assets" (
        robocopy "!OLD!\assets" "assets" /E /XC /XN /XO /NFL /NDL /NJH /NJS >nul
        echo Modelos copiados de "!OLD!\assets"
    ) else (
        echo [AVISO] "!OLD!\assets" nao existe.
    )
)
if not exist "assets\stt\vosk-model-small-pt-0.3\final.mdl" if not exist "assets\stt\vosk-model-pt-fb-v0.1.1-20220516_2113\am\final.mdl" (
    echo.
    echo Reconhecimento de fala: baixe o modelo vosk-model-small-pt-0.3 em https://alphacephei.com/vosk/models
    echo   e extraia para assets\stt\vosk-model-small-pt-0.3  ^(deve existir assets\stt\vosk-model-small-pt-0.3\final.mdl^)
)
if not exist "assets\voices\pt_BR-faber-medium.onnx" (
    echo.
    echo Voz neural: baixe pt_BR-faber-medium.onnx e pt_BR-faber-medium.onnx.json em
    echo   https://huggingface.co/rhasspy/piper-voices  ^(pasta pt/pt_BR/faber/medium^)
    echo   e coloque em assets\voices. Sem ela, o JARVIS usa a voz do Windows ^(SAPI^).
)
:models_ok

rem ---------------------------------------------------------------- 4. Ollama e modelos de IA locais
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

rem ---------------------------------------------------------------- 5. inicio automatico (opcional; so a chave do JARVIS em HKCU\...\Run)
echo.
choice /c SN /m "Iniciar o JARVIS automaticamente com o Windows (orbe recolhido)?"
if errorlevel 2 (
    "%VPY%" -m ultron.platform.autostart off
) else (
    "%VPY%" -m ultron.platform.autostart on
)

rem ---------------------------------------------------------------- 6. diagnostico
echo.
echo Componentes:
"%VPY%" TEST_JARVIS.py --env
echo.
echo Diagnostico do sistema:
"%VPY%" main.py --diagnose
echo.
echo Instalacao concluida. Inicie com START_JARVIS.bat
echo Teste de voz falando:   START_JARVIS.bat --voice-test
echo Calibrar a palavra de ativacao para a sua voz: Sistemas ^> VOZ ^> CALIBRAR
pause
