# Prova de conceito da casca do desktop: Tauri × QtWebEngine

Data: 15/11/2026. Decisão correspondente: **AD-07, aberta**. Nada aqui migra o aplicativo: as duas cascas são
provas de conceito isoladas em `desktop/`, que abrem a mesma página (`desktop/poc-ui/`) e conversam com o
mesmo SAFRA Assistant pela rota de saúde, em `127.0.0.1`.

## 1. O que cada prova de conceito faz

| Item pedido | Tauri (`desktop/poc-tauri`) | QtWebEngine (`desktop/poc-qt/shell.py`) |
|---|---|---|
| Inicialização | inicia o Assistant como processo filho (`SAFRA_POC_BACKEND`), abre a janela, confere a saúde | igual |
| Encerramento | ao sair, encerra o Assistant e espera o processo terminar | igual |
| Instância única | `tauri-plugin-single-instance`: a segunda execução traz a primeira janela para a frente | não implementado |
| Área de notificação (bandeja) | ícone com menu "Abrir" e "Sair" | ícone com o mesmo menu, quando o sistema oferece bandeja |
| Notificações | `tauri-plugin-notification` | `QSystemTrayIcon.showMessage` |
| Comunicação com o backend local | HTTP em `127.0.0.1`, porta configurável; a página pede ao processo da casca, que consulta o Assistant | igual |
| Áudio e microfone | **não testados**: por desenho, captura e síntese ficam no processo do Assistant (Python), não na casca; a casca só exibiria o nível de áudio recebido por evento | idem |
| Autoteste | `--self-test` grava `SELFTEST_READY {…}` no arquivo de `SAFRA_POC_REPORT` depois que a página carrega | igual |

Permissões do Tauri (`capabilities/default.json`): só os comandos da própria prova de conceito e o envio de
notificações. A página não tem acesso a arquivos, *shell* ou rede externa; a CSP limita a origem ao próprio
aplicativo e ao Assistant local.

## 2. Método de medição

`desktop/measure_shell.py`, o mesmo para as duas cascas: inicia a casca com `--self-test`, espera o relatório de
pronto, amostra por 15 s a memória residente (RSS) e a CPU de **toda a árvore de processos** (casca, motor web e
o Assistant, quando ela o iniciou), encerra a árvore e confere que nenhum processo sobrou. Três execuções por
configuração. Os dados brutos ficam em `docs/performance/data/cascas/`.

Limites do método: a RSS soma páginas compartilhadas entre processos e por isso **superestima** o total; o
tempo de pronto é medido pela própria casca (do início do processo até a página avisar que carregou) e
confirmado pelo instrumento.

## 3. Resultados no contêiner Linux (não valem para o Windows)

Ambiente: contêiner Linux 6.18, 4 CPUs, Xvfb, renderização por software, sem GPU e sem área de notificação
real. Tauri com WebKitGTK; Qt 6.8 com Chromium embutido.

| Configuração | Pronto (ms, 3 execuções) | Processos | RSS da árvore, mediana (MB) | CPU em repouso | Sobrou processo? |
|---|---|---|---|---|---|
| Tauri, sem Assistant | 908 · 714 · 697 | 3 | 468 · 467 · 458 | ~0 % | não |
| Tauri iniciando o Assistant | 700 · 711 · 716 | 4 | 538 · 528 · 528 | 0 % | não |
| Qt, sem Assistant | 305 · 360 · 294 | 4 | 483 · 481 · 479 | ~0 % | não |
| Qt iniciando o Assistant | 14 667 (primeira, a frio) · 456 · 433 | 5 | 544 · 551 · 549 | ~0 % | não |
| Só o Assistant (referência) | 464 | 1 | 69,5 | — | — |

Outros números do contêiner: executável Tauri de versão (*release*) com 5 242 952 bytes, compilado em 2 min 39 s
sem avisos; latência da rota de saúde vista pela casca de 3 a 17 ms. A bandeja e a notificação do Tauri
responderam "ok", o que significa que a chamada retornou sem erro, **não** que algo foi visto na tela; a do Qt
informou que o ambiente não oferece bandeja.

