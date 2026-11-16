# JARVIS — Relatório de desempenho

Todos os números abaixo foram **medidos**, não estimados. Nada aqui afirma melhora sem medição.

## 1. Método

* Ferramenta: `tools/benchmark.py` (no repositório). Pasta de dados temporária, Ollama simulado
  por HTTP local (inferência fixa de 250 ms), sem microfone, sem tocar nos dados do usuário.
* Mede: custo por quadro do desenho isolado (600 quadros por cenário), e — com o **núcleo
  real** e as janelas reais (Qt *offscreen*) — CPU do processo, quadros pintados por segundo,
  tempo de pintura, tempo da thread da interface ocupada pintando, atraso do laço da interface,
  memória (RSS), latência de resposta e threads restantes após o encerramento. Fases: repouso
  logo após iniciar, repouso estável, atividade (pedidos + crescimento do grafo), TARDIS aberto,
  TARDIS com uma região aberta, cada perfil de qualidade e orbe compacto.
* **Mesmas condições**: as três versões foram medidas em sequência, na mesma sessão e máquina,
  com o mesmo script (`docs/benchmarks/final_compare_*.json`):
  * **Antes da missão** — commit `6f73c2b` (ULTRON, antes desta transformação);
  * **Antes da Fase D** — commit `e692875` (TARDIS e voz novos, ainda sem otimização);
  * **Final** — a versão entregue.
* Ambiente: Linux em contêiner, 4 vCPUs, Python 3.13, renderização por software (*offscreen*).
  **Não é o seu Windows nem a sua GPU**: os valores absolutos mudam no seu computador; as
  relações entre versões (mesmo roteiro, mesma máquina) é que são comparáveis. Para medir no
  Windows: `.venv\Scripts\python.exe tools\benchmark.py --out resultado.json`.

## 2. Resultados (mesmas condições)

### JARVIS CORE (núcleo real, 1320×820)

| Medida | Antes da missão (`6f73c2b`) | Antes da Fase D (`e692875`) | Final |
|---|---|---|---|
| Repouso estável: CPU do processo | 39,2 % | 37,9 % | 22,0 % |
| Repouso estável: quadros pintados por segundo | 36,7 | 37,2 | 17,1 |
| Repouso estável: tempo de pintura (média) | 8,47 ms | 8,06 ms | 8,75 ms |
| Repouso estável: thread da interface ocupada pintando | 311,3 ms/s | 300,3 ms/s | 149,5 ms/s |
| Repouso estável: atraso do laço da interface (p95) | 10,41 ms | 10,38 ms | 7,20 ms |
| Em atividade: CPU | 52,5 % | 52,4 % | 48,4 % |
| Em atividade: atraso do laço (p95) | 18,53 ms | 18,94 ms | 19,20 ms |
| Em atividade: pintura (média / p95) | 13,0 / 24,7 ms | 13,3 / 24,8 ms | 13,9 / 26,8 ms |
| Latência da resposta (p50; 250 ms de inferência simulada) | 257 ms | 261 ms | 261 ms |
| Memória (RSS) em repouso | 145,8 MB | 161,9 MB | 168,3 MB |
| Threads após encerrar (além do servidor simulado) | 0 | 0 | 0 |

### TARDIS (aberto e em foco; o CORE fica visível atrás)

| Medida | Antes da missão (`6f73c2b`) | Antes da Fase D (`e692875`) | Final |
|---|---|---|---|
| CPU com o TARDIS aberto, em repouso | — | 93,4 % | 23,2 % |
| Pintura do TARDIS (média) | — | 19,10 ms | 3,73 ms |
| Quadros do TARDIS por segundo | — | 24,5 | 15,2 |
| Quadros do CORE atrás do TARDIS | — | 28,0 | 8,0 |
| Atraso do laço da interface (p95) | — | 22,56 ms | 3,84 ms |
| CPU com uma região aberta (painel lateral) | — | 68,9 % | 28,8 % |
| Memória (RSS) com o TARDIS aberto | — | 185,0 MB | 192,3 MB |

### Custo por quadro, desenho isolado (600 quadros)

| Medida | Antes da missão (`6f73c2b`) | Antes da Fase D (`e692875`) | Final |
|---|---|---|---|
| CORE repouso (grafo maduro): média / quadros > 16 ms | 5,94 ms / 0 | 4,85 ms / 0 | 5,23 ms / 1 |
| CORE em execução: média / quadros > 16 ms | 13,91 ms / 135 | 12,67 ms / 103 | 13,95 ms / 131 |
| CORE com a câmera em movimento: média / quadros > 16 ms | 9,57 ms / 8 | 9,54 ms / 18 | 9,57 ms / 12 |
| TARDIS repouso com dados: média / quadros > 16 ms | — | 17,04 ms / 314 | 2,88 ms / 0 |
| TARDIS com eventos: média / quadros > 16 ms | — | 17,15 ms / 335 | 4,46 ms / 0 |
| TARDIS viagem da câmera: média / quadros > 16 ms | — | 15,36 ms / 206 | 7,70 ms / 0 |

### Perfis de qualidade (CORE em repouso)

