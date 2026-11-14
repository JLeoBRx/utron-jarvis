# Linha de base de desempenho do legado

Data: 14/11/2026. Serve de comparação para a nova versão: nenhuma melhoria será declarada sem repetir estas
medições no mesmo ambiente.

## 1. Ambiente e validade

| Item | Valor |
|---|---|
| Máquina | contêiner Linux 6.18, Intel Xeon 2,30 GHz, 4 CPUs lógicas, 15,7 GB |
| Python | 3.13.18; PySide6 6.8.3 (Qt sem tela); Vosk 0.3.45; piper-tts 1.8.0 |
| Código medido | legado no commit `470359f` (código de execução idêntico desde `456fe23`) |
| Instrumento | `scripts/perf/legacy_baseline.py` — dados brutos em `data/legacy_baseline_470359f.json` |

**Este não é o computador de referência.** Os números valem para comparar o legado com a nova versão *neste
mesmo contêiner*. Não dizem como o SAFRA se comporta no Windows do autor.

| Real nestas medições | Simulado | Não medido |
|---|---|---|
| o programa inteiro como processo; o núcleo completo com SQLite; a síntese (Piper) e o reconhecimento (Vosk) | a inferência do modelo de linguagem (servidor local que responde em 0 ms) | Windows; microfone e alto-falante; GPU; modelo de linguagem real; tempo até o primeiro *token*; interface em tela real; taxa de erro em uso real |

## 2. Testes

| Execução | Resultado |
|---|---|
| Suíte completa do legado, commit `470359f`, 14/11/2026 | **475 aprovados, 0 falhas, 1 pulado**, 154,5 s |
| Suíte completa, commit `34c712b`, 13/11/2026 | 475 aprovados, 0 falhas, 1 pulado, 178,7 s |
| Cena 3D real (o teste pulado), commit `f1a9e2e` | 24 de 24 |

## 3. Medições novas (14/11/2026)

### 3.1 Processo completo

Tempo de parede de uma execução inteira do programa (interpretador, importações, trabalho, encerramento).
Sete execuções de cada.

| Caso | p50 | p95 | mín. | máx. | falhas |
|---|---:|---:|---:|---:|---:|
| `main.py --version` | 0,060 s | 0,064 s | 0,059 s | 0,065 s | 0 |
| `main.py --say "que horas são"` (inicia o núcleo, responde, encerra) | 1,94 s | 1,99 s | 1,90 s | 1,99 s | 0 |
| `main.py --gui-check` (monta a interface Qt sem tela e sai) | 1,12 s | 1,13 s | 1,04 s | 1,14 s | 0 |

### 3.2 Núcleo

Núcleo criado em processo, **sem** voz, percepção, plugins e interface.

| Medida | Valor |
|---|---|
| Inicialização do núcleo | 0,048 s na primeira vez (cria o banco); 0,013–0,015 s nas quatro seguintes |
| Comando determinístico, do pedido à resposta publicada (300 amostras) | p50 5,5 ms · p95 12,6 ms · p99 17,7 ms · máx. 23,7 ms |
| Caminho do modelo com inferência simulada (100 amostras) | p50 12,6 ms · p95 23,1 ms · p99 35,7 ms — é só a sobrecarga do núcleo, **não** o tempo de um modelo |
| Pedidos sem resposta | 0 de 400 |
| Memória residente | 56,1 MB após iniciar; 75,2 MB após os 400 pedidos |
| Repouso por 60 s | CPU do processo: média 0,55 %, p95 1,0 % de um núcleo lógico; 75,5 MB; 18 *threads* |
| *Threads* após encerrar | 1 (só a principal) |

### 3.3 Voz

Sobre áudio sintetizado, sem microfone nem alto-falante.

