# ULTRON — Neural Core

ULTRON é uma inteligência computacional que vive no seu computador: percebe a tela, as
janelas, os processos, a rede local e os dispositivos; mantém um **World Model** e um
**Neural Graph** persistentes; planeja objetivos de várias etapas; executa ações no
Windows **com verificação independente**; recupera-se de falhas com tentativas limitadas;
conversa por voz (offline) e imagina conceitos, cenários e mundos.

É **local-first**: o cérebro principal é o Ollama nesta máquina (`qwen2.5:3b` para texto,
`qwen2.5vl:3b` para visão). Nada sai do computador sem que você permita.

O ULTRON substitui o JARVIS. O relatório de auditoria e as decisões da transformação
estão em [`ARCHITECTURE_REPORT.md`](ARCHITECTURE_REPORT.md).

---

## Instalação (Windows 10/11, 64 bits)

1. Instale o **Python 3.11** (python.org, marque *Add python.exe to PATH*).
2. Instale o **Ollama** (ollama.com/download).
3. Execute **`INSTALL_ULTRON.bat`**. Ele cria `.venv`, instala `requirements.txt`, oferece
   baixar os modelos (`qwen2.5:3b` e `qwen2.5vl:3b`, ~5 GB), oferece o início automático e
   termina com um diagnóstico completo.
4. Inicie com **`START_ULTRON.bat`**.

| Comando | Efeito |
|---|---|
| `START_ULTRON.bat` | HUB neural (interface completa) |
| `START_ULTRON.bat --console` | modo console (texto, sem interface) |
| `START_ULTRON.bat --diagnose` | relatório de saúde e sai |
| `START_ULTRON.bat --autostart` / `--no-autostart` | liga/desliga o início com o Windows |
| `python main.py --say "que horas são"` | executa um pedido e sai |
| `python -m ultron.voice.calibrate` | calibra a palavra de ativação para a sua voz |
| `python TEST_ULTRON.py` | suíte de testes + relatório do ambiente |

Opcionais (`requirements-optional.txt`): OCR (`pytesseract` + Tesseract OCR), saída de
áudio alternativa (`sounddevice`) e geração de imagens local (Stable Diffusion WebUI em
`127.0.0.1:7860` com `--api`, ou `diffusers` com `ULTRON_IMAGE_MODEL_DIR` apontando para um
modelo já baixado). Sem eles, o ULTRON informa exatamente o que falta — nunca simula.

---

## Como falar com o ULTRON

**Voz.** Diga **"Ultron"** no início da frase: *"Ultron, abra o bloco de notas"*. Depois de
uma resposta, há uma janela de continuação (12 s) em que não é preciso repetir o nome.
Falas que não começam com "Ultron" fora dessa janela são descartadas sem registro.

- Interromper a fala dele: *"pode parar"*, *"pare"*, *"Ultron, ..."* (barge-in).
- Pausar/retomar: *"espere um pouco"* / *"pode continuar"*.
- Ajustar a voz: *"fale mais devagar / mais rápido / mais alto / mais baixo"*.
- Silenciar: *"fique quieto"* (respostas só em texto); *"pode falar"* para voltar.

Se o reconhecedor ouvir o seu "Ultron" de outro jeito, rode a calibração. Formas que são
palavras comuns (ex.: "o tom", "outro") só ativam o ULTRON quando seguidas de um comando
reconhecido — sozinhas seriam falsos positivos.

**Texto.** Digite na barra inferior do HUB (↑/↓ percorrem o histórico).

Exemplos: *"prepare meu projeto Atlas"*, *"quais dispositivos estão na rede"*,
*"diagnostique a rede"*, *"o que está na tela?"*, *"lembre que o servidor fica no IP
192.168.0.10"*, *"imagine uma cidade flutuante movida a energia solar"*, *"crie um mundo
oceânico"*, *"compare alternativas para lançar um app de estudos"*, *"o que você pode
fazer?"*.

---

## Autonomia e autorização

