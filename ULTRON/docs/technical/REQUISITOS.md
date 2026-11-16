# Requisitos do SAFRA

Especificação dos requisitos do SAFRA no escopo do TCC (ver `AUDITORIA_INICIAL.md` §11). Os requisitos
foram **levantados do sistema existente** (engenharia reversa do código, dos testes e da documentação) e
complementados pelos objetivos da fase SAFRA. A estrutura segue as recomendações gerais da ISO/IEC/IEEE
29148 para requisitos (identificador único, enunciado verificável, prioridade, critério de aceitação e
rastreabilidade).

* **Prioridade** (MoSCoW): **E** essencial · **D** desejável · **O** opcional.
* **Situação** (ao fim da fase SAFRA, 11/2026) remete ao `INVENTARIO_FUNCIONALIDADES.md`: ✔ atendido com
  evidência · ◐ parcial · ? não verificado · ○ planejado.
* **Verificação** indica o teste automatizado (arquivo em `tests/`) ou o protocolo experimental
  (`docs/research/PROTOCOLOS_DE_VALIDACAO.md`, códigos `PV-xx`).

Fora do escopo: controle de robôs ou de qualquer dispositivo físico (o módulo NOCTARIO foi descontinuado),
treinamento de modelos de IA, execução em sistemas operacionais além do Windows 10/11 como alvo de uso
(o Linux é usado como ambiente de desenvolvimento e de testes).

---

## 1. Requisitos funcionais

### 1.1 Núcleo e processamento de comandos

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF01 | O sistema deve receber pedidos por texto (interface gráfica e modo console) e por voz, entregando-os a um único núcleo de processamento. | E | ✔ | `test_core`, `test_cli` |
| RF02 | O sistema deve reconhecer comandos em português por regras determinísticas, sem depender de modelo de linguagem. | E | ✔ | `test_core`, `test_original_recovery` |
| RF03 | Pedidos não reconhecidos pelas regras devem ser respondidos por um modelo de linguagem executado localmente (Ollama). | E | ✔ (com dublê) | `test_model_router`, PV-02 |
| RF04 | O modelo de linguagem só pode acionar ferramentas oferecidas explicitamente para o pedido corrente. | E | ✔ | `test_security` |
| RF05 | Cada resposta deve informar a sua procedência (memória, ação verificada, modelo local, modelo na nuvem, inferência). | E | ✔ | `test_intelligence` |
| RF06 | O usuário deve poder cancelar o pedido em andamento por voz, texto ou botão, inclusive com o modelo ainda carregando. | E | ✔ | `test_model_router`, `test_transitions` |
| RF07 | O uso de um modelo pago na nuvem deve ser opcional, desligado por padrão, com autorização no primeiro uso e limite mensal de gasto. | D | ✔ (com dublê) | `test_intelligence`, `test_openai_provider` |

### 1.2 Interação por voz

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF08 | O sistema deve reconhecer fala em português sem conexão com a internet. | E | ✔ (fala sintetizada) / ? (voz humana) | `test_voice`, PV-01 |
| RF09 | O sistema deve ser ativado por voz pela palavra **"Safra"** no início da frase, mantendo **"Jarvis"** como forma aceita para compatibilidade. | E | ◐ implementado; reconhecimento abaixo da meta com voz sintética (PV-01) | `test_voice`, PV-01 |
| RF10 | Após uma interação, o usuário deve poder continuar falando por alguns segundos sem repetir a palavra de ativação. | D | ✔ | `test_voice` |
| RF11 | O sistema deve responder por voz sintetizada localmente em português, com perfil de voz próprio. | E | ✔ | `test_jarvis_voice`, `test_voice_prosody` |
| RF12 | A síntese deve tratar números, horas, valores, siglas e endereços para leitura natural (prosódia). | D | ✔ | `test_voice_prosody` |
| RF13 | O sistema não deve reagir à própria fala (sem autoescuta) e deve permitir interrupção ("pare"). | E | ✔ | `test_voice` |
| RF14 | O sistema deve oferecer um diagnóstico de voz por etapas, do microfone até a fala reproduzida. | D | ✔ (etapas lógicas) | `test_voice`, `test_cli` |

