@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem START_JARVIS.bat                 abre o JARVIS (TARDIS, Noctario e as outras paginas pela navegacao ou F1-F7)
rem START_JARVIS.bat --console       modo console (texto)
rem START_JARVIS.bat --diagnose      saude completa + voz (8 etapas) e sai
rem START_JARVIS.bat --voice-test    teste de voz falando ("Jarvis, que horas sao?")
rem START_JARVIS.bat --mics          lista os microfones
rem START_JARVIS.bat --status        diz se o JARVIS esta em execucao
rem START_JARVIS.bat --stop          encerra o JARVIS em execucao (normalmente, sem forcar)
rem START_JARVIS.bat --backup        backup do banco (memorias, lembretes, rede)
rem START_JARVIS.bat --list-backups  lista os backups;  --restore-backup ARQUIVO  restaura um (JARVIS fechado)
rem START_JARVIS.bat --export ARQ    exporta a memoria pessoal (.json ou .csv) para um arquivo novo
rem START_JARVIS.bat --say "TEXTO"   executa um pedido e mostra a resposta
rem START_JARVIS.bat --autostart     liga o inicio automatico com o Windows ( --no-autostart desliga )
rem START_JARVIS.bat --help          todos os comandos
rem Comandos que respondem com texto rodam nesta janela (com o Python de console) e esperam uma tecla.

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente do JARVIS ainda nao foi instalado. Execute INSTALL_JARVIS.bat primeiro.
    pause
    exit /b 1
)
set "VPY=.venv\Scripts\python.exe"
set "VPYW=.venv\Scripts\pythonw.exe"

if /i "%~1"=="--console" goto console_mode
if /i "%~1"=="--mics" goto list_mics
if /i "%~1"=="--autostart" goto autostart_on
if /i "%~1"=="--no-autostart" goto autostart_off

rem comandos que escrevem uma resposta e saem: com o pythonw (sem console) a resposta se perderia
set "TEXT_COMMAND="
for %%A in (--diagnose --voice-test --list-mics --mic --status --stop --backup --list-backups --restore-backup --export --import-models --say --set-openai-key --use-openai --use-ollama --test-openai --autostart-check --headless --version --help -h) do (
    if /i "%~1"=="%%A" set "TEXT_COMMAND=1"
)
if defined TEXT_COMMAND goto text_command

if not exist "%VPYW%" set "VPYW=%VPY%"
start "" "%VPYW%" main.py %*
exit /b 0

:text_command
"%VPY%" main.py %*
set "CODE=%errorlevel%"
pause
exit /b %CODE%

:console_mode
"%VPY%" main.py --headless
exit /b %errorlevel%

:list_mics
"%VPY%" main.py --list-mics
set "CODE=%errorlevel%"
pause
exit /b %CODE%

:autostart_on
"%VPY%" -m ultron.platform.autostart on
set "CODE=%errorlevel%"
pause
exit /b %CODE%

:autostart_off
"%VPY%" -m ultron.platform.autostart off
set "CODE=%errorlevel%"
pause
exit /b %CODE%