| Perfil | Antes da missão | Antes da Fase D | Final |
|---|---|---|---|
| Econômico | 22,7 % · 20 q/s | 19,0 % · 14 q/s | 17,8 % · 12 q/s |
| Equilibrado | 32,5 % · 26 q/s | 43,1 % · 48 q/s | 23,7 % · 17 q/s |
| Alto | — | 40,7 % · 32 q/s | 33,5 % · 26 q/s |
| Cinematográfico | 74,6 % · 64 q/s | 78,5 % · 64 q/s | 49,0 % · 42 q/s |
| Orbe compacto | 16,3 % · 24 q/s | 17,2 % · 24 q/s | 13,3 % · 15 q/s |

**Leitura honesta dos números**

* **Melhorou (medido):** repouso do CORE (CPU −44 %, metade dos quadros, metade do tempo de
  pintura por segundo, atraso do laço p95 −31 %); TARDIS aberto (CPU −75 %, quadro 19,1 → 3,7 ms,
  atraso do laço p95 22,6 → 3,8 ms; nenhum quadro acima de 16 ms em repouso, com eventos ou na
  viagem da câmera); todos os perfis e o orbe.
* **Não melhorou:** o custo de um quadro do CORE **em atividade** (≈ 13–14 ms; a Fase E
  adicionou os efeitos de estado — halo da escuta, ondas, arco do plano — que custam até ~1 ms
  por quadro ativo; comparações lado a lado repetidas ficaram dentro do ruído de ±0,5 ms) e o
  atraso do laço p95 em atividade (≈ 19 ms, igual). A CPU em atividade caiu pouco (52,5 → 48,4 %).
* **Piorou:** memória +22 MB em repouso (145,8 → 168,3 MB) por causa dos recursos novos (TARDIS,
  painéis, diagnóstico de voz, autonomia); o TARDIS aberto soma ~24 MB.
* A latência de resposta não mudou (é dominada pela inferência).
* Variação entre horários: em outras sessões o mesmo cenário "CORE em execução" mediu de 80 a
  217 quadros acima de 16 ms para o MESMO código — por isso só comparo versões medidas juntas.

## 3. O que causava o custo e o que foi feito

| Causa (medida) | Correção |
|---|---|
| Verificação de saúde de rotina a cada 15 s fazia a sinapse de TELEMETRIA crescer e mantinha o CORE no teto de quadros ~4 s por ciclo (amostragem das causas de movimento em repouso) | só mudanças reais do quadro de saúde animam (assinatura dos problemas); rotina vira um brilho abaixo do limiar de crescimento |
| Repouso pintando 34–37 quadros/s para um giro lento | cadência de repouso por perfil (10/15/24/40) e giro mais lento em repouso (≈1–2 px por quadro, sem degraus) |
| CORE continuava pintando atrás do TARDIS | hub atrás do outro em foco cai para a cadência de fundo (5/8/10/15) |
| TARDIS redesenhava elipses grandes antisserrilhadas e caminhos com traço de 1,2 px a cada quadro (≈ 8 ms em portais, 3,8 ms em corredores) | camada estrutural em cache, refeita só quando a câmera/dados/foco mudam; traços cosméticos de 1 px (caminho rápido do QPainter): portais 8,1 → 1,7 ms, corredores 3,8 → 0,2 ms; marcas dos anéis giradas por transformação (1,05 → 0,46 ms); estrutura desenhada direto durante a viagem da câmera |
| TARDIS no teto de quadros com partículas rápidas | fluxo de partículas proporcional à atividade real; repouso na cadência ociosa |
| Sensores de contexto no mesmo ritmo com o usuário ausente | intervalos relaxados após 5 min sem teclado/mouse (janelas ×3, processos ×3, sistema ×2,5, visão ×4), restaurados ao voltar; microfone, lembretes e rede inalterados |

Outras garantias do projeto, verificadas por testes: nenhuma consulta ao banco na thread da
interface (leitores em thread própria), nenhum `sleep` na thread da interface, relógio dos
hubs parado quando ocultos ou minimizados, timers únicos por hub, workers nomeados e únicos,
cancelamento cooperativo, densidade limitada por perfil (partículas, pulsos, sinapses ativas,
pontos da malha) e malha 3D em camada de cache (não é recalculada a cada quadro).

## 4. Perfis de qualidade

| Perfil | Teto | Repouso | Fundo | Partículas | Uso indicado |
|---|---|---|---|---|---|
| Econômico | 30 | 10 | 5 | 70 | notebooks, máquinas modestas |
| Equilibrado (padrão) | 60 | 15 | 8 | 120 | uso geral |
| Alto | 90 | 24 | 10 | 190 | desktops com folga |
| Cinematográfico | 144 | 40 | 15 | 260 | demonstração, máquinas fortes |

O teto respeita `hud_fps` (configurável). Perfil muda só o custo visual; memória, lembretes,
execução e segurança são idênticos em todos. Trocar: bandeja > *Qualidade visual*.

## 5. Histórico

* `docs/benchmarks/before_jarvis.json` — medição da Fase A (outra sessão).
* `docs/benchmarks/phase_d_before.json` / `phase_d_after.json` — Fase D, medidas na mesma sessão.
* `docs/benchmarks/final_compare_*.json` — as três versões acima, mesmas condições.