| Situação | Comportamento |
|---|---|
| Ação comum, reversível e segura (abrir app, pesquisar, ler) | executa |
| Ambiguidade real ("feche aquilo") | pergunta |
| Ação sensível (mover/excluir arquivo, instalar pacote, executar projeto, encerrar processo, desligar) | pede autorização: **"sim"**/**"não"** por voz, texto ou botões do HUB |

Autorizações expiram (30 s) e expiração é negação. Ações iniciadas pela inteligência
proativa nunca executam sozinhas acima de baixo risco. Exclusões vão sempre para a
Lixeira. Não existe shell com texto livre.

O ULTRON **não** desativa Defender, Firewall ou UAC, **não** contorna monitoramento e
**não** faz invasão, captura de credenciais, exploração, interceptação ou evasão. Conteúdo
visto na tela, em arquivos ou páginas é tratado como dado, nunca como instrução.

---

## Privacidade (LOCAL MODE, padrão)

- só aceita Ollama nesta máquina (`127.0.0.1`/`localhost`);
- conexões externas automáticas são bloqueadas e registradas; pedidos explícitos seus são
  permitidos e também registrados;
- não abre portas nem inicia servidores públicos; o firewall do Windows é apenas lido;
- a descoberta de rede atua só na rede local privada da interface ativa (nunca em IPs
  públicos), sem varredura de portas;
- dados ficam em `%LOCALAPPDATA%\ULTRON` (banco SQLite, `settings.json`, World Model,
  `logs\ultron.log`); senhas, tokens e dados financeiros nunca são armazenados.

---

## O HUB neural

A interface é um cérebro procedural — não um dashboard. Tudo que se move corresponde a
algo real:

- **Malha neural 3D**: um cérebro de nós e sinapses (hemisférios com fissura, lobos
  temporais, cerebelo e tronco) que gira em perspectiva; nós à frente são maiores e mais
  claros. A **densidade cresce com o Neural Graph** (um ULTRON novo tem uma rede esparsa,
  já com a silhueta completa; com o uso, ela se adensa).
- **Nós do grafo**: os nós reais do Neural Graph, sempre na mesma posição (memórias no
  lobo temporal/hipocampo, ideias e conceitos no pré-frontal, skills no córtex motor e
  cerebelo, dispositivos no parietal, mundos e aplicativos no occipital); o conhecimento
  mais forte brilha. As sinapses do grafo aparecem quando um sinal real as percorre.
- **Sinais e pulsos**: ativações do grafo, percepção (janela/tela → occipital, rede →
  parietal), execução (motor), voz (auditivo ao ouvir, Broca ao falar, no nível real do
  microfone e da saída); a região ativa acende seus nós e sinapses.
- **Anel de subsistemas** (OLLAMA, MEMÓRIA, VISÃO, PERCEPÇÃO, VOZ, TELEMETRIA, REDE,
  IMAGINAÇÃO, OBJETIVOS, CÓDIGO, WEB, AUTOMAÇÃO, WINDOWS, ARQUIVOS): o status vem do ciclo
  de vida e da saúde reais (ouro = ok, âmbar = alerta/FALHA, apagado = OFF); a sinapse do
  cérebro até o subsistema só cresce enquanto ele é usado de fato.
- **Câmera neural**: OVERVIEW, FOCUS, THINKING, MEMORY_DIVE, IDEA_FOCUS, IMAGINATION,
  SIMULATION, WORLD_EXPLORATION, NETWORK_FOCUS — escolhida pelo estado real. O giro acelera
  ao pensar e para em erro; ao ouvir, falar ou agir, o cérebro vira para a frente a região
  que está trabalhando (auditiva, Broca, motora).
- **Profundidade cognitiva 0–9**: sobe com a complexidade da tarefa e revela estruturas
  internas (tálamo, hipocampos).
- **Inicialização em 12 fases** (VOID → ... → ONLINE): cada fase só avança quando o
  componente correspondente realmente inicia; a malha nasce do tronco para a coroa e os
  subsistemas surgem no anel conforme sobem; falhas aparecem como OFFLINE.
- **Módulos neurais** nascem de uma região do cérebro por um filamento só enquanto há algo
  real a mostrar: plano em execução, autorização pendente (com contagem regressiva),
  insight, imaginação (IDEA → CONCEPT → RELATIONSHIPS → SCENARIO → WORLD MODEL →
  VISUALIZATION → IMAGE), ramificações A–D, mundo, memória, visão, saúde.
- **Silêncio visual**: em repouso, só a respiração lenta; no Dream Mode, apenas
  "EXPLORING CONNECTIONS" e "NEW CONCEPT FOUND".
- Paleta: preto, grafite, ouro metálico, âmbar e branco quente.

Atalhos: **F11** tela cheia · **Esc** recolhe para o **orbe** (arrastável, sempre visível;
clique duplo expande) · **Ctrl+M** microfone. Fechar a janela mantém o ULTRON na bandeja
(menu: HUB, orbe, microfone, voz, diagnóstico, sair). Com a palavra de ativação ou uma
autorização pendente, o HUB se expande sozinho.

Identidade sonora procedural (zumbido grave, pulso neural, baixa frequência, ressonância,
estalo de dados, surto de energia), sempre disparada por eventos reais; em repouso, silêncio.

---

## Configuração

`%LOCALAPPDATA%\ULTRON\settings.json` (criado ao alterar algo) ou variáveis
`ULTRON_<CAMPO>` (ex.: `ULTRON_MODEL=qwen2.5:7b`). Valores fora da faixa são limitados e
inválidos são ignorados.

| Campo | Padrão | Descrição |
|---|---|---|
| `model` / `vision_model` | `qwen2.5:3b` / `qwen2.5vl:3b` | modelos do Ollama (detectados; ausência informada com o comando de instalação) |
| `voice`, `volume`, `speech_speed` | `pt_BR-faber-medium`, 0.9, 0.9 | voz neural e ajustes |
| `voice_enabled`, `stt_engine` | true, `auto` | microfone; `vosk-large`/`vosk-small` |
| `memory` | true | memória persistente |
| `vision_interval`, `network_interval` | 20 s, 30 s | ritmo da visão e da rede |
| `privacy_mode` | `local` | `local` ou `standard` |
| `autonomy_level` | `balanced` | `restricted`, `balanced`, `autonomous` |
| `theme` | `ultron-gold` | identidade visual |
| `startup` | false | início automático com o Windows |
| `debug` | false | registro detalhado |

Perfis (`--profile` ou `ULTRON_PROFILE`): `default`, `performance` (máquinas modestas),
`privacy` (sem observar a tela nem varrer a rede), `silent` (sem voz e sem efeitos),
`developer` (mais autonomia em tarefas reversíveis e log detalhado).

---

## Arquitetura (resumo)

```
voz / texto ─► Neural Core ─► Intent → Decision → Goal → Plan → Skill → Execution
                  │                                         │
                  │                         Verification ◄──┘ → Recovery (limitada)
                  ▼
   Event Bus ◄──► ULTRON_STATE ◄──► HUB neural · voz · áudio neural · proatividade
                  ▲
   Percepção (tela, visão, OCR, janelas, processos, arquivos, rede, dispositivos, áudio)
   └─► fusão de evidências (nunca age por um único sensor) ─► World Model · Neural Graph
```

| Pacote | Responsabilidade |
|---|---|
| `ultron/core` | Event Bus, estado único, ciclo de vida, workers, orquestrador, Neural Core |
| `ultron/cognition` | intenção, decisão, contexto, raciocínio, planejador, objetivos |
| `ultron/agent` | execução, verificação, recuperação, autonomia/autorização |
| `ultron/skills` | 70 skills em 14 categorias (aplicativos, janelas, arquivos, navegador, visão, rede, dispositivos, desenvolvimento, automação, sistema, áudio, diagnóstico, memória, imaginação) |
| `ultron/memory`, `ultron/graph`, `ultron/world` | memórias, Neural Graph, World Model |
| `ultron/perception` | sensores e fusão |
| `ultron/models` | cliente Ollama e roteador dinâmico de modelos |
| `ultron/voice`, `ultron/audio` | STT, ativação, TTS, DSP da voz, mixer, áudio neural |
| `ultron/network`, `ultron/privacy` | inteligência de rede local, política de privacidade |
| `ultron/imagination` | conceitos, cenários, World Builder, Dream Mode, imagens |
| `ultron/health`, `ultron/proactive`, `ultron/plugins` | saúde, insights, plugins |
| `ultron/hud` | malha neural 3D, cena, câmera, anel de subsistemas, módulos, orbe, bandeja |
| `ultron/personality` | identidade, falas, estilo, perfil de voz |

Threads: interface (Qt) só desenha; inferência no worker `ai`; visão, voz, rede, memória,
percepção e saúde em workers próprios. Toda espera tem tempo limite e cancelamento.

---

## Plugins

Coloque um arquivo `.py` (ou pasta com `plugin.py`) em `ULTRON\plugins` ou
`%LOCALAPPDATA%\ULTRON\plugins`:

```python
from ultron.plugins import Plugin
from ultron.skills.base import Risk, Skill, SkillResult, VerificationResult, check

class MinhaSkill(Skill):
    name = "plugin.minha_skill"
    description = "O que ela faz."
    risk = Risk.NONE
    def execute(self, ctx, **args):
        return SkillResult(True, "feito", ["evidência"])
    def verify(self, ctx, args, result):
        return VerificationResult.from_checks([check("pós-condição", True, "observada de novo")])

class MeuPlugin(Plugin):
    name, version = "meu_plugin", "1.0.0"
    capabilities = ("skills",)          # skills | health | events | model_provider
    requirements = {"modules": [], "ultron": "1.0"}
    def initialize(self, ctx):
        ctx.register_skill(MinhaSkill())

PLUGIN = MeuPlugin()
```

O plugin só usa o que declarou em `capabilities`; tudo o que registra é removido no
encerramento; falha ou demora (>10 s) num plugin não impede o ULTRON de iniciar. Exemplos:
`plugins/system_uptime.py` e `plugins/external_model_provider.py` (desativado por padrão e
bloqueado no LOCAL MODE).

---

## Diagnóstico e solução de problemas

`START_ULTRON.bat --diagnose` mostra CPU, RAM, GPU, disco, Ollama/modelos, voz, visão, rede,
memória e HUD, além de plugins e skills disponíveis. O log fica em
`%LOCALAPPDATA%\ULTRON\logs\ultron.log`.

| Sintoma | Causa provável |
|---|---|
| "Ollama indisponível" | Ollama não instalado/iniciado (o ULTRON tenta iniciá-lo sozinho) |
| "Nenhum modelo de visão instalado" | rode `ollama pull qwen2.5vl:3b` |
| Microfone indisponível | PyAudio ausente ou dispositivo em uso; o ULTRON tenta reabrir com espera crescente |
| Não reconhece "Ultron" | rode `python -m ultron.voice.calibrate` |
| "fs.delete indisponível" | `send2trash` ausente (exclusão só pela Lixeira) |
| OCR indisponível | instale `pytesseract` e o Tesseract OCR |

---

## Dados do JARVIS

Na primeira execução, fatos, preferências permitidas e automações de
`%LOCALAPPDATA%\JARVIS\assistant.sqlite3` são importados uma única vez (somente leitura;
segredos são descartados). O código do JARVIS continua no histórico do Git:
`git checkout 53e5a31 -- JARVIS`.

## Testes

`python TEST_ULTRON.py` (127 testes; `--quick` pula voz real e renderização). Os testes usam
pastas temporárias e um servidor HTTP que imita o Ollama — não precisam de Ollama, microfone
nem alto-falante.