Leitura: neste ambiente as duas cascas ficam na mesma faixa de memória, porque sem GPU o WebKitGTK e o
Chromium do Qt pesam parecido; a vantagem de memória que se espera do Tauri vem do WebView2 já instalado no
Windows, e só uma medição no Windows mostra se ela existe. O Qt abriu mais depressa aqui; a primeira execução
a frio com o Assistant (14,7 s) reflete o carregamento inicial das bibliotecas do Python e não se repetiu.

## 4. Resultados no Windows do CI

Ambiente: *runner* `windows-latest` do GitHub Actions, Python 3.13.17, commit `58571cd`, sem sessão de usuário
visível. Nas três execuções de cada casca, ela própria iniciou o Assistant. Dados em
`docs/performance/data/cascas/windows_ci.json`, transcritos do log do job
(<https://github.com/JLeoBRx/utron-jarvis/actions/runs/43775067299/job/132999452549>), porque esta sessão não
consegue baixar o artefato; os nomes dos processos não aparecem no log.

| Medida | Tauri (WebView2) | QtWebEngine |
|---|---|---|
| Compilação | 4 min 19 s, sem erros | não se aplica (Python) |
| Executável | 3 521 536 bytes (o WebView2 já vem com o Windows) | não se aplica; o Qt instalado pelo `pip` ocupa centenas de MB |
| Interface pronta (ms; a primeira é a frio) | 3 283 · 520 · 509 | 3 549 · 4 476 · 531 |
| Até o relatório completo, visto pelo instrumento (s) | 4,8 · 6,5 · 6,6 | 3,7 · 4,7 · 1,8 |
| Processos na árvore | 10 | 4 |
| RSS da árvore, mediana (MB) | 402 · 386 · 383 | 315 · 313 · 281 |
| CPU em repouso (média; 100 = um núcleo) | 0 – 0,11 % | 0,11 – 0,31 % |
| Bandeja e notificação | as chamadas retornaram "ok"; ninguém viu a tela | idem (no Qt, "ok" quer dizer que o sistema declara suportar mensagens) |
| Rota de saúde do Assistant | respondeu; a primeira resposta bem-sucedida levou ~1,5 s | respondeu; 75 ms a 1,1 s |
| Sobrou processo depois de encerrar | não | não |

O intervalo entre "interface pronta" e "relatório completo" é a espera pelo Assistant: nas duas cascas, a
página abre antes, e o relatório só é gravado quando a rota de saúde responde. O motivo da primeira resposta
lenta no Tauri (~1,5 s nas três execuções) **não foi investigado**.

Leitura: neste *runner*, a soma da memória ficou **menor no Qt** (~300 MB) do que no Tauri (~390 MB), o oposto do
que se costuma esperar. A RSS do Windows soma páginas compartilhadas entre os 10 processos do WebView2, que numa
máquina real também são usados por outros programas; três execuções num *runner* compartilhado são poucas; e as
duas cascas abriram a interface em cerca de meio segundo depois da execução a frio. Os números **não decidem**
a AD-07: mostram que as duas funcionam no Windows e que a diferença de memória precisa ser medida na máquina
do autor, de preferência com o conjunto privado de cada processo (*private working set*) em vez da RSS.

## 5. O que falta para decidir a AD-07

| Falta | Por quê |
|---|---|
| Medir no Windows do autor, com GPU e área de notificação reais, e com a memória privada de cada processo | o CI não tem sessão de usuário visível, e a RSS somada favorece quem tem menos processos |
| Ver a bandeja e a notificação na tela | "ok" na chamada não prova que o usuário viu |
| Critérios da AD-07 que a prova de conceito não cobre | iniciar com o Windows, tecla de atalho global, clique na notificação, o Assistant sobrevivendo à queda da casca |
| Instância única no Qt | só o Tauri implementa |
| Tamanho do instalador e tempo de atualização | as provas de conceito não geram instalador (publicação de instaladores não autorizada) |
| Comportamento com o microfone em uso pelo Assistant | áudio não passa pela casca, mas é preciso confirmar que a casca não disputa o dispositivo |
| Custo de manutenção | Tauri exige Rust no projeto; Qt mantém tudo em Python, mas carrega as obrigações da LGPL do Qt na distribuição (ver `docs/engineering/LICENSE_INVENTORY.md`) |

Até lá, **nenhuma das duas está escolhida**, e o aplicativo legado continua como está.