### 1.3 Memória persistente

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF15 | O sistema deve guardar episódios, fatos, procedimentos e preferências num banco local persistente. | E | ✔ | `test_memory` |
| RF16 | O sistema deve recuperar memórias relevantes para compor o contexto de cada pedido. | E | ◐ lexical 100 %, paráfrase 45 % (PV-03) | `test_memory`, PV-03 |
| RF17 | O usuário deve poder registrar compromissos, lembretes e anotações por voz ou texto, e consultá-los em português. | E | ✔ | `test_second_brain` |
| RF18 | Respostas sobre a memória pessoal devem usar **somente** registros salvos; sem registro, o sistema deve dizer que não encontrou. | E | ✔ | `test_second_brain` |
| RF19 | Lembretes devem disparar no horário, sem duplicação, e lembretes perdidos com o programa fechado devem ser avisados uma vez. | E | ✔ | `test_second_brain` |
| RF20 | O sistema deve permitir backup, restauração e exportação dos dados sem sobrescrever cópias anteriores. | E | ✔ | `test_cli`, `test_failures` |

### 1.4 Interface humanoide e sincronização labial

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF21 | A interface deve apresentar um holograma humanoide 3D animado conforme o estado real do sistema (repouso, escutando, pensando, executando, falando, alerta, erro). | E | ✔ (WebGL por software) | `test_scene3d`, `test_avatar`, PV-04 |
| RF22 | A boca do holograma deve acompanhar o áudio real da fala, fechando no silêncio. | E | ✔ (funcional) / ? (atraso medido) | `test_lipsync`, PV-05 |
| RF23 | A interface deve exibir a conversa, as autorizações pendentes, o histórico de atividades, as configurações e os diagnósticos. | E | ✔ | `test_platform` |
| RF24 | Na falta de WebGL, a interface deve passar para uma vista 2D sem perder funções, registrando o motivo. | E | ✔ | CI Windows, `test_scene3d` |
| RF25 | A identidade visual deve ser a do SAFRA (vermelho, bordô, preto/grafite), definida numa fonte única de tokens usada pelo Qt, pela cena 3D e pela web. | E | ✔ (fase SAFRA) | `test_scene3d.DesignTokensTest` |

### 1.5 Ambiente virtual TARDIS

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF26 | O sistema deve executar tarefas de análise (diagnóstico, telemetria, organização, planejamento sem execução) numa fila própria com prazos e cancelamento. | E | ✔ | `test_tardis_logic` |
| RF27 | A sala de controle 3D deve refletir o modo e as tarefas reais do motor da TARDIS (rotor, painéis). | E | ✔ (WebGL por software) | `test_tardis_room`, `test_scene3d` |
| RF28 | A telemetria exibida deve conter apenas métricas medidas do próprio sistema. | E | ✔ | `test_tardis_logic` |

### 1.6 Execução e segurança

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF29 | Toda ação deve passar por um único executor que valida argumentos, aplica permissões, pede autorização quando necessário, executa com prazo e registra o resultado. | E | ✔ | `test_executor` |
| RF30 | O usuário deve poder definir, por categoria (consultar, configurar, executar programas, arquivos, apagar dados), se a ação é permitida, confirmada ou bloqueada. | E | ✔ | `test_permissions` |
| RF31 | O sistema deve verificar o efeito de cada ação e diferenciar "verificado", "sem confirmação independente", "negado" e "falhou". | E | ✔ | `test_verifier`, `test_transitions` |
| RF32 | Toda ação deve ficar registrada no histórico de atividades e na auditoria. | E | ✔ | `test_activity` |
| RF33 | Uma identidade alternativa (Protocolo ULTRON) deve poder ser ativada e restaurada a qualquer momento, sem criar outro núcleo, outra memória ou outro executor. | O | ✔ | `test_ultron_protocol` |

### 1.7 Diagnóstico e operação

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RF34 | O sistema deve oferecer diagnóstico pela linha de comando e pela interface (componentes ausentes, saúde, voz). | E | ✔ | `test_cli`, `test_startup` |
| RF35 | O sistema deve funcionar em modo console quando a interface gráfica não estiver disponível. | E | ✔ | `test_cli`, CI Windows |
| RF36 | O sistema deve impedir duas instâncias simultâneas e oferecer `--status` e `--stop`. | E | ✔ | `test_integrity`, `test_cli` |
| RF37 | O sistema deve permitir acesso remoto ao MESMO núcleo por um navegador pareado, sem abrir portas no computador. | O | ✔ (local) | `test_web_orb` |

