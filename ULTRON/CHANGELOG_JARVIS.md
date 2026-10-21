# JARVIS — Registro de mudanças

Transformação do ULTRON em JARVIS, na ordem obrigatória das fases (A → I). Cada fase foi
testada antes do commit; os commits estão na branch `claude/adoring-brahmagupta-vcejpt`.

## Fase A — Auditoria (commit `1b4b8e2`)
* Mapa real dos subsistemas, testes existentes (131 OK em Python 3.13 e 3.11), inicialização
  real sem exceções. Relatório: `docs/JARVIS_AUDITORIA_E_PLANO.md`.
* Voz **medida**: o Vosk transcreve "Jarvis" como "aviso", "aves", "já vi", "davis";
  gramática restrita descartada (22/22 falsos positivos no modelo grande, 0/14 no pequeno).
* Linha de base de desempenho gravada (`docs/benchmarks/before_jarvis.json`).

## Fase B — Plano
* Prioridades P0 (voz, identidade, Event Bus), P1 (tema, TARDIS, desempenho, memória, rede),
  P2 (autonomia escopada, entrega). Preservar o que funciona; mudar só o necessário.

## Fase C — Estabilização (commits `369d368`, `e692875`)
* **Voz restaurada**: palavra de ativação "Jarvis" com formas medidas (fortes; nomes só no
  início; fracas só com comando reconhecido); formas do ULTRON migradas; calibração ao vivo.
* **Microfone**: PyAudio e, na falta ou falha, **sounddevice**; dispositivos que recusam 16 kHz
  abrem na taxa nativa com reamostragem (filtro FIR); silêncio absoluto detectado
  (privacidade do Windows); escolha de microfone na interface e no console.
