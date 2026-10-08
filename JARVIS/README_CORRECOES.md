# J.A.R.V.I.S. — pacote corrigido

## O que foi corrigido nesta revisão

1. **Inicialização sem `core/runtime.py`**
   - `main.py` agora mantém compatibilidade com `core.runtime` quando existir.
   - Se a pasta `core` não estiver presente, cai automaticamente para `jarvis_hud.main`.
   - Foi incluído um `core/runtime.py` mínimo e compatível para evitar a falha de importação do projeto distribuído.

2. **Inicialização da aprendizagem**
   - `backend.py` usava `learning_engine.initialize()` sem importar `learning_engine`.
   - O import foi corrigido.

3. **TTS/voz do Windows**
   - O worker de voz foi reforçado para inicializar COM corretamente no Windows.
   - `pythoncom` é usado quando disponível; caso contrário, há fallback para `ole32.CoInitialize`.
   - A voz neural Piper continua opcional.
   - Qualquer falha da voz neural volta para `pyttsx3`.
   - Falhas de TTS não deixam o JARVIS preso permanentemente em `SPEAKING`.

4. **Ambiente Python**
   - `requirements.txt` foi incluído para Python 3.11.x.
   - PyAudio foi fixado em 0.2.14.
   - `cffi` e `pywin32` foram incluídos para as partes nativas/COM.

5. **Diagnóstico**
   - `diagnostico.py` verifica Python, dependências, PyAudio, pyttsx3 e modelo Vosk.

## Como instalar

Use Python **3.11.x** e um ambiente virtual:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

No PowerShell, se a política bloquear `Activate.ps1`, use o CMD e `activate.bat`, ou execute diretamente `.venv\Scripts\python.exe`.

## Diagnóstico

```cmd
python diagnostico.py
```

## Iniciar

```cmd
python Jarvis.py
```

## Ollama e Vosk

O projeto continua dependendo do Ollama para o núcleo local de linguagem e do modelo Vosk configurado em `VOSK_MODEL` para reconhecimento de voz. O pacote não inclui automaticamente esses modelos externos.

## Limite da validação

Esta revisão foi validada por análise estática/compilação dos arquivos Python. Não foi possível executar o HUD Windows/PySide6, SAPI, Vosk e Ollama neste ambiente de desenvolvimento. Portanto, problemas dependentes do hardware, drivers, modelos externos ou da configuração específica do Windows ainda precisam ser verificados no PC.