| Medida | Valor |
|---|---|
| Carregar a voz (Piper, `pt_BR-faber-medium`) | 1,28 s |
| Síntese por frase (20 amostras, 5 frases) | p50 84 ms · p95 122 ms · p99 130 ms |
| Fator de tempo real da síntese | p50 0,029 (sintetiza cerca de 34 vezes mais rápido do que a fala dura) |
| Carregar o modelo de reconhecimento (Vosk pequeno) | 0,25 s |
| Reconhecimento por frase (5 amostras) | p50 954 ms · máx. 2.092 ms; fator de tempo real p50 0,36 |

O reconhecimento tem só 5 amostras: o valor serve de ordem de grandeza, não de percentil confiável.

## 4. Medições anteriores ainda válidas

Feitas em 11–12/11/2026 no mesmo tipo de contêiner, sobre o mesmo código de execução. Dados em
`ULTRON/docs/research/resultados/`.

| Protocolo | Resultado |
|---|---|
| PV-01 ativação por voz (fala sintética) | "Safra" 2,2–3,9 % de acerto; "Jarvis" 17–18 %; ativações indevidas ≤ 0,46 % |
| PV-03 memória | perguntas com as mesmas palavras: 100 % entre as 3 primeiras; paráfrases: 45 %; lembrança indevida: 70 % |
| PV-04 interface | montagem da interface Qt 1,48 s (média de 10); cena 3D pronta em 0,73 s; 5,3 quadros/s com WebGL por software |
| PV-06 segurança | 11 de 11 ações indevidas bloqueadas; 4 de 4 ações legítimas executadas |
| PV-07 estabilidade, 30 min | 1.785 de 1.785 respostas; 0 erros; 55,6 → 74,3 MB; 8,4 MB/h depois de 5 min de aquecimento; nenhuma *thread* restante |

## 5. Leitura dos números

- **O núcleo é leve e rápido** sem os serviços opcionais: inicia em centésimos de segundo e responde a
  comandos diretos em milissegundos. A nova arquitetura acrescenta uma API no caminho; a meta é não passar de
  p95 de 100 ms para leituras locais.
- **O custo de abertura está fora do núcleo**: dos cerca de 1,9 s de um pedido por linha de comando, a
  inicialização do núcleo responde por centésimos. O resto é interpretador, importações e encerramento — o
  alvo do carregamento sob demanda.
- **A voz custa na carga, não no uso**: 1,3 s para carregar a voz e 0,25 s para o modelo de reconhecimento.
  São candidatos naturais a carregar depois que a interface abrir.
- **O que mais importa ainda não foi medido**: tempo de resposta e tempo até o primeiro *token* com um modelo
  real, consumo com a interface em tela real e comportamento em 8 horas. Ficam para o computador de referência.

## 6. Metas da nova versão (perfil equilibrado)

Metas, não resultados. Cada uma será medida com o mesmo instrumento, adaptado à API.

| Medida | Legado (contêiner) | Meta |
|---|---|---|
| Interface utilizável depois de iniciar | não comparável (Qt montava em 1,1–1,5 s) | abre antes de os serviços opcionais terminarem; ≤ 3 s no computador de referência |
| Comando determinístico pela API | 12,6 ms p95 (sem API) | ≤ 100 ms p95 |
| Memória do núcleo em repouso, sem voz | 75 MB | ≤ 150 MB, com a API no ar |
| CPU em repouso | 0,55 % | ≤ 2 % |
| Crescimento de memória | 8,4 MB/h (30 min) | ≤ 20 MB/h em 8 h |
| Tempo até o primeiro *token* (modelo local e remoto) | não medido | medir p50, p95 e p99; meta definida depois da primeira medição real |
| Síntese de voz por frase | 122 ms p95 | não piorar |
| Taxa de erro e recuperação | 0 erros em 1.785 pedidos | 0 falhas fatais; recuperação de provedor indisponível sem reiniciar |

## 7. Como repetir

```text
python scripts/perf/legacy_baseline.py            # completo, cerca de 5 minutos
python scripts/perf/legacy_baseline.py --rapido   # só para conferir o instrumento
```

Requer o ambiente Python do legado (`ULTRON/requirements.txt`). Usa pasta de dados temporária.