---

## 2. Requisitos não funcionais

Os valores-alvo abaixo são **metas de avaliação** do TCC, não resultados. Os resultados medidos ficam em
`docs/research/resultados/` e no capítulo de resultados.

| ID | Categoria | Requisito | Meta (critério de aceitação) | Verificação |
|---|---|---|---|---|
| RNF01 | Desempenho | Resposta a comandos determinísticos (sem modelo) | p95 ≤ 1,0 s do fim do pedido à resposta publicada | PV-02 |
| RNF02 | Desempenho | Resposta com o modelo local (`qwen2.5:3b`) a perguntas curtas | registrar p50/p95 no computador de referência; meta p50 ≤ 8 s | PV-02 |
| RNF03 | Desempenho | Inicialização até a interface pronta | ≤ 15 s no computador de referência | PV-04 |
| RNF04 | Desempenho | Cena 3D pronta e taxa de quadros | pronta ≤ 5 s; ≥ 30 quadros/s no perfil Equilibrado com GPU | PV-04 |
| RNF05 | Desempenho | Uso de CPU em repouso com a interface aberta | ≤ 25 % (registrado junto com o modelo do processador) | PV-04, `tools/benchmark.py` |
| RNF06 | Usabilidade da voz | Taxa de acerto da palavra de ativação | ≥ 90 % das ativações intencionais | PV-01 |
| RNF07 | Usabilidade da voz | Ativações falsas | ≤ 2 % das frases sem a palavra de ativação | PV-01 |
| RNF08 | Sincronização | Atraso entre áudio e boca | dentro da faixa de não percepção da ITU-R BT.1359 (som adiantado ≤ 45 ms; atrasado ≤ 125 ms) | PV-05 |
| RNF09 | Memória | Recuperação correta | ≥ 80 % de acerto entre as 3 primeiras memórias recuperadas para o conjunto de teste | PV-03 |
| RNF10 | Confiabilidade | Execução prolongada | 8 h sem falha fatal; crescimento de memória ≤ 20 MB/h; nenhuma thread restante ao encerrar | PV-07, `test_tardis` |
| RNF11 | Confiabilidade | Isolamento de falhas | falha de um módulo periférico (voz, modelo, cena 3D, sensor) não interrompe o núcleo | `test_failures`, `test_transitions` |
| RNF12 | Portabilidade | Plataformas | Windows 10/11 64 bits (alvo); Python 3.11 e 3.13 | CI |
| RNF13 | Operação local | Funcionamento sem internet | todas as funções essenciais (RF01–RF36) operam sem internet | PV-06 |
| RNF14 | Manutenibilidade | Testes automatizados | suíte completa aprovada em cada commit do CI; cobertura de linhas ≥ 70 % | CI, `coverage` |
| RNF15 | Manutenibilidade | Fonte única de identidade visual | nenhuma cor da identidade fora dos tokens nos módulos de tema | `DesignTokensTest` |
| RNF16 | Acessibilidade visual | Contraste do texto principal | ≥ 4,5:1 sobre o fundo (WCAG 2.1, nível AA) | teste de contraste dos tokens |

## 3. Requisitos de segurança

