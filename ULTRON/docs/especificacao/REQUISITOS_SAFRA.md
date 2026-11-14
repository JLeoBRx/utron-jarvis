# Requisitos do SAFRA — novo escopo

Especificação da Fase 2. Substitui `../technical/REQUISITOS.md` (fase anterior) quando a migração terminar; até
lá aquele documento descreve o sistema que está no ar. As metas dos requisitos não funcionais são **metas de
avaliação**, não resultados.

**Colunas.** *P*: prioridade — E essencial, D desejável, O opcional. *Origem*: identificador no documento
anterior, ou "novo". *Hoje*: ✔ existe e tem teste · ◐ existe e precisa ser adaptado · ○ a construir.
*Verificação*: como o requisito será conferido (tipos de teste na seção 7).

## 1. Requisitos funcionais

### 1.1 Interação por texto e voz

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-01 | Pedidos por texto (interface, painel, console) e por voz chegam a um único núcleo | E | RF01 | ◐ | integração: o mesmo pedido pelas quatro entradas gera a mesma atividade |
| RF-02 | Comandos em português são reconhecidos por regras determinísticas, sem modelo de linguagem | E | RF02 | ✔ | unitário (existente) |
| RF-03 | Pedidos não reconhecidos pelas regras são respondidos por modelo executado localmente | E | RF03 | ✔ | integração com modelo simulado; medição com modelo real no PC de referência |
| RF-04 | O modelo só aciona ferramentas oferecidas para o pedido corrente | E | RF04 | ✔ | unitário (existente) |
| RF-05 | Cada resposta informa a procedência (memória, ação verificada, modelo local, nuvem, inferência) | E | RF05 | ✔ | unitário; contrato (campo `provenance`) |
| RF-06 | O pedido em andamento pode ser cancelado por voz, texto, botão ou parada de emergência | E | RF06 | ◐ | integração pela API |
| RF-07 | Modelo pago na nuvem é opcional, desligado por padrão, com autorização no primeiro uso e limite mensal | D | RF07 | ✔ | unitário com provedor simulado |
| RF-08 | A fala em português é reconhecida sem internet | E | RF08 | ✔ | fala sintetizada (existente); voz humana no PC de referência |
| RF-09 | A ativação por voz usa **somente** a palavra "Safra" | E | RF09 (alterado) | ◐ | unitário: "jarvis" não ativa; PV-01 e PV-01B |
| RF-10 | Uma tecla de atalho global abre a janela de escuta; repetir ou `Esc` cancela; conflito de tecla é informado | E | novo | ○ | unitário (registro e mensagem simulada); CI Windows; teclado real no roteiro de validação |
| RF-11 | Depois de uma interação, o usuário pode continuar falando por alguns segundos sem repetir a ativação | D | RF10 | ✔ | unitário (existente) |
| RF-12 | A resposta é falada por síntese local em português, com perfil de voz próprio | E | RF11 | ✔ | unitário e fala sintetizada |
| RF-13 | Números, horas, valores, siglas e endereços são tratados para leitura natural | D | RF12 | ✔ | unitário (existente) |
| RF-14 | O sistema não reage à própria fala e aceita interrupção | E | RF13 | ✔ | unitário (existente) |
| RF-15 | Há diagnóstico de voz por etapas, do microfone à fala reproduzida | D | RF14 | ✔ | unitário; rota `/voice/diagnostics` |
| RF-16 | O nível da voz falada (energia do áudio real) é publicado para a interface | D | RF22 (substitui) | ◐ | unitário: silêncio dá nível zero; evento `voice.level` |