* **Diagnóstico de voz em 8 etapas** (interface, `--voice-test`, `--diagnose`, "diagnóstico de
  voz"), que espera o modelo carregar e mostra evidência por etapa.
* Encerramento ordenado de fala e saída de áudio (threads com `join`).
* **Event Bus**: aviso de descarte agregado a cada 5 s (antes: uma linha de log por evento).
* Configurações v2 com migração da identidade ULTRON e cópia de segurança
  (`settings.ultron-backup.json`); variáveis `JARVIS_*` (aceita `ULTRON_*`).
* Pedidos de autorização citam o recurso exato (registro, quantidade, URL).

## Fase D — Desempenho (commit `a706c27`)
Medido com `tools/benchmark.py` (agora cobre TARDIS, perfis e orbe). Detalhes e números
finais em `PERFORMANCE_REPORT.md`.
* Causa do CORE "nunca em repouso": a verificação de saúde de rotina (a cada 15 s) fazia a
  sinapse de TELEMETRIA crescer e prendia o teto de quadros por ~4 s. Agora só mudanças reais
  de saúde animam (assinatura do quadro de problemas).
* Repouso com giro mais lento e cadência ociosa menor (Econômico 10, Equilibrado 15, Alto 24,
  Cinematográfico 40 quadros/s).
* Hub atrás do outro (CORE atrás do TARDIS e vice-versa) cai para a cadência de fundo.
* TARDIS: camada estrutural em cache (fundo, anéis, corredores, portais, textos), traços
  cosméticos de 1 px (caminho rápido do QPainter), marcas dos anéis giradas por
  transformação, desenho direto durante a viagem da câmera.
* Percepção relaxa os intervalos com o usuário ausente (> 5 min) e restaura ao voltar.

## Fase E — Identidade JARVIS (commits `369d368`, `329a37c`)
* Nome JARVIS em janelas, textos, mensagens, notificações, bandeja, voz, prompts e scripts;
  pacote `ultron`, pasta de dados e mutex preservados por compatibilidade.
* Personalidade: inteligente, serena, confiante, analítica, elegante, ligeiramente
  espirituosa e profissional; uma pergunta objetiva quando falta o essencial; nunca afirma
  execução sem verificação.
* Voz masculina, grave e natural (perfil JARVIS), mais inteligível que a anterior (medido).
* Tema único azul profundo/ciano com fonte única (`hud/palette.py` → `hud/theme.py`).
* Estados visuais ligados a sinais reais: repouso azul profundo, escuta (halo pelo nível do
  microfone), percepção (ondas por análise real), planejamento (conexões acesas conforme as
  etapas terminam), execução (pulsos das operações), memória (nós em azul), fala (anéis pelo
  nível da voz), imaginação (profundidade), erro (contorno fixo, sem alarme).
* Ícone novo em vários tamanhos.

## Fase F — TARDIS e memória pessoal (commits `e692875`, `a706c27`)
* **TARDIS**: câmara central (hoje), anéis concêntricos, corredores e portais com registros
  reais, partículas com orçamento, pulsos só para eventos reais, câmera com transição suave,
  painel lateral de consulta/edição, captura rápida, som ambiente opcional, volta ao CORE sem
  perder o estado.
* **Conflitos de agenda** informados (nunca bloqueados) na captura, edição, TARDIS e linha do
  tempo.
* **Exportação** JSON/CSV para arquivo novo; **backup** consistente diário com rotação;
  restauração segura só com o JARVIS fechado.
* Filtros de prioridade e período (30 dias, sem data) nas tarefas.

## Fase G — Rede local (commit `9b5aba1`)
* Observação honesta por aparelho (respondeu recentemente / inferido / conhecido antes / sem
  resposta / este computador), gateway, interface, primeira e última vez, origem e
  confiabilidade; desconhecido aparece como desconhecido.
* **Descobrir ≠ administrar**, explícito por aparelho e na tela.

## Fase H — Validação (commit `10b0ab6` e seguintes)
* **Autorização permanente escopada** ("sim, sempre" / SEMPRE 24 h): mesma ação + mesmo
  recurso + validade; nunca para sensível, crítico, irreversível ou proativo; revalidada a
  cada uso; revogável. Aba **AUTONOMIA** com histórico e registro de ações.
* Falhas de varredura de rede sempre registradas como limitação visível.
* Novos testes: memória pessoal completa, dois hubs com núcleo real, desempenho/cadência,
  identidade de estados, autorização escopada, integridade (todos os módulos importam),
  falha de rede, parada limpa por `--stop`.

## Fase I — Entrega
* `README_JARVIS.md`, `ARCHITECTURE_JARVIS.md`, `PERFORMANCE_REPORT.md`,
  `VOICE_DIAGNOSTICS.md`, `TEST_REPORT.md`.
* Scripts: `INSTALL_JARVIS.bat` (não apaga nada; copia modelos de uma instalação anterior só
  quando faltam), `START_JARVIS.bat` (`--status`, `--stop`, `--diagnose`, `--voice-test`,
  `--backup`…), `ATUALIZAR_JARVIS.bat` (para, faz backup, atualiza, diagnostica),
  `DIAGNOSTICO_JARVIS.bat` (componentes ausentes, saúde, voz, backups); `START_ULTRON.bat`,
  `INSTALL_ULTRON.bat` e `TEST_ULTRON.py` mantidos como atalhos de compatibilidade.
* `--status` e `--stop` (parada normal pedida à instância em execução, sem forçar).
* Dependências: `sounddevice` obrigatório (funciona sem PyAudio), `tzdata` no Windows.
* `JARVIS_FINAL.zip` sem `.venv`, caches, dados pessoais nem modelos grandes.
* `tools/build_release.py`: o pacote sai só de arquivos versionados no Git, é validado
  (conteúdo obrigatório, nada proibido, `.bat` em ASCII com CRLF, tamanho) e foi **testado depois
  de extraído** numa pasta nova.
* Esse teste encontrou um defeito: o diagnóstico de voz acusava "modelo ausente" quando os
  arquivos não estavam no disco, mesmo com o reconhecedor carregado e em uso. Agora a etapa 5
  confia primeiro no reconhecedor em uso; teste de regressão em `test_jarvis_voice.py`.

---

# JARVIS ULTIMATE — JARVIS original + TARDIS + Noctário

## Fases 1 e 2 — Auditoria e arquitetura (commit `a725f56`)
* `INVENTARIO_JARVIS_ORIGINAL.md` (e `docs/inventario/`): o que o JARVIS original tinha, o que
  funcionava, o que estava quebrado e o que precisava voltar. `ARQUITETURA_ULTIMATE.md` e
  `DESIGN_VISUAL.md`: módulos, protocolos, estados, identidades visuais.

## Fase 3, parte 1 — Recuperação do original no núcleo (commit `fb55f2d`)
* Observador (desligado ao iniciar, pausar/retomar), **modo privacidade** que fecha o microfone
  de verdade, automações do original reparadas (nomes antigos mapeados), personalidade do
  original, frases de encerramento, teclas e apelidos do original, mutex do original respeitado,
  `--autostart-check`, importação de modelos sem sobrescrever, **OpenAI** opcional (Responses
  API, chave no cofre do sistema, LOCAL MODE bloqueia, falha → Ollama), notas de sessão.

## Fase 3, parte 2 — Permissões, histórico e a plataforma (commits `bab7370` e seguinte)
* **Permissões por categoria** aplicadas pelo executor, com pisos (apagar dados e robô nunca
  abaixo de "confirmar") e parada de emergência sempre liberada.
* **Histórico de atividades** no mesmo banco (migração v4), alimentado pelo núcleo, pelo
  executor e pelos eventos; skills `activity.recent` e `activity.clear`.
* **Plataforma**: janela única com navegação F1–F7, páginas preservadas, transição
  holográfica, barra superior com estado e indicadores reais, conversa do original (horários,
  STATUS, HORAS, PARAR, COPIAR RESPOSTA, LIMPAR, Ctrl+L), Esc como no original, histórico ↑/↓
  com rascunho, ENVIAR.
* Páginas **ATIVIDADES**, **CONFIGURAÇÕES** e **DIAGNÓSTICOS** (console de eventos, log,
  serviços e GPU); TARDIS e Sistemas embutidos sem perder estado.
* Bandeja: Reiniciar voz, Modo privacidade, Observador (modos e pausa), Iniciar com o Windows.
* **Saída de áudio** selecionável; orbe lembra a posição; a interface informa quando cobre a
  tela (observação suspensa); "encerre o JARVIS" fecha a interface e o modo console;
  exceções não tratadas vão para o log.
* Testes: 263 aprovados em Python 3.13 e 3.11 (novos: permissões, histórico, plataforma).

## Fase 4 — Rosto holográfico, boca sincronizada, 12 estados e legendas
* `hud/avatar/`: geometria esculpida (NumPy; normais em repouso calculadas uma vez, só a parte de
  baixo recalculada quando a mandíbula abre), os 12 estados por sinais reais (função pura, prioridade
  da arquitetura), animador (cabeça, olhar, piscadas, expressões, montagem pelo progresso real do
  boot, pulsos de conexão/desconexão), renderização por camadas com QPainter (fundo em cache, grade
  3D, anéis de dados, partículas, varredura, brilho em NumPy) e widget CPU ou GPU (QOpenGLWidget com
  o mesmo desenho; volta para a CPU com o motivo).
* `voice/lipsync.py`: visemas pelos fonemas do Piper sobre os trechos sonoros do áudio real
  (alinhamento do modelo quando existir; espectro quando não há fonemas); abertura pela energia real.
* `Speaker`: síntese por frase com fonemas; `mouth()`, `caption()` e `audible()` pela posição real de
  reprodução; interromper fecha a boca no mesmo quadro. Indicador "reconhecendo" na voz.
* Indicador de estado da barra superior = estado resolvido do avatar.
* Otimização medida: traços longos com caneta de 1 px (o caminho rápido do QPainter) — 21–29 ms →
  11–15 ms por quadro no perfil equilibrado a 1280×760.
* `tools/benchmark_avatar.py` e `docs/benchmarks/avatar_fase4.json`.
* Testes: `test_avatar.py` (12) e `test_lipsync.py` (8, inclusive com a voz Piper real quando
  instalada).

