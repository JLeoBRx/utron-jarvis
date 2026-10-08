@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if exist requirements.txt pip install -r requirements.txt
if exist requirements-openai.txt pip install -r requirements-openai.txt

echo.
echo JARVIS instalado. Para iniciar: START_JARVIS.bat
pause