### 1.2 Memória e projetos

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-17 | Episódios, fatos, procedimentos e preferências ficam num banco local persistente | E | RF15 | ✔ | unitário (existente) |
| RF-18 | Memórias relevantes são recuperadas para o contexto de cada pedido | E | RF16 | ◐ | PV-03 (hoje: lexical 100 %, paráfrase 45 %) |
| RF-19 | Compromissos, lembretes e anotações podem ser registrados e consultados por voz, texto e interface | E | RF17 | ✔ | unitário; funcional |
| RF-20 | Respostas sobre a memória pessoal usam só registros salvos; sem registro, o sistema diz que não sabe | E | RF18 | ✔ | unitário (existente) |
| RF-21 | Lembretes disparam no horário, sem duplicação; os perdidos com o programa fechado são avisados | E | RF19 | ✔ | unitário (existente) |
| RF-22 | Backup, restauração e exportação não sobrescrevem cópias anteriores | E | RF20 | ✔ | unitário; integração |
| RF-23 | O usuário cria, edita e arquiva **projetos** e liga a cada um notas, registros de memória, tarefas de análise e atividades; consulta tudo de um projeto num só lugar | E | novo (parcial) | ○ | unitário; contrato; funcional |
| RF-24 | Projetos existentes (nomes já usados em notas e registros do tipo "projeto") aparecem como projetos depois da migração | E | novo | ○ | teste de atualização |

### 1.3 Análises

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-25 | Tarefas de análise (consulta, planejamento, organização, rotinas, telemetria, diagnóstico, coordenação, projeto) rodam numa fila com prazo, cancelamento e persistência | E | RF26 | ◐ | 37 testes existentes, renomeados |
| RF-26 | Uma análise nunca executa ações: devolve ações propostas, que só rodam com a confirmação do usuário pelo executor | E | RF26 | ✔ | unitário (existente) |
| RF-27 | A telemetria mostrada contém só métricas medidas do próprio sistema | E | RF28 | ✔ | unitário (existente) |
| RF-28 | Cada resultado informa o modelo usado ou "sem modelo: análise determinística" | E | RF26 | ✔ | unitário (existente) |

### 1.4 Habilidades, permissões e execução

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-29 | Toda ação passa por um único executor que valida argumentos, aplica permissões, pede autorização, respeita prazo e registra | E | RF29 | ✔ | unitário; PV-06 |
| RF-30 | O usuário define por categoria (consultar, configurar, executar programas, arquivos, apagar dados) se a ação é permitida, confirmada ou bloqueada | E | RF30 | ✔ | unitário (existente) |
| RF-31 | Operações sensíveis pedem confirmação com descrição, risco, reversibilidade e prazo; expirar equivale a negar | E | RF29, RS07 | ✔ | unitário; contrato |
| RF-32 | O efeito de cada ação é verificado e classificado: verificado, sem confirmação independente, negado, falhou | E | RF31 | ✔ | unitário (existente) |
| RF-33 | Toda ação fica no histórico de atividades e na auditoria, com a origem e a sessão | E | RF32 | ◐ | integração pela API |
| RF-34 | **Modo Operador**: o usuário pode ampliar a autonomia para rotinas liberadas, só a partir do computador principal, com prazo, rótulo permanente na tela e os pisos de segurança; a parada de emergência o encerra | O | RF33 (alterado) | ◐ | testes de permissões sob o perfil (existentes, adaptados) |
| RF-35 | As habilidades são listadas com categoria, risco, disponibilidade e a dependência que falta | D | novo | ◐ | contrato (`/skills`) |
| RF-36 | Plugins do usuário continuam carregando, inclusive os escritos para os nomes de pacote antigos | D | existente | ✔ | unitário com plugin de exemplo antigo |
| RF-37 | Um pedido com efeito, repetido com a mesma chave, não repete o efeito | E | novo | ○ | contrato (idempotência) |