| ID | Requisito | Prior. | Situação | Verificação |
|---|---|---|---|---|
| RS01 | O código não deve executar comandos por shell, `eval`, `exec`, `os.system` ou desserializar `pickle`. | E | ✔ | `test_security` (varredura) |
| RS02 | Pastas do sistema, da inicialização automática, do programa e dos dados devem ser recusadas como alvo **antes** de qualquer pedido de autorização, inclusive por link simbólico. | E | ✔ | `test_security` |
| RS03 | Exclusões devem ir para a Lixeira; cópias de segurança nunca podem ser sobrescritas. | E | ✔ | `test_security` |
| RS04 | Senhas, tokens, dados financeiros e de autenticação devem ser recusados antes de qualquer gravação em memória. | E | ✔ | `test_memory`, `test_second_brain` |
| RS05 | Credenciais de serviços externos devem ficar apenas no cofre do sistema operacional, nunca em arquivos de configuração ou registros. | E | ✔ (cofre simulado) | `test_security` |
| RS06 | Conteúdo lido da tela, de arquivos ou de páginas deve entrar no contexto do modelo como **dado**, nunca como instrução. | E | ✔ | `test_security` |
| RS07 | Autorizações expiradas devem ser tratadas como negadas; autorizações permanentes devem ser escopadas (ação + recurso + validade) e nunca valer para ações sensíveis, críticas, irreversíveis ou de origem proativa. | E | ✔ | `test_executor` |
| RS08 | A cena 3D não pode acessar a rede nem recursos externos; só pode enviar ao núcleo pedidos de uma lista branca. | E | ✔ | `test_scene3d` |
| RS09 | O sistema não deve desativar proteções do sistema operacional (UAC, antivírus, firewall) nem alterar o registro além da entrada opcional de início automático. | E | ✔ (varredura) | `test_security` |
| RS10 | O acesso remoto deve exigir pareamento confirmado no computador, sessão revogável, HTTPS/WSS, verificação de origem, CSRF e limites de tentativas; ações sensíveis só podem ser confirmadas no computador. | O | ✔ (local) | `test_web_orb` |
| RS11 | A rede local só pode ser observada por meios passivos e legítimos (sem varredura de portas, exploração ou interceptação). | E | ✔ | `test_security`, `test_network` |

## 4. Restrições técnicas

| ID | Restrição | Justificativa |
|---|---|---|
| RT01 | Execução local em um computador pessoal com Windows 10/11 64 bits | público-alvo e privacidade |
| RT02 | Modelos de IA executados localmente (Ollama, Vosk, Piper); nuvem apenas opcional | operação sem internet e sem custo recorrente |
| RT03 | Python 3.11 como versão de instalação; 3.13 testado | compatibilidade das bibliotecas de voz e Qt |
| RT04 | Qt 6.8 (PySide6 `>=6.8.1,<6.9`) | série testada; a 6.12 quebrava o projeto |
| RT05 | Um único banco SQLite; nenhum banco paralelo | consistência e backup simples |
| RT06 | Identificadores internos `ultron` preservados | compatibilidade com instalações e dados existentes |
| RT07 | Sem hardware dedicado (robôs, sensores externos) | decisão de escopo |
| RT08 | Áudio protegido por direitos autorais não é distribuído; efeitos sonoros são originais | direitos autorais |

## 5. Critérios de aceitação do protótipo (para o TCC)

O protótipo será considerado **aceito** para defesa quando:

1. **CA01** — a suíte automatizada completa estiver aprovada no CI (Linux 3.11/3.13 e Windows) no commit
   entregue;
2. **CA02** — todos os requisitos essenciais (prioridade E) estiverem com situação ✔ ou com a limitação
   explicitamente documentada no capítulo de resultados;
3. **CA03** — os protocolos PV-01 a PV-07 tiverem sido executados no computador de referência, com os
   dados brutos versionados em `docs/research/resultados/`;
4. **CA04** — cada meta de RNF tiver um resultado registrado (atingida, não atingida ou não medida, com
   o motivo);
5. **CA05** — a instalação a partir do pacote ZIP funcionar num Windows limpo seguindo apenas o
   `README_JARVIS.md`.

## 6. Matriz de rastreabilidade (objetivos → requisitos)

| Objetivo específico (TCC) | Requisitos |
|---|---|
| OE1 Projetar a arquitetura modular | RNF11, RNF14, RT05, RF29 |
| OE2 Integrar o núcleo inteligente e o processamento de comandos | RF01–RF07 |
| OE3 Implementar memória persistente | RF15–RF20, RS04, RNF09 |
| OE4 Desenvolver a interação por voz | RF08–RF14, RNF06–RNF07 |
| OE5 Desenvolver a interface humanoide com sincronização labial | RF21–RF25, RNF04, RNF08, RNF16 |
| OE6 Desenvolver o ambiente virtual TARDIS | RF26–RF28 |
| OE7 Estabelecer mecanismos de segurança e permissões | RF29–RF33, RS01–RS11 |
| OE8 Garantir diagnóstico, desempenho e confiabilidade | RF34–RF36, RNF01–RNF05, RNF10–RNF13 |
| OE9 Testar e avaliar os resultados | CA01–CA05 |
