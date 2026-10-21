@echo off
rem JARVIS - configurar a OpenAI (opcional; o JARVIS original tinha configurar_openai.bat)
rem A chave fica no Gerenciador de Credenciais do Windows, nunca em arquivo de configuracao.
setlocal
cd /d "%~dp0"
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [ERRO] Ambiente nao instalado. Rode INSTALL_JARVIS.bat primeiro.
    pause
    exit /b 1
)
echo JARVIS - configurar a OpenAI
echo.
echo 1. Chave da OpenAI ^(guardada no Gerenciador de Credenciais do Windows^)
"%VPY%" main.py --set-openai-key
echo.
echo 2. Usar a OpenAI como cerebro ^(os dados das conversas saem do computador^)
"%VPY%" main.py --use-openai
echo.
echo 3. Teste de conexao
"%VPY%" main.py --test-openai
echo.
echo Para voltar ao cerebro local: START_JARVIS.bat --use-ollama
pause