### 1.5 Interface

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-38 | Uma única interface atende o desktop e o painel web, usando só o contrato v1 | E | novo | ○ | a mesma bateria funcional na casca e no navegador |
| RF-39 | **Modo Cotidiano**: símbolo, conversa, entrada de texto e voz, e o que pede atenção (autorização, lembretes, falhas) | E | novo | ○ | funcional |
| RF-40 | **Central de Comando**: visão geral, atividades, memória, projetos, análises, habilidades, voz, saúde, rede e configurações | E | RF23 (substitui) | ○ | funcional; lista de paridade |
| RF-41 | O assistente é representado por um **símbolo abstrato** em 2D/2.5D, sem rosto, cujos estados vêm só do estado real do núcleo | E | RF21 (substitui) | ○ | componente: cada estado do núcleo mapeia para um estado visual; nenhum estado sem origem |
| RF-42 | A autorização pendente aparece em qualquer tela, com descrição, risco, reversibilidade e tempo restante | E | RF23 | ◐ | funcional |
| RF-43 | Toda tela tem estados de carregamento, vazio, erro e "sem conexão com o núcleo"; dado antigo nunca é mostrado como atual | E | novo | ○ | componente; injeção de falhas |
| RF-44 | A casca oferece janela principal, ícone na bandeja e janela compacta com o símbolo | E | existente | ◐ | integração; Windows real |
| RF-45 | Lembretes, autorizações e falhas geram notificação na interface e aviso nativo | D | existente | ◐ | integração; Windows real |
| RF-46 | A interface é utilizável de 360 px de largura a telas largas, por teclado e por toque, e respeita a preferência de movimento reduzido | E | novo | ○ | funcional em três larguras |
| RF-47 | A identidade visual vem de uma fonte única de *tokens* | E | RF25 | ◐ | teste: nenhuma cor fora dos *tokens* |

### 1.6 API e sessões

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-48 | O núcleo oferece a API local do contrato v1 (HTTP e WebSocket) | E | novo | ○ | contrato |
| RF-49 | A casca entra por bilhete de uso único; o navegador, por código de uso único; sessões são listadas e revogáveis | E | novo | ○ | segurança |
| RF-50 | O painel funciona no navegador do próprio computador | E | RF37 (adaptado) | ○ | funcional |
| RF-51 | O painel é acessível de outros dispositivos pelo retransmissor, por conexão de saída e pareamento confirmado no computador | O | RF37 | ○ (posterior) | fora desta migração |

### 1.7 Sistema, instalação e dados

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RF-52 | Diagnóstico pela linha de comando e pela interface | E | RF34 | ◐ | unitário; contrato |
| RF-53 | O sistema funciona em modo console quando não há interface | E | RF35 | ✔ | unitário (existente) |
| RF-54 | Duas instâncias simultâneas são impedidas; `--status` e `--stop` funcionam | E | RF36 | ✔ | unitário; versão antiga e nova não rodam juntas |
| RF-55 | Monitor de saúde e métricas de desempenho ficam disponíveis na Central de Comando | E | existente | ◐ | contrato |
| RF-56 | Configurações são validadas, migradas entre versões com cópia de segurança e editáveis pela interface | E | existente | ◐ | unitário; teste de atualização |
| RF-57 | Instalação, atalhos e início automático no Windows usam o nome SAFRA e não exigem Node | E | existente | ◐ | CI Windows; Windows real |
| RF-58 | **Atualização controlada**: backup antes, conferência de integridade do pacote, verificação depois e retorno ao estado anterior se falhar | E | existente (parcial) | ○ | integração; Windows real |
| RF-59 | Dados e configurações de uma instalação atual são preservados na atualização, sem intervenção manual | E | novo | ○ | teste de atualização com banco de exemplo |
| RF-60 | Logs estruturados, com identificador de correlação, consultáveis pela Central de Comando | D | novo | ○ | unitário; contrato |
| RF-61 | Percepção (janelas, processos, tela, OCR), Observador e modo privacidade continuam disponíveis | D | existente | ✔ | unitário (existente) |
| RF-62 | Inventário passivo da rede local continua disponível | O | existente | ✔ | unitário (existente) |
| RF-63 | Objetivos persistentes, proatividade (sugere, não age), imaginação e geração de imagens continuam disponíveis | O | existente | ✔ | unitário (existente) |

## 2. Requisitos não funcionais

