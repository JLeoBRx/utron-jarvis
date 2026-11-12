# Resultados das medições

Cada arquivo JSON traz os dados brutos, as métricas calculadas, o ambiente (sistema, CPU, memória, versões, commit,
data) e as listas `real` e `simulado`. Os protocolos estão em `../PROTOCOLOS_DE_VALIDACAO.md`; a análise, no TCC
(Capítulo 12). Rótulo `conteiner` = ambiente C (Linux, sem GPU, microfone ou alto-falante).

| Arquivo | Protocolo | Ambiente | Resumo |
|---|---|---|---|
| `linha_de_base_bf070f6.txt` | suíte | C | 471 testes, 0 falhas, 1 pulado (antes da fase SAFRA) |
| `pv01_ativacao_conteiner-sintetico.json` | PV-01 A | C, voz sintética | "Safra" 3,9 % (pequeno) / 2,2 % (grande); "Jarvis" 17,2 % / 18,3 %; indevidas 0,46 % / 0 % |
| `pv01_analise_formas_conteiner-sintetico.json` | PV-01 (exploratório) | C | "faça" como forma fraca: "Safra" 88,9 % no modelo grande, indevidas 0,9 % — **não adotado** |
| `pv02_latencia_conteiner-modelo-simulado.json` | PV-02 | C, inferência simulada | determinísticos p95 9,3 ms; sobrecarga do modelo p95 20,7 ms; núcleo inicia em 52 ms |
| `pv03_memoria_conteiner-antes-da-correcao.json` | PV-03 | C | lexical 90 %; paráfrase 40 %; indevida 70 % |
| `pv03_memoria_conteiner-depois-da-correcao.json` | PV-03 | C | lexical 100 %; paráfrase 45 %; indevida 70 % (só palavras inteiras em comum) |
| `pv04_interface_conteiner-webgl-software.json` | PV-04 | C, llvmpipe | montagem 1,48 s; cena pronta 0,73 s (10/10, 0 erros JS); 5,3 q/s (sem GPU: não avalia a meta) |
| `pv05_sincronizacao_conteiner.json` | PV-05 A | C | defasagem forma×áudio mediana 0 ms (p95 10 ms); boca fechada no silêncio 100 %; início de palavra mediana 60 ms |
| `pv06_seguranca_conteiner.json` | PV-06 | C | 11/11 tentativas bloqueadas sem efeito; 4/4 controles |
| `pv07_estabilidade_conteiner-30min.json` | PV-07 | C, 30 min | 1.785/1.785 respostas; 0 erros; 8,4 MB/h após aquecimento; 0 threads restantes |

Resultados do computador de referência (ambiente R) entram aqui com o rótulo `pc-referencia` (cronograma:
março e maio de 2027).
