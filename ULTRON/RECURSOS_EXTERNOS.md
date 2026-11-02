# JARVIS — Recursos que dependem de serviços ou hardware externos

> Rascunho da Fase 8 (entrega em pausa até a confirmação da inicialização no seu Windows).

Entregável 19. Tudo o que o JARVIS usa e que **não vem dentro do programa**: serviços, modelos, bibliotecas
nativas, partes do Windows e hardware. Para cada um: para que serve, como configurar, o que acontece sem ele
e o que foi verificado. Nenhum destes recursos é fingido: sem ele, a função diz que está indisponível e por
quê (DIAGNÓSTICOS, `START_JARVIS.bat --diagnose` ou `TEST_JARVIS.py --env` mostram o estado de cada um).

Legenda da última coluna: **CI** = executado no CI do GitHub (Linux e Windows Server 2025, sem microfone,
áudio, GPU ou área de trabalho); **simulado** = coberto por testes com um substituto (servidor local, porta
virtual, simulador); **não verificado** = depende do seu computador ou do robô.

## 1. Inteligência

| Recurso | Para quê | Como configurar | Sem ele | Verificado |
|---|---|---|---|---|
| **Ollama** (serviço local, `http://127.0.0.1:11434`) | o cérebro do JARVIS: conversa, planejamento, escolha de ferramentas, análises da TARDIS (o **mesmo** modelo, com instruções próprias) | instale de ollama.com/download; `ollama pull qwen2.5:3b` (texto) e `ollama pull qwen2.5vl:3b` (visão) — o `INSTALL_JARVIS.bat` oferece; endereço em `ollama_url` ou `JARVIS_OLLAMA_URL`; o JARVIS tenta abrir o Ollama sozinho (`ollama_autostart`) | "Ollama indisponível": continuam funcionando os comandos diretos (abrir programas, horas, lembretes, notas, memória pessoal, Noctário, diagnóstico); a TARDIS responde "sem modelo: análise determinística" | simulado (servidor HTTP que imita a API); o modelo real não roda aqui |
| **OpenAI** (opcional; serviço na internet, cobrado) | cérebro alternativo, com pesquisa na web | `CONFIGURAR_OPENAI.bat` ou CONFIGURAÇÕES > INTELIGÊNCIA: a chave vai para o **Gerenciador de Credenciais do Windows** (ou a variável `OPENAI_API_KEY`), nunca para o `settings.json`; exige confirmação explícita porque **os dados saem do computador**; volta: `START_JARVIS.bat --use-ollama` | nada muda: o padrão é o Ollama local (LOCAL MODE) | simulado (provedor falso); nunca chamado com uma chave real |
| **Geração de imagens** (opcional) | "imagine/gere uma imagem de…" | Stable Diffusion WebUI local em `127.0.0.1:7860` com `--api`, ou `diffusers` + `torch` (ver `requirements-optional.txt`; pesado, GPU recomendada) | a ação responde que não há modelo de imagem; o resto da imaginação (conceitos, cenários) funciona | não verificado |

## 2. Voz e áudio

