# JARVIS 2.0 — Auditoria da inicialização (a janela não abria no Windows 10)

Pedido: o `START_JARVIS.bat` não abria a interface no Windows 10 e o diagnóstico parava em
`Diagnostico do sistema:`. Esta auditoria responde às 10 perguntas com o que foi **reproduzido ou medido**.
O que não pôde ser verificado (o seu PC, o seu microfone, a sua bandeja) está dito como tal.

## Causa

`HudController.__init__` criava a bandeja do sistema **antes** de criar `self.state_cache`. Quando o sistema
tem bandeja (todo Windows de mesa), `_make_tray()` monta o menu e já chama `sync()`, que preenche o submenu
do Observador lendo `self.state_cache` — que ainda não existia:

```
File "ultron/hud/controller.py", line 88, in __init__        self.tray = self._make_tray()
File "ultron/hud/controller.py", line 803, in _menu           sync()
File "ultron/hud/controller.py", line 668, in _fill_observer_menu
AttributeError: 'HudController' object has no attribute 'state_cache'
```

Reproduzido aqui com o mesmo traceback, declarando a bandeja disponível. Entrou na Fase 3 (commit `25c0324`,
21/10, quando o submenu do Observador foi para a bandeja). Os testes e o CI não pegavam porque rodam com o Qt
*offscreen*, que não tem bandeja: o menu nunca era montado na construção. Com o `pythonw` (sem console), a
exceção ia só para o registro e o processo saía — nenhuma janela, nenhuma mensagem.

## As 10 perguntas

| # | Pergunta | Resposta (evidência) |
|---|---|---|
| 1 | O que o `START_JARVIS.bat` faz? | Sem argumentos, `start "" .venv\Scripts\pythonw.exe main.py`: um processo **sem console**, e o `.bat` termina na hora. Qualquer erro só aparece no `ultron.log`. |
| 2 | O `pythonw.exe` é encerrado silenciosamente? | **Sim.** A exceção acima subia até `main()`, era registrada como `CRITICAL exceção não tratada` e o processo saía com código 1 (reproduzido). |
| 3 | Instância anterior presa? | Não neste defeito: o processo que caía saía de verdade, e o mutex `Local\ULTRON.NeuralCore` some com ele. Mas havia um problema parecido: com uma instância **viva** (escondida na bandeja ou em modo console), abrir de novo imprimia "O JARVIS já está em execução" num processo sem console — parecia que "não abria". |
| 4 | O `NeuralCore` trava? | Não (medido): criar o núcleo 0,04 s; `boot()` 1,3–2,3 s com voz, percepção e plugins (21 componentes). E a janela é montada **antes** do boot, que roda em segundo plano. |
| 5 | O Ollama bloqueia o boot? | Não: as chamadas têm prazo e o boot termina sem ele (CI: Ollama ausente, núcleo iniciado em ~2 s). Sem Ollama, comandos diretos, lembretes e memória continuam. |
| 6 | Vosk ou Piper demoram indefinidamente? | Não indefinidamente: o modelo grande do Vosk levou **11,4 s** para carregar aqui, numa thread própria. A janela não espera por ele; o diagnóstico esperava (até 30 s) **sem imprimir nada**. |
| 7 | Erro no PySide6, Qt ou OpenGL? | Não neste caso (Qt 6.8 abriu offscreen e no CI do Windows; o rosto usa CPU por padrão, OpenGL só se escolhido). Mas as mensagens do Qt se perdiam sem console — inclusive a fatal, de plataforma gráfica que não carrega. |
| 8 | O `run_hud()` falha? | **Sim — é a causa** (acima). |
| 9 | O SQLite ou o `settings.json` impedem? | Não neste caso. Banco danificado e configuração ilegível já eram tratados na Fase 7 (mensagem clara, arquivo intacto); o diagnóstico agora confere a integridade do banco (`quick_check`) e lê as configurações como etapas próprias. |
| 10 | O diagnóstico espera sem prazo? | Dois problemas. (a) Ele só imprimia **depois** de tudo — boot, espera da voz (até 30 s), sonda da voz (até 15 s), saúde — e parecia travado em `Diagnostico do sistema:`. (b) Com a saída redirecionada (instalador sob outro programa, pipe, arquivo), ele **caía** com `UnicodeEncodeError` no caractere `→` logo depois dessa linha — reproduzido no Windows Server 2025 do CI. Num console comum o Python escreve Unicode, então no seu caso o mais provável é (a). |

