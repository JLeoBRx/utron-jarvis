# Testes do SAFRA — estratégia, comandos, ambientes e resultados

Documento técnico de testes da fase SAFRA. A estratégia e os protocolos experimentais estão descritos com
detalhe no TCC (Capítulo 11) e em `docs/research/PROTOCOLOS_DE_VALIDACAO.md`; aqui ficam os comandos, os
ambientes e os resultados de cada execução. O relatório de testes das fases anteriores (`../../TEST_REPORT.md`)
é histórico.

## 1. Comandos

```text
python TEST_JARVIS.py                      suíte completa + relatório do ambiente
python TEST_JARVIS.py test_voice test_memory   módulos escolhidos
python TEST_JARVIS.py --quick              sem os testes lentos
JARVIS_TEST_SCENE3D=1 xvfb-run -a python TEST_JARVIS.py test_scene3d    cena 3D real no Linux
python -m pyflakes ultron gateway tests tools TEST_JARVIS.py TEST_ULTRON.py main.py
python -m compileall -q ultron gateway tests tools main.py TEST_JARVIS.py
python tools/build_release.py --out ../JARVIS_FINAL.zip                 pacote validado
python tools/experimentos/pvNN_*.py --rotulo NOME                       protocolos PV-01…PV-07
```

## 2. Ambientes

| Ambiente | Descrição | Usado para |
|---|---|---|
| C — contêiner | Linux 6.18, 4 vCPUs, 15 GB, Python 3.13.18 em ambiente virtual, PySide6 6.8.3, Qt *offscreen*; Xvfb + llvmpipe para a cena 3D; sem GPU, microfone, alto-falante ou Ollama | suíte, cena 3D real, protocolos no ambiente C |
| CI Linux | GitHub Actions `ubuntu-latest`, Python 3.11 e 3.13, Xvfb | suíte, cena 3D real, estáticos, pacote extraído |
| CI Windows | GitHub Actions `windows-latest` (Windows Server 2025), Python 3.11 | suíte, estáticos, pacote, instalação pelo `INSTALL_JARVIS.bat` |
| R — computador de referência | Windows do autor, GPU, microfone, alto-falante | rodadas oficiais de 2027 (PV-01B, PV-02, PV-04, PV-05B, PV-07 8 h) |

## 3. Resultados da suíte nesta fase

| Momento | Commit | Ambiente | Resultado |
|---|---|---|---|
| Linha de base (antes da fase) | `bf070f6` | C, Python 3.13 | **471 testes, 0 falhas, 1 pulado** (cena 3D real, executada à parte) — `docs/research/resultados/linha_de_base_bf070f6.txt` |
| Linha de base | `bf070f6` | CI (execução 61) | aprovado em Linux 3.11/3.13 e Windows |
| Depois da identidade SAFRA, 1ª execução | trabalho local | C | 30 falhas — expectativas de texto ("JARVIS") e **identificadores renomeados por engano** (cofre de credenciais, pastas do original) |
| Depois das correções | trabalho local | C | 1 falha (quebras de linha CRLF dos `.bat`) |
| Etapa 3 entregue | `35a7554` | C | **474 testes, 0 falhas**; cena 3D real 24/24 (a 1ª tentativa revelou a ponte `window.JARVIS` renomeada, com 1 erro de JavaScript) |
| Etapa 4 (correções de memória) | ver `CHANGELOG.md` | C | **475 testes, 0 falhas** (novo teste de regressão da recuperação de memória) |

## 4. Defeitos encontrados nesta fase

| # | Defeito | Encontrado por | Correção | Teste de regressão |
|---|---|---|---|---|
| 1 | Serviço do cofre de credenciais renomeado | `test_security.CredentialsTest` | revertido para "JARVIS" | o próprio teste |
| 2 | Pastas do JARVIS original renomeadas na importação | `test_original_recovery` | revertido | o próprio teste |
| 3 | Prefixo de variáveis de ambiente renomeado | revisão do diff | `SAFRA_` somado a `JARVIS_`/`ULTRON_` | suíte (usa `JARVIS_DATA_DIR`) |
| 4 | Entrada do início automático renomeada | revisão do diff | revertido | CI do Windows confere a chave |
| 5 | Ponte `window.JARVIS` renomeada (cena 3D sem estado) | `test_scene3d.NativeSceneTest` (cena real) | revertido | o próprio teste |
| 6 | CRLF dos `.bat` perdido | `test_cli.WindowsScriptsTest` | CRLF restaurado | o próprio teste |
| 7 | Recuperação casava pedaços de palavras ("ana" em "losartana") | protocolo PV-03 | comparação por palavra, com variação de plural/gênero | `test_memory.test_recall_ignores_accents_and_never_matches_pieces_of_words` |
| 8 | Fato sem palavra em comum passava pelo limite só com bônus de recência/uso | protocolo PV-03 | exige sobreposição lexical > 0 | idem |
| 9 | Pré-filtro do banco sensível a acentos ("medico" não achava "médico") | protocolo PV-03 | comparação sem acentos, por palavra | idem |
| 10 | Calibração poderia aprender "faça" como forma da palavra de ativação | análise do PV-01 | "faça" (e afins) proibidas como forma forte | `test_voice.test_calibration_never_learns_common_words_near_safra` |
| — | Instrumento PV-05: tempos do Vosk acumulavam entre frases | revisão dos dados (erros de dezenas de segundos) | reconhecedor novo por frase | — (instrumento) |
| — | Instrumento PV-07: inclinação misturava aquecimento | revisão das amostras | métrica após o aquecimento | — (instrumento) |

## 5. Resultados dos protocolos (ambiente C)

Resumo; análise completa no TCC, Capítulo 12, e dados em `docs/research/resultados/`.

| Protocolo | Resultado principal | Meta | Situação |
|---|---|---|---|
| PV-01 (voz sintética) | "Safra" 2,2–3,9 %; "Jarvis" 17–18 %; indevidas ≤ 0,46 % | ≥ 90 %; ≤ 2 % | ativação **não atingida** (voz sintética); indevidas atingida |
| PV-02 (inferência simulada) | determinísticos p95 9,3 ms; sobrecarga do modelo p95 20,7 ms | p95 ≤ 1 s | RNF01 atingida; RNF02 não medida |
| PV-03 | lexical 100 %; paráfrase 45 %; indevida 70 % | recall@3 ≥ 80 % | atingida para lexical; **não** para paráfrase |
| PV-04 (WebGL por software) | montagem 1,48 s; cena 0,73 s; 5,3 q/s | ≤ 5 s; ≥ 30 q/s com GPU | não avalia a meta |
| PV-05 A | defasagem forma×áudio mediana 0 ms (p95 10 ms); silêncio 100 %; início de palavra mediana 60 ms | ITU-R BT.1359 (apresentação) | cálculo alinhado; apresentação não medida |
| PV-06 | 11/11 bloqueadas; 4/4 controles | 100 % / 100 % | atingida |
| PV-07 (30 min) | 1.785/1.785 respostas; 0 erros; 8,4 MB/h após aquecimento; 0 threads | 8 h; ≤ 20 MB/h; 0 | parcial (30 min) |