| Recurso | Para quê | Como configurar | Sem ele | Verificado |
|---|---|---|---|---|
| **Modelo Vosk** em português (arquivos locais, ~50 MB o pequeno) | reconhecimento de fala offline | `assets\stt\vosk-model-small-pt-0.3\` (ou o grande); o instalador copia de uma instalação anterior sem sobrescrever (`--import-models PASTA`) ou mostra a fonte oficial (alphacephei.com/vosk/models) | o JARVIS funciona por texto | real: fala sintetizada pelo Piper reconhecida pelo Vosk com os modelos do repositório (**sem microfone**) |
| **Voz Piper** `pt_BR-faber-medium` (arquivos locais) | a voz do JARVIS e os fonemas que movem a boca do avatar | `assets\voices\pt_BR-faber-medium.onnx` + `.onnx.json` (huggingface.co/rhasspy/piper-voices) | usa a voz do Windows (SAPI, via `pyttsx3`/`pywin32`); a boca segue o espectro do áudio | real (síntese e sincronia medidas com o áudio gerado) |
| **Microfone** | escuta e palavra de ativação "Jarvis" | Windows: Configurações > Privacidade > Microfone > permitir aplicativos da área de trabalho; escolha em CONFIGURAÇÕES > VOZ E ÁUDIO ou `START_JARVIS.bat --mics`; calibre em DIAGNÓSTICOS > VOZ > CALIBRAR | só texto; o diagnóstico de voz (8 etapas) diz em que etapa parou | **não verificado** (não há microfone nos ambientes de teste) |
| **Saída de áudio** (alto-falante/fone) | fala, sons da interface | CONFIGURAÇÕES > VOZ E ÁUDIO > saída de áudio (vazio = padrão do sistema) | responde só com texto e legendas | **não verificado** |
| **PortAudio** (embutido no `sounddevice`; PyAudio opcional) | abrir microfone e saída | instalado pelo `requirements.txt` | sem áudio, como acima | CI (instalação); o dispositivo real não |

## 3. Windows

| Recurso | Para quê | Como configurar | Sem ele | Verificado |
|---|---|---|---|---|
| **Python 3.11** (3.10–3.13) | executar o JARVIS | python.org, marcando *Add python.exe to PATH*; o `INSTALL_JARVIS.bat` cria o `.venv` | não instala | CI: instalação pelo `INSTALL_JARVIS.bat` a partir do ZIP extraído (Windows Server 2025) |
| **Interface** (PySide6 6.8) | janela, avatar, TARDIS, painel do Noctário | `requirements.txt` | modo console (texto) | CI (Qt offscreen); a tela real, a bandeja e as notificações **não** |
| **UI Automation** (`pywinauto`), **volume** (`pycaw`, `comtypes`), **teclado/mouse** (`pyautogui`) | elementos de janelas, volume verificável, teclas de mídia | `requirements.txt` | cada ação informa a biblioteca que falta | não verificado (exigem área de trabalho interativa) |
| **Lixeira** (`send2trash`) | toda exclusão vai para a Lixeira | `requirements.txt` | a exclusão é recusada (nunca apaga direto) | simulado (Lixeira falsa) |
| **Gerenciador de Credenciais** (`keyring`) | guardar a chave da OpenAI | automático no Windows | a chave só pela variável de ambiente; nunca em arquivo | simulado (cofre falso) |
| **Registro do Windows** — só `HKCU\...\Run`, valor `JARVIS` (e a entrada antiga `ULTRON` que aponte para esta instalação) | iniciar com o Windows | só por clique seu (bandeja, CONFIGURAÇÕES, `START_JARVIS.bat --autostart`) ou pela pergunta do instalador; `--unattended` não mexe | não inicia sozinho | CI confere que a instalação sem perguntas **não** altera o registro; ligar/desligar de verdade **não verificado** |
| **Captura de tela** (`mss`, `Pillow`) e **OCR** (opcional: `pytesseract` + o programa Tesseract OCR) | "o que há na tela?", Observador | Tesseract: github.com/UB-Mannheim/tesseract/wiki | sem OCR, o sensor de texto da tela fica indisponível e a análise visual pelo modelo `qwen2.5vl:3b` continua; sem captura, a ação informa | simulado |
| **GPU / OpenGL** (opcional) | renderização 3D por GPU | CONFIGURAÇÕES > APARÊNCIA > GPU; DIAGNÓSTICOS > SERVIÇOS E GPU > DETECTAR OPENGL | CPU (padrão); se a GPU falhar, volta para a CPU e diz por quê | OpenGL por software (Mesa) no contêiner; GPU real **não verificada** |

## 4. Rede

| Recurso | Para quê | Como configurar | Sem ele | Verificado |
|---|---|---|---|---|
| **Rede local** (tabela de vizinhos, ping de 1 pacote, DNS reverso; SSDP só se você ligar `network_ssdp`) | DIAGNÓSTICOS > REDE LOCAL | `network_discovery` (padrão ligado); só a sub-rede privada da interface ativa; **descobrir não é administrar** | a página diz que não há dados | simulado; a rede física **não** |
| **Teste de internet** (1.1.1.1:443 e 8.8.8.8:53) | "estou conectado?" | desligado no LOCAL MODE | responde que o teste está desligado | conferido por teste (são as únicas conexões TCP do código) |
| **Base IEEE de fabricantes** (`standards-oui.ieee.org`) | nomes de fabricantes dos aparelhos | só por pedido seu ("atualize os fabricantes"), com autorização | usa a lista embutida | não verificado |
| **Navegador e sites** | "pesquise…", "abra o YouTube" | abre o navegador padrão; o JARVIS não lê páginas por conta própria | — | não verificado |

## 5. Noctário (robô)

| Recurso | Para quê | Como configurar | Sem ele | Verificado |
|---|---|---|---|---|
| **ESP32 DevKit + TB6612FNG + 8 sensores QTR + sensor de cruzamento + LED** (pinagem em `firmware/noctario/README.md`) | o robô | montagem conforme o README do firmware | a página mostra **SEM CONEXÃO — nenhum dado do robô**; o simulador continua disponível, sempre rotulado | firmware compilado para a ESP32 no CI e núcleo testado no PC; **gravar na placa e o robô real: não verificados** |
| **PlatformIO** (ou Arduino IDE com o core ESP32) | compilar e gravar o firmware | `cd firmware/noctario && pio run -t upload` | — | CI compila (`firmware.bin`); gravação não |
| **Bluetooth Clássico (SPP)** pareado no Windows | link PC ↔ robô | parear "Noctario"; em CONFIGURAÇÕES > NOCTÁRIO: *Porta COM do Bluetooth* (`pyserial`) ou *Bluetooth direto* (endereço do robô) | sem link vale a política do firmware (padrão: parar, cão de guarda de 1,5 s) | simulado (porta serial virtual, servidor local); Bluetooth real **não** |
| **Botão físico de emergência** que corte a alimentação dos motores | segurança | na montagem | — | **obrigatório**: a parada pelo Bluetooth não o substitui |

Pontos que só a bancada confirma (ajustáveis pela interface, sem regravar): ordem física dos sensores e
sentido de cada motor. Roteiro da primeira vez: `firmware/noctario/README.md`.