Medições no computador de referência (Windows do autor), salvo indicação. "Linha de base" é o valor medido
antes da migração, na Fase 3.

| ID | Categoria | Requisito | Meta | Verificação |
|---|---|---|---|---|
| RNF-01 | Desempenho | Resposta a comandos determinísticos | p95 ≤ 1,0 s do pedido à resposta publicada | PV-02 (linha de base no contêiner: p95 9,3 ms) |
| RNF-02 | Desempenho | Resposta com o modelo local a perguntas curtas | registrar p50 e p95; meta p50 ≤ 8 s | PV-02 com modelo real |
| RNF-03 | Desempenho | Inicialização | núcleo pronto ≤ 15 s; interface utilizável ≤ 5 s depois da API | PV-04 novo |
| RNF-04 | Desempenho | API local | leituras p95 ≤ 100 ms; entrega de evento p95 ≤ 200 ms | PV-08 |
| RNF-05 | Desempenho | Fluidez da interface | símbolo a ≥ 30 quadros/s sem GPU dedicada; resposta visual a uma ação ≤ 100 ms | PV-04 novo |
| RNF-06 | Recursos | Repouso com a interface aberta | CPU ≤ 5 %; memória do núcleo mais a casca registrada e não mais que 25 % acima da linha de base sem justificativa | PV-04 novo |
| RNF-07 | Voz | Acerto da palavra de ativação | ≥ 90 % das ativações intencionais, voz humana | PV-01B |
| RNF-08 | Voz | Ativações falsas | ≤ 2 % das frases sem a palavra | PV-01 |
| RNF-09 | Memória | Recuperação correta | ≥ 80 % entre as 3 primeiras | PV-03 |
| RNF-10 | Confiabilidade | Execução prolongada | 8 h sem falha fatal; crescimento ≤ 20 MB/h; nenhuma *thread* nem processo restante ao encerrar | PV-07 |
| RNF-11 | Confiabilidade | Isolamento de falhas | (a) falha da interface não encerra o núcleo; (b) falha da voz não impede gravar e ler memória; (c) falha de habilidade não encerra o aplicativo | PV-05 novo |
| RNF-12 | Confiabilidade | Recuperação | casca reaberta em ≤ 10 s; reconexão de eventos sem perda dentro da janela de 1.000 eventos | PV-05 novo |
| RNF-13 | Portabilidade | Plataformas | Windows 10/11 64 bits; Python 3.11 e 3.13; painel em Chrome, Edge e Firefox atuais | CI; Windows real |
| RNF-14 | Operação local | Sem internet | todas as funções essenciais operam sem internet; a interface não carrega nada de fora | teste: nenhuma requisição externa |
| RNF-15 | Manutenibilidade | Testes e arquitetura | suíte aprovada a cada commit no CI; regra de dependência entre domínios verificada; cobertura de linhas medida, com meta ≥ 70 % nos domínios novos | CI (a cobertura ainda não é medida hoje) |
| RNF-16 | Manutenibilidade | Fonte única de identidade | nenhuma cor, fonte ou medida fora dos *tokens* | teste automatizado |
| RNF-17 | Acessibilidade | Contraste, foco, teclado, toque | texto ≥ 4,5:1; componentes ≥ 3:1; foco visível; tudo operável por teclado; alvos de toque ≥ 44 px | teste sobre os *tokens*; funcional |
| RNF-18 | Usabilidade | Idioma e clareza | interface e mensagens em português do Brasil; erro sempre diz o que houve e o que fazer | revisão; funcional |
| RNF-19 | Compatibilidade | Instalações existentes | atualizam sem perda de banco, configurações, credenciais e início automático | teste de atualização; Windows real |
| RNF-20 | Originalidade | Recursos de terceiros | todo recurso externo tem licença registrada; nenhum nome, personagem, cenário ou som de obra alheia | teste de identidade; inventário de licenças |
| RNF-21 | Distribuição | Tamanho | tamanho da interface compilada e do pacote registrados a cada versão | registro no CI |