O `%LOCALAPPDATA%\ULTRON\logs\ultron.log` do seu PC não está acessível daqui; o traceback que você encontrou
nele é idêntico ao reproduzido.

## O que foi corrigido

1. **Interface**: `state_cache` criado logo no início (o mesmo dicionário de sempre, compartilhado pelas
   páginas e atualizado no lugar — não um dicionário novo); o submenu do Observador aceita dado ausente ou
   malformado (antes do boot vale a configuração) sem esconder erro de inicialização; ele é relido do estado
   real a cada abertura do menu.
2. **Falha da interface**: traceback completo no registro; o motivo aparece (no terminal, ou numa caixa de
   mensagem do Windows quando não há console); o modo console é oferecido — no terminal com o MESMO núcleo,
   sem console numa janela nova, depois de liberar a instância. Nunca duas instâncias. Código de saída 4.
3. **Já em execução**: abrir de novo traz a janela para a frente; se ela não responder, ou se a instância
   estiver em modo console, uma mensagem diz o que fazer.
4. **`--stop` durante a abertura se perdia**: a janela apagava pedidos de parada ao terminar de montar; um
   `--stop` enviado nesse intervalo (ex.: `ATUALIZAR_JARVIS.bat` logo após abrir) era ignorado. Achado pelo
   teste novo; corrigido.
5. **Mensagens do Qt** vão para o registro (`ultron.qt`), inclusive as fatais.
6. **Diagnóstico por etapas** (`ultron/diagnose.py`): cada etapa aparece ao terminar, as lentas avisam antes,
   cada uma tem prazo; a que não responde fica `[TEMPO]` com o nome dela e as independentes continuam. Inclui
   a **interface gráfica montada de verdade** (sem mostrar a janela, num processo separado) — teria apontado
   esta falha. Nenhum caractere derruba a saída.
7. **Modo console completo** (`ultron/console.py`): cabeçalho com o estado real (modelo, memória, TARDIS,
   voz), prompt com o nome configurado (`profile_name`), cada resposta esperada antes do próximo prompt,
   confirmações de autorização, Ctrl+C cancela o pedido, `sair` e `--stop` encerram em ordem.

8. **Processos filhos e a entrada do usuário**: a verificação da GPU (no boot) chamava o PowerShell sem
   fechar a entrada padrão; com a entrada redirecionada ele a lia até o fim — no CI do Windows, as linhas
   enviadas ao modo console sumiam antes do primeiro prompt. Todas as chamadas de processo agora fecham a
   entrada (teste confere o código inteiro).

9. **`chcp` e a entrada**: no Windows, o `chcp 65001` do início dos `.bat` consome a entrada padrão quando ela
   vem redirecionada (confirmado por sondas no CI: o mesmo `.bat` sem o `chcp` conversou, com ele não). Todos os
   `.bat` usam `chcp 65001 <nul >nul`; num terminal comum não havia efeito, mas scripts e atalhos que
   redirecionam a entrada passam a funcionar.
10. **Voz e boca** (achados pelo CI no Windows): o efeito de voz quebrava com áudio muito curto, e a boca
    "abria" em 1e-15 no limite entre quadros logo após a fala. Ambos corrigidos, com testes.

Verificado no CI do Windows (execução 56): instalação pelo `INSTALL_JARVIS.bat` a partir do ZIP, diagnóstico
por etapas até o fim, `START_JARVIS.bat --version/--status/--backup/--list-backups/--say`, a **janela aberta
pelo `pythonw` e fechada com `--stop`**, o **console** com conversa, memória, confirmação negada e `sair`, e a
**interface montada com a plataforma nativa do Windows e a bandeja do sistema disponível** — o caminho que
derrubava a sua janela.

## O que continua sem verificação no seu PC

A janela real com a sua bandeja, o seu microfone e a sua voz. Os testes declaram a bandeja disponível no Qt
offscreen para percorrer o mesmo caminho do Windows, e o CI monta a interface no Windows Server — não é a sua
área de trabalho. Roteiro para confirmar: §2 de `README_JARVIS.md` (`START_JARVIS.bat`,
`START_JARVIS.bat --console`, `DIAGNOSTICO_JARVIS.bat`; para ver erros no terminal,
`START_JARVIS.bat --foreground`).

## Achado fora do escopo (não alterado)

Perguntas gerais à memória sem assunto ("quais ideias salvei?", "quais são minhas ideias?") respondem "não
encontrei"; com assunto funcionam ("o que anotei sobre horta?", "quais ideias salvei para o projeto Atlas?").
É do mecanismo de perguntas da memória (igual na janela e no console), não da inicialização.
