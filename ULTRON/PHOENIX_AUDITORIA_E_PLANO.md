# Operação Phoenix — auditoria inicial e plano técnico

## 1. Estado do repositório (conferido antes de qualquer mudança)

* Branch de trabalho: `claude/adoring-brahmagupta-vcejpt` (é a branch desta sessão de desenvolvimento);
  commit inicial da Phoenix: `34f1fa0`; árvore limpa e sincronizada com `origin`.
* `main` (`53e5a31`) não tem nada além do que esta branch já contém (82 commits à frente, 0 atrás). **Nenhum
  merge na `main` é feito por esta operação.**
* Branches de segurança existentes, **não tocadas**: `safety/backup-before-phase-7-8-20261029`,
  `work/phase-7-8-safe-release`.
* As imagens citadas no pedido ("imagens anexadas") **não chegaram** a esta sessão; a auditoria visual usa o
  código e as capturas já registradas em `docs/capturas/`.

## 2. O que existe hoje (e é preservado)

| Peça | Onde | Observação |
|---|---|---|
| Um NeuralCore | `ultron/core/neural_core.py` | orquestra percepção, intenção, planejamento, execução, verificação, voz |
| Uma memória / um banco | `ultron/memory/` (SQLite com migrações em `store.py`) | memória pessoal, Second Brain, TARDIS, atividades |
| Um Event Bus | `ultron/core/event_bus.py` | publicação assíncrona com estatísticas |
| Um executor e uma autorização | `ultron/agent/execution.py`, `autonomy.py`, `permissions.py` | risco + categorias + pedidos de confirmação |
| Uma fonte de estado | `ultron/core/state.py` | `JARVIS_STATE` com versão |
| Roteador de modelos | `ultron/models/router.py` | Ollama local; OpenAI só quando o usuário escolhe `ai_provider=openai` e a privacidade permite |
| Central 3D | `ultron/hud/scene3d/` (Three.js r170 no QtWebEngine) | holograma, ORBE (vista NÚCLEO), cabine e sala da TARDIS; reserva 2D automática |
| ORBE compacto | `ultron/hud/orb.py` | janela flutuante **2D** (cérebro em miniatura) |

## 3. Lacunas encontradas para a Phoenix

**Visual.** O holograma de corpo inteiro ainda tem aspecto de manequim: rosto simples (o mesmo perfil da
cabeça 2D), malha de anéis horizontais densa, sem camadas de circuito, sem vista lateral. A TARDIS 3D está boa
mas pode ganhar detalhe (cabine e rotor). O ORBE minimizado ainda é o desenho 2D.

**Inteligência.** O roteador não avalia a tarefa: usa o modelo configurado (texto/visão) ou a OpenAI quando
escolhida. Não há perfis (LOCAL/HÍBRIDO/AVANÇADO/ECONÔMICO/PRIVACIDADE), contabilidade de custo, limite de
gasto, nem autorização no **primeiro uso pago**. As respostas não marcam a procedência (memória, internet,
inferência). Defeito conhecido da auditoria anterior: perguntas gerais à memória sem tema ("quais ideias
salvei?") respondem "não encontrei".

**Rede.** Não existe acesso remoto. O módulo `ultron/network` é o inventário da rede LOCAL (não confundir).

**Noctário.** Integrado em 30+ arquivos (UI, núcleo, intenções, permissões, configurações, TARDIS, CI,
firmware). Removido nesta fase — ver `REMOCAO_NOCTARIO.md`.

## 4. Plano técnico por fase (cada uma com testes executados antes de ser dada como concluída)

**A — Auditoria e estabilização.** Este documento; remoção do Noctário com manifesto; TELEMETRIA da TARDIS
passa a medir o próprio JARVIS.

**B — Experiência visual.**
* Avatar: cabeça nova de androide (rosto com planos definidos, órbitas, nariz, lábios, mandíbula, "gema" na
  testa), corpo com seções anatômicas, linhas que seguem a anatomia (contornos de músculo, circuitos), camadas
  (casca Fresnel, linhas, circuitos, nós, esqueleto) e vistas FRENTE/LATERAL.
* TARDIS: mais detalhe na cabine e no rotor, mantendo os painéis reais.
* ORBE minimizado: **a mesma cena 3D** (um motor) é emprestada à janela flutuante, num modo compacto que desenha
  só o núcleo; janela redonda por máscara (sem depender de transparência do sistema), arrastar, duplo clique,
  menu, posição por monitor; sem WebGL, volta o orbe 2D atual.
* Design system: tokens comuns (cores, tipografia, estados) para desktop, cena 3D e web.

**C — Protocolo ULTRON.** Lógica pura (`ultron/hud/ultron_protocol.py`): ativação manual por frase, ocasional
(probabilidade, intervalo mínimo, só em repouso, nunca com autorização pendente/execução/gravação), saída por
frase, botão, Esc ou tempo; histórico. Só muda **apresentação** (cena 3D, barra, ORBE, mensagens fictícias
rotuladas); nenhuma permissão, comando, arquivo ou credencial é tocado — com testes que provam isso.

**D — Inteligência.** Perfis de inteligência no roteador; classificação da tarefa (simples, raciocínio,
visão, planejamento) para escolher o modelo; provedores por interface comum; contabilidade de tokens e custo
no **mesmo banco** (tabela nova via migração), limite mensal, autorização antes do primeiro uso pago;
procedência nas respostas; melhoria da recuperação da memória (perguntas gerais e relações entre projetos).

**E — JARVIS Network.**
* Gateway (`gateway/`, serviço separado, Python + aiohttp): contas com senha em **scrypt**, sessões com cookie
  HttpOnly/Secure/SameSite, CSRF, limite de tentativas, TOTP opcional, dispositivos, pareamento por código de
  uso único, WebSocket, auditoria; banco próprio do gateway (contas, dispositivos, sessões, metadados) —
  **nunca** a memória pessoal.
* Agente local (`ultron/remote/`): conexão de **saída** HTTPS/WSS para o gateway (nenhuma porta aberta no
  roteador), usa o MESMO NeuralCore e o MESMO sistema de autorização; só operações de uma lista fechada.
* Web responsiva (desktop e celular) reaproveitando os módulos 3D (holograma e ORBE).

**F — Publicação.** Auditoria de segredos e dependências, Dockerfile, compose, `.env.example`, health checks,
migrações, CI, guia de deploy/domínio/HTTPS, rollback. **Publicar exige hospedagem e domínio do proprietário**
— sem essas credenciais, a entrega fica pronta para deploy e diz exatamente o que falta.