## 3. Requisitos de segurança

| ID | Requisito | P | Origem | Hoje | Verificação |
|---|---|:-:|---|:-:|---|
| RS-01 | O código não executa comandos por shell, `eval`, `exec`, `os.system` nem desserializa `pickle` | E | RS01 | ✔ | varredura (existente) |
| RS-02 | Pastas do sistema, do início automático, do programa e dos dados são recusadas como alvo antes de pedir autorização | E | RS02 | ✔ | unitário; PV-06 |
| RS-03 | Exclusões vão para a Lixeira; cópias de segurança nunca são sobrescritas | E | RS03 | ✔ | unitário (existente) |
| RS-04 | Senhas, *tokens* e dados financeiros são recusados antes de gravar em memória | E | RS04 | ✔ | unitário (existente) |
| RS-05 | Credenciais ficam só no cofre do sistema; nunca em arquivo, no JavaScript, em resposta da API ou em log | E | RS05 | ◐ | segurança |
| RS-06 | Conteúdo lido da tela, de arquivos ou de páginas entra no contexto do modelo como dado, nunca como instrução | E | RS06 | ✔ | unitário (existente) |
| RS-07 | Autorização expirada é negada; autorização permanente é escopada e revogável | E | RS07 | ✔ | unitário (existente) |
| RS-08 | A interface não carrega recursos externos; a casca bloqueia navegação para fora da API | E | RS08 (substitui) | ○ | segurança |
| RS-09 | O sistema não desativa proteções do sistema operacional nem contorna o UAC | E | RS09 | ✔ | varredura (existente) |
| RS-10 | A rede local só é observada por meios passivos | E | RS11 | ✔ | unitário (existente) |
| RS-11 | A API escuta só em 127.0.0.1 | E | novo | ○ | segurança: conferência do endereço de escuta |
| RS-12 | Toda rota exige sessão válida, exceto saúde e entrada | E | novo | ○ | segurança, sobre todas as rotas |
| RS-13 | `Origin` e `Host` são conferidos em todo pedido e no WebSocket; CORS fechado | E | novo | ○ | segurança |
| RS-14 | Pedidos que alteram exigem o valor anti-CSRF | E | novo | ○ | segurança |
| RS-15 | Não existe rota para executar habilidade arbitrária, SQL, terminal ou acesso direto ao modelo | E | novo | ○ | contrato: lista fechada de rotas |
| RS-16 | Sessões têm escopo por origem; confirmar ações sensíveis, ligar o Modo Operador, administrar sessões e redefinir configurações só pela janela do SAFRA (sessão `desktop`) | E | novo | ○ | segurança |
| RS-17 | Tamanho e frequência dos pedidos são limitados | E | novo | ○ | segurança |
| RS-18 | Só os eventos do catálogo são transmitidos; conteúdo de tela e de janelas não sai pelo contrato | E | novo | ○ | contrato |
| RS-19 | O Modo Operador nunca desbloqueia o que a política normal bloqueia e mantém as confirmações obrigatórias | E | RF33 | ✔ | unitário (existente, adaptado) |
| RS-20 | Dados de tabelas antigas só são removidos depois de exportados e conferidos | E | novo | ○ | teste de atualização |
| RS-21 | Dependências com versão travada; a interface é compilada a partir do arquivo de trava | D | novo | ○ | CI |
| RS-22 | O acesso remoto, quando existir, exige pareamento confirmado no computador, sessão revogável, HTTPS e conferência de origem | O | RS10 | ○ (posterior) | fora desta migração |

## 4. Restrições

