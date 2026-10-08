@echo off
setlocal
color 0B
echo ===============================================
echo        J.A.R.V.I.S. - OPENAI
 echo ===============================================
echo.
set /p "KEY=Cole sua OPENAI_API_KEY e pressione ENTER: "
if "%KEY%"=="" (
  echo Nenhuma chave informada.
  pause
  exit /b 1
)
setx OPENAI_API_KEY "%KEY%" >nul
setx JARVIS_AI_PROVIDER "openai" >nul
setx JARVIS_OPENAI_MODEL "gpt-5.6-sol" >nul
echo.
echo Chave salva no ambiente do usuario.
echo Feche e abra o terminal/JARVIS para carregar a chave.
echo ===============================================
pause