| ID | Restrição | Motivo |
|---|---|---|
| RT-01 | Execução local em computador pessoal com Windows 10/11 64 bits | público-alvo e privacidade |
| RT-02 | Modelos de IA executados localmente; nuvem só opcional | operação sem internet e sem custo recorrente |
| RT-03 | Python 3.11 como versão de instalação; 3.13 testado | compatibilidade das bibliotecas de voz e Qt |
| RT-04 | Qt 6.8 (PySide6 `>=6.8.1,<6.9`) na casca | série testada |
| RT-05 | Um único banco SQLite | consistência e backup simples |
| RT-06 | Experiência só em 2D/2.5D; sem rosto humano, avatar 3D, ambientes ou modelos 3D | regra da missão |
| RT-07 | Sem nomes, personagens, cenários, marcas, músicas ou interfaces de terceiros | regra da missão |
| RT-08 | Paleta definida pelo autor | regra da missão |
| RT-09 | Sem hardware dedicado e sem robótica | escopo |
| RT-10 | Node só para desenvolver e compilar a interface | simplicidade de instalação |
| RT-11 | Nomes antigos só na camada de compatibilidade e em `legado/` | ADR-014, ADR-016 |

## 5. Requisitos retirados

| Anterior | O que era | Por quê |
|---|---|---|
| RF21 | holograma humanoide 3D | regra: sem avatar 3D; substituído por RF-41 |
| RF22 | boca acompanha o áudio | sem rosto; a energia do áudio fica em RF-16 |
| RF24 | reserva 2D na falta de WebGL | a interface não usa mais WebGL |
| RF27 | sala de controle 3D | regra: sem ambiente 3D nem tema de terceiros |
| RF33 (parte) | identidade alternativa (persona) | regra: sem personagens; o perfil fica em RF-34 |
| RNF04 | cena 3D pronta e taxa de quadros | substituído por RNF-03 e RNF-05 |
| RNF08 | atraso entre áudio e boca | sem boca |
| RT06 | identificadores `ultron` preservados | substituído por RT-11 |

## 6. Rastreabilidade com a missão

| Item da missão | Requisitos |
|---|---|
| Assistente por texto / por voz | RF-01 a RF-16 |
| Memória persistente | RF-17 a RF-22 |
| Organização por projetos | RF-23, RF-24 |
| Sistema de habilidades | RF-35, RF-36 |
| Execução controlada de ferramentas | RF-29, RF-32, RF-37 |
| Sistema de permissões / confirmação | RF-30, RF-31, RF-34 |
| Histórico de atividades | RF-33 |
| Monitoramento / diagnóstico | RF-52, RF-55, RF-60 |
| Recuperação de falhas | RNF-11, RNF-12 |
| Configurações | RF-56 |
| Atualizações controladas | RF-58, RF-59 |
| Validação de entradas, *timeouts*, erros centralizados | RF-29, RS-17, contrato §1.1 |
| Menor privilégio, isolamento de ferramentas | RS-15, RS-16, RF-29 |
| Logs estruturados | RF-60 |
| Proteção de credenciais | RS-05 |
| Prevenção de operações duplicadas | RF-37 |
| Backups e recuperação de dados | RF-22, RS-20 |
| Proteção da API local / autenticação do painel | RS-11 a RS-18, RF-49 |
| As três garantias de isolamento | RNF-11 |
| Dois contextos de interface | RF-39, RF-40 |
| Símbolo abstrato, sem rosto, sem 3D | RF-41, RT-06 |

## 7. Tipos de verificação

| Tipo | O que é |
|---|---|
| Unitário | um domínio isolado; a suíte atual |
| Arquitetura | regra de dependência entre domínios |
| Identidade | nomes e elementos de terceiros só onde a ADR-014 permite |
| Contrato | rotas e eventos conferidos contra `CONTRATO_V1.md` |
| Segurança | sessão, origem, anti-CSRF, escopos, limites, segredos; PV-06 |
| Integração | núcleo, API e casca juntos |
| Atualização | banco e configurações de exemplo na versão atual, levados à nova |
| Funcional | fluxos na interface real, com modelo simulado e declarado |
| Componente | componentes da interface isolados |
| Injeção de falhas | PV-05 novo |
| Medição | protocolos PV, com ambiente declarado |
| Windows real | roteiro executado pelo autor; resultado registrado com data e versão |
