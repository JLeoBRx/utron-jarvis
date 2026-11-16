# Inventário da interface — JARVIS original × plataforma atual

Auditoria **somente leitura** · 21/10/2026

## Fontes, método e convenções

- **Original**: export em `53e5a31:JARVIS (git archive 53e5a31 JARVIS)/`. Os arquivos `jarvis_hud.py`, `neural_core.py`, `autostart.py`, `jarvis_lock.py`, `jarvis_lock_setup.py`, `README_TELA_JARVIS.md` e `LEIA-ME.txt` são **idênticos** aos do commit `53e5a31` do repositório (conferido com `git show 53e5a31:JARVIS/<arquivo> | cmp`).
- **Atual**: `ULTRON/`.
- **Caminhos**: sem prefixo (ex.: `jarvis_hud.py:2517`) = original. Começando por `ultron/` ou `ULTRON/` = atual.
- **Método**: leitura integral de `jarvis_hud.py` (3118 linhas), `neural_core.py`, `neural_hud_engine.py`, `live_hud_state.py`, `interface.py`, `Jarvis.py`, lock/autostart, `.bat` e documentos; trechos de `backend.py`, `copilot.py` e `telemetria.py` que alimentam a HUD; leitura de `ultron/hud/*`, `ultron/platform/*`, `ultron/app.py` e dos documentos atuais. **Nada foi executado** (não há Windows aqui, e a regra de não escrever no repositório impediu rodar os testes). "Funcional?" = funcional pela leitura do código. Nenhum documento do original registra validação em tela real (CHANGELOG_HUD_HOLOGRAMA.md:27-35, README_FASE_13_HOLOGRAPHIC_HUD.md:26, README_INICIO.md:22-23).
- **Status**: **PRESERVADO** (equivalente existe; diferenças menores anotadas) · **PARCIAL** (existe, mas falta parte relevante) · **AUSENTE** · **SUBSTITUÍDO** (trocado de propósito por outra solução).
- Cópias antigas (`*_BACKUP_*`, `*_ANTES_*`, `_backup_antes_do_copilot/`) aparecem só no **Apêndice A** e não entram na contagem.

### Linha do tempo do elemento central (evidências)

1. `interface.py` (Tkinter): núcleo pulsante estático com valores fixos (interface.py:98-181, 218-229, 479-485). Observação: `Jarvis.py` **não tem interface gráfica**; é um assistente de console (Vosk + pyttsx3 + Ollama, sem nenhum import de tkinter).
2. Reator circular "NEURAL CORE // SIM" (jarvis_hud_BACKUP_FUNCIONANDO.py:572-754).
3. Avatar humanoide holográfico, Fase 13 (README_FASE_13_HOLOGRAPHIC_HUD.md:7-18), hoje a classe `CoreWidgetAvatarAntigo` (jarvis_hud.py:1004-1243).
4. Globo wireframe `CoreWidget` (CHANGELOG_HUD_HOLOGRAMA.md:6-12; jarvis_hud.py:1246-1596).
5. Cérebro neural `NeuralCore`/`BrainSim`, o **único elemento instanciado na versão final** (jarvis_hud.py:2517; neural_core.py:65-542; README_INICIO.md:14). Avatar e globo ficaram como código morto: não há nenhuma instância deles no projeto.

---

## 1. Elementos visuais centrais (avatar, globo, cérebro)

### 1.1 Avatar holográfico humanoide: `CoreWidgetAvatarAntigo` (jarvis_hud.py:1004-1243)

**Situação no original final**: classe de reserva, não instanciada (docstring 1005-1006; o CHANGELOG_HUD_HOLOGRAMA.md:12 explica como religá-la). Validação apenas sintática (README_FASE_13_HOLOGRAPHIC_HUD.md:26). É um **busto** (cabeça, ombros, tronco até a cintura e braços pendentes, sem pernas) sobre uma plataforma de projeção.

**Unidades e enquadramento**
- Escala `s = min(w/700, h/620)` (1054). Origem horizontal `cx = 0,5·w` (1052); referência vertical `base_y = 0,72·h` (1053).
- Constantes (em `s`): raio da cabeça 61 (1056), pescoço 34 (1057), `shoulder_y = base_y − 205` (1058), `head_y = shoulder_y − 96 = base_y − 301` (1059), meia-largura dos ombros 155 (1061), queda do braço 145 (1062). `torso_bottom` (1060) é calculado e nunca usado.
- Não desenha nada se `w` ou `h` < 260 (1044-1045). Entra com fade de ~1,15 s após cada expansão da HUD: opacidade = easeOutCubic((`anim.since` − 0,1)/1,15) (1048-1050; `summon_t` é reiniciado em 2715).
- Primitivas: `_line` (1025-1026); `_joint` = círculo preenchido na cor do estado com contorno branco de 0,8 px (1028-1031); **`_glow_line` = traço duplo**: halo com 4,5× a largura e 1/4 do alfa + linha fina por cima (1033-1038). Esse traço duplo é a "assinatura" luminosa de todas as linhas estruturais.

**Partes** (coordenadas em `s`; x relativo a `cx`; y relativo a `base_y`, positivo para baixo)

| Parte | Linhas | Geometria | Traço / alfa |
|---|---|---|---|
| Atmosfera | 1064-1071 | gradiente radial centrado em (0, −250), raio 270 | centro α 35+42·energia; α15 a 34 %; borda 0 |
| Plataforma de projeção | 1073-1083 | elipses em y = +30: 175×30 e 130×19; 12 raios girando a 0,4 rad/s, de r = 132 (achatamento 17) até r = 158+8·sen(t+i) (achatamento 22) | 1 px, α75 |
| Varredura do corpo | 1085-1093 | linha de ±205 que desce de y = −275 até +65 em ciclo de ~4,3 s (`t·0,23`) + faixa em gradiente de ±28 | linha α80; faixa α24 no centro |
| Partículas de projeção | 1095-1103 | 105 partículas (semente 17, 1016-1021): x = ±210·ox; y = −205 + 280·oy − ((18·t·sp + 3i) mod 95); sobem e reiniciam; raio 0,75·tamanho (1 a 2,8) | α 22+92·tw; tw = 0,35+0,65·(0,5+0,5·sen(t·(1,8+sp)+fase)) |
| Halo da cabeça | 1105-1110 | radial de raio 1,55·61 em (0, −301) | α 35+35·energia, até 0 |
| Contorno da cabeça | 1112-1117 | elipse 61 × 69 (ry = 1,13·61); dois arcos de reforço sobre o próprio contorno: 20° a 165° e 205° a 325° | 1,4 px α205; arcos 1 px α125 |
| Malha da cabeça | 1119-1125 | 5 "meridianos" verticais em x = (−0,62; −0,30; 0; 0,30; 0,62)·61, altura ±0,85·61; 5 "paralelos" = elipses achatadas em y = (−0,65 … 0,65)·61, meia-largura 61·√(1−y²) e meia-altura 5 | 0,7 px α70 |
| Olhos | 1128-1132 | duas fendas retas: esquerda de (−38, −309) a (−14, −311); direita de (14, −311) a (38, −309); a ponta interna fica 2·s mais alta | `_glow_line` 1,8 px α220 + halo de 8,1 px α55 |
| Nariz | 1133-1135 | polilinha (0, −305) → (−3, −279) → (8, −276) | branco 0,8 px α165 |
| Boca | 1136-1137 | arco inferior (205° a 335°) da elipse de caixa x ∈ [−24, 24], y ∈ [−277, −257]: um sorriso discreto | 1 px α130 |
| Pescoço | 1139-1143 | duas linhas de (∓24,5; −246) a (∓31,3; −240) | glow 1,4 px α190 |
| Clavículas | 1145-1151 | ombros (∓155, −205) → (∓50, −229) → esterno (0, −212) | 1,8 px α220 / 1,2 px α170 |
| Tronco | 1153-1159 | trapézio: peito em (∓105, −170), cintura em (∓75, −18) | glow 1,5 px α180 |
| Grade torácica | 1161-1169 | 5 linhas horizontais a 18/35/52/69/86 % entre ombro e cintura, meia-largura 104−28·fração; 5 verticais em x = (−0,7 … 0,7)·92, de −177 a −20 | 0,75 px α75 |
| Reator do peito | 1171-1187 | centro (0, −130), rr = 28: radial de raio 2,5·rr (branco α245 → cor α245 em 22 % → α90 em 55 % → 0); anel branco de raio rr; arco de 250° no raio 1,45·rr girando 80°/s; 8 marcas radiais (1,05 a 1,55·rr) girando 0,6 rad/s | anel 1,5 px α210; arco 2 px α210; marcas 1 px α120 |
| Braços e juntas | 1189-1203 | cotovelos em (∓192, −110); mãos em (∓202, −30); juntas de raio 5 (ombro, α210), 4 (cotovelo, α180) e 3,5 (mão, α190); 4 "dedos/feixes" por mão: Δx = ±(8+4j), Δy alternando ±4 | braço 1,8 px α205; antebraço 1,4 px α175; dedos 0,7 px α130 |
| Linhas de energia dos braços | 1205-1211 | 4 linhas por lado, do ombro (y = −195) até a altura do cotovelo, espaçadas 7·s | branco 0,7 px α75 |
| Cortes do holograma | 1213-1218 | 8 linhas horizontais que descem de y = −245 ao longo de 285·s (ciclo de 12,5 s); meia-largura 125·(0,45+0,55·sen²(π·Δy/285)), com silhueta de corpo | branco 0,7 px α55 |
| Textos | 1220-1243 | topo: "HOLOGRAPHIC AVATAR // ONLINE", "PROJECTION MATRIX // MARK VII", "PERCEPTION // ACTIVE", "CORE // <modelo Ollama>"; base: nome do estado (Segoe UI 20, negrito, espaçamento 4), subtítulo `STATE_SUB`, "MIC 000%" e "LATÊNCIA IA n MS" (ou N/D) | Consolas 6,5 a 8 |

**Como a animação se liga a estado e áudio**
- **Estado → cor**: tudo usa `col = anim.color` (1047), interpolada a 4/s (215-219) em direção a `state_color` (100-111). Na paleta final: IDLE/RETURNING_IDLE `#1E8CFF`; WAKE ≈`#33F3FF`; LISTENING `#00F0FF`; THINKING/TOOL_EXECUTION ≈`#8CF8FF`; SPEAKING ≈`#4CF4FF`; ERROR `#FF2A3D`.
- **Estado → energia**: `anim.energy` tende a `ENERGY[estado]` (120-121; IDLE 0,24 · WAKE 1 · LISTENING 0,75 · THINKING/TOOL 1 · SPEAKING 0,9 · ERROR 0,6), a 2,5/s (220). **No avatar a energia só muda o alfa da atmosfera (1066) e do halo da cabeça (1107).**
- **Tempo puro** (não depende de estado nem de áudio): raios da plataforma (1079-1083), varredura (1086), subida e cintilação das partículas (1100-1101), arco e marcas do reator (1182, 1185), cortes (1216).
- **Áudio**: o nível **real** do microfone (`anim.mic`, 224) aparece **somente como texto** "MIC 000%" (1241). Não há boca ou olhos animados, nem geometria que reaja à voz; `anim.voice`, `anim.think` e `anim.spin` não são usados. Isso contradiz README_FASE_13_HOLOGRAPHIC_HUD.md:18 ("resposta visual à energia, voz/microfone").

**Defeitos e esquisitices (evidência)**
- `scan_offsets` (1022) e `torso_bottom` (1060) nunca são usados.
- `x*.999` (1123) e `x*.998` (1169) inclinam de leve meridianos e verticais (efeito desprezível).
- Precedência de operadores em 1211: as 4 linhas de energia do braço **esquerdo convergem** no cotovelo e as do **direito ficam paralelas**, uma assimetria involuntária.
- O "pescoço" (1140-1143, de +54,9 a +61 abaixo do centro da cabeça) fica **dentro** do contorno da cabeça (queixo em +68,9); na prática a cabeça encosta no "V" das clavículas.

**DNA visual a preservar no rosto novo**
- Holograma **monocromático na cor do estado**, com branco só nos realces (contorno das juntas, nariz, cortes, centro do reator).
- Traço duplo halo + linha fina; cabeça elíptica com malha de meridianos e paralelos; olhos em fenda; nariz em polilinha mínima; boca em arco.
- Partículas que sobem; varredura horizontal lenta; cortes descendentes com silhueta de corpo; plataforma elíptica com raios girando.
- Rótulos técnicos nos cantos e nome do estado em caixa alta sob a figura.
- Sinais reais que o projeto atual **já expõe** e que o avatar original não usava: nível do microfone `scene.hearing` e nível real da fala `scene.voice_level` (ultron/hud/scene.py:893-904, vindos de `mic_level` e `out_level` da telemetria, ultron/hud/controller.py:204-215). São a base natural para olhos e boca reativos.

**Atual**: **AUSENTE**. Nenhum avatar ou rosto em `ultron/hud`.

### 1.2 Globo wireframe: `CoreWidget` (jarvis_hud.py:1246-1596)

Fora de uso na versão final (código morto); foi validado só com PySide6 simulado (CHANGELOG_HUD_HOLOGRAMA.md:27-29).

- **Malha**: 5 paralelos (−60° a 60°) e 8 meridianos de 40 segmentos (1272-1281); rotação em giro e inclinação (1287-1293); separa trechos da frente e de trás com alfas diferentes (1295-1316). Raio R = max(40, min(0,165·w, (h−130)/4,2)) (1410-1414).
- **Camadas**: atmosfera (1417-1424); feixe de projeção em trapézio + 3 elipses (2,25 / 1,65 / 1,05·R, achatamento 0,17) + 48 marcas girando (1426-1444); anel graduado de 120 marcas (1446-1454); 3 arcos ativos girando com `anim.spin` (1456-1464); 46 partículas de poeira orbital, atrás e à frente do globo (1466-1479, 1541).
- **Anel de áudio**: 90 barras radiais espelhadas; amplitude = histórico **real** do microfone (`audio_hist`) + mistura de mic e voz × ruído + energia (1481-1495).
- **Globo**: corpo em gradiente, contorno, malha e um plano de varredura branco que oscila mais rápido ao pensar (1497-1517).
- **Núcleo de energia**: pulsa com a energia e o mic; mostra arcos internos ao pensar (1519-1539).
- **Medidores**: CPU à esquerda e RAM à direita, arcos de 120° com cores por faixa de 75 % e 90 % (1327-1351, 1543-1546).
- **Nós**: 6 módulos reais (voz, TTS, IA, visão, memória, automação) em R·1,62 (1259-1260, 1548-1568).
- **Interação**: o ponteiro inclina o globo; clique no núcleo liga/pausa o microfone; hover e clique nos nós (1354-1393, 1407-1408, 1498-1499).
- **Textos**: "HOLOGRAPHIC CORE // ONLINE" etc. (1574-1596).

**Atual**: **AUSENTE**. O halo de áudio e o anel de subsistemas do cérebro atual cumprem parte do papel (ultron/hud/brain_view.py:331-362, 702-747).

### 1.3 Cérebro neural: `BrainSim` + `NeuralCore` (neural_core.py), o elemento central da versão final

- **Malha**: 230 pontos de casca. θ é uniforme; φ = acos(U(−0,75; 1)), sem a calota inferior; giros g = 1 + 0,11·sen(5θ+3φ)·sen(4φ); y·0,78 e z·0,8; fissura longitudinal (|z| < 0,06 é empurrado ±0,09). Mais 34 pontos de cerebelo e tronco (neural_core.py:69-80). Arestas: 3 vizinhos mais próximos com d² < 0,09 (87-93).
- **Gênese**: a ordem de nascimento vai do tronco para a coroa (−y ± 0,35), entre 1,2 e 9,2 s (83-86). Cada partícula **voa do núcleo** até a posição final em 1,6 s (321-326). Cada sinapse é desenhada de i para j em 1,1 s, com cabeça brilhante (94, 336-352). Há um brilho quando o ponto encaixa (359). O título "J.A.R.V.I.S." / "NEURAL CORE" surge depois de 8,5 s (381-394). O relógio `gt` conta desde o **início do processo** (95, 206); como a HUD inicia oculta, a gênese normalmente acontece sem ser vista.
- **Núcleo de energia e faíscas**: halo azul → azul profundo e núcleo gelo → ciano, que crescem com a formação, a respiração e os pulsos (297-311). Faíscas: 16/s durante a gênese, depois 2,5/s + 70·boost + 10·energia, no máximo 90 (261-267, 313-315).
- **Projeção 3D**: giro de 0,2 + 0,8·boost + 0,4·energia rad/s (228); inclinação fixa −0,12; perspectiva 1/(1 − 0,22·Z); alongamento horizontal 1,28 (317-332). Alfa por profundidade; frente de onda radial e cintilação quando o JARVIS é chamado (343-346, 357); pulsos percorrendo sinapses (271-275, 363-368); conexões novas temporárias (121-124, 369-374).
- **Nós do plano**: 12 na órbita externa (VISÃO … VOZ) e INTENÇÃO/VERIFICAÇÃO na interna (22-25). A "intenção" vem de **regex sobre o texto do pedido** (31-45, 129-145), e linhas de log acrescentam módulos (147-157). A ativação é em cadeia, com 0,45 s entre nós (233-240). Cada sinapse é uma curva quadrática que cresce com ponta brilhante e 2–3 sinais viajando (419-443). O nó só aparece quando a sinapse chega, com anel de chegada (444-452), rótulos e tags LOCAL/ACTIVE (469-478) e uma cadeia pontilhada entre os nós já chegados (479-483).
- **Rota Ollama → GPT**: `m` migra em ~1,8 s; a sinapse local enfraquece e a do GPT se intensifica; rótulos MIGRANDO / GPT ACTIVE (172-179, 229, 415-418, 465-468).
- **Estado sob o título**: `vstate · rota` (160-179, 395-397).
- **Painéis gerados pelo cérebro**: `PANEL_MODS` liga cada painel a módulos (47-49); a opacidade `po` (250-256) controla os painéis (jarvis_hud.py:3046-3054). `FlowLayer` faz partículas saírem do centro do cérebro para o painel (materializar) ou voltarem a ele (dissolver), em curva quadrática com desvio de ±70 px, até 220 partículas; as que voltam alimentam o pulso (neural_core.py:545-594).
- **Widget**: centro em 0,45·h e R = min(0,19·w; 0,25·h); clique no núcleo (≤ 1,1·R) liga/pausa a escuta; hover e clique em nós (≤ 14 px) (489-542). O orbe compacto `CompactWidget` desenha o mesmo cérebro sem nós, sob um véu escuro (jarvis_hud.py:1900-1928).

**Defeitos**
- `vstate` mostra "VERIFYING" durante SPEAKING e "WAITING" durante ERROR (neural_core.py:164-170).
- O clique num nó chama `ModulesPanel.describe(nome)` (jarvis_hud.py:2764-2766, 468-474), que só reconhece TELEMETRIA, MEMÓRIA e AUTOMAÇÃO. Para os outros **11 de 14** nós, a conversa recebe apenas o nome.
- `neural_hud_engine.py` e `live_hud_state.py` **não são lidos pela HUD**: o primeiro é escrito por autonomous_core.py:62-63 e voice_pipeline.py:21-31 e lido só por test_fases36_40.py; o segundo não é usado. Isso contradiz README_INICIO.md:16.

**Atual (reimplementação)**: é a mesma família de malha — mesma semente 11, mesma fórmula de casca, a fissura e a gênese "do tronco para a coroa" com ±0,35 (ultron/hud/brain_model.py:67-80, 116, 137-141). Agora tem 640 pontos, com lobos temporais, cerebelo, tronco e estruturas internas (117-132), além de:
- regiões funcionais (32-44) e densidade que cresce com o grafo real (61-64, 152-157);
- nós reais do Neural Graph em posições fixas por tipo (46-58, 205-220);
- câmera que vira a região ativa para o observador (ultron/hud/scene.py:28-47, 82-91, 835-892);
- anel de 15 subsistemas cuja sinapse cresce só durante o uso (scene.py:95-104, 954-971; brain_view.py:702-769);
- módulos que nascem de uma região (scene.py:688-702; brain_view.py:848-876);
- boot em 12 fases ligado a eventos reais (scene.py:55-61, 279-336).

### 1.4 Status dos elementos centrais

| ID | Recurso | Original | Funcional? | Atual | Status | Observação |
|---|---|---|---|---|---|---|
| C1 | Avatar humanoide holográfico | jarvis_hud.py:1004-1243 | Código íntegro, mas não instanciado (código morto) | — | AUSENTE | rosto/avatar será um projeto novo |
| C2 | Globo wireframe 3D com anel de áudio, medidores e nós | jarvis_hud.py:1246-1596 | Código íntegro, mas não instanciado | — | AUSENTE | |
| C3 | Cérebro de partículas como elemento central | neural_core.py:65-109, 291-397, 489-542; jarvis_hud.py:2517 | Sim | ultron/hud/brain_model.py:104-150; ultron/hud/brain_view.py:441-494; ultron/hud/scene.py:340-396 | PRESERVADO | reimplementado e ampliado |
| C4 | Gênese do cérebro | neural_core.py:83-94, 317-352, 381-394 | Sim, mas roda nos primeiros ~12 s do processo, em geral com a HUD oculta | brain_model.py:137-141; scene.py:1059-1063; brain_view.py:446-470, 549-551 | PARCIAL | os nós surgem por fase real de boot, com brilho; sem voo a partir do núcleo e sem sinapses desenhadas progressivamente |
| C5 | Núcleo de energia, faíscas, pulsos nas sinapses, frente de onda ao ser chamado | neural_core.py:115-124, 259-275, 297-315, 343-374 | Sim | núcleo (brain_view.py:665-674); partículas e pulsos só por eventos reais (scene.py:446-517; brain_view.py:571-613, 676-699) | PARCIAL | sem emissão contínua de faíscas nem frente de onda |
| C6 | Nós do plano em órbita, com sinapses que crescem em cadeia, anel de chegada e rótulos | neural_core.py:22-28, 181-256, 399-483 | Sim (plano heurístico por regex) | anel de 15 subsistemas (scene.py:95-104, 954-971; brain_view.py:702-769) + etapas reais do plano no arco (brain_view.py:378-411) | PRESERVADO | reinterpretado com sinais reais; sem a cadeia INTENÇÃO→VERIFICAÇÃO |
| C7 | Rota Ollama ↔ GPT animada | neural_core.py:126-127, 172-179, 229, 415-418, 465-477 | Sim | modelo ativo no rodapé e modo LOCAL no rótulo (brain_view.py:808-815, 1049-1050) | PARCIAL | sem animação de migração |
| C8 | Identidade sob o cérebro ("J.A.R.V.I.S." / "NEURAL CORE" / estado · rota) | neural_core.py:381-397 | Sim (rótulo de estado errado em SPEAKING e ERROR) | "JARVIS" / "CORE" / "ESTADO · MODO" (brain_view.py:796-817) | PRESERVADO | |
| C9 | Interação com o núcleo: clique liga/pausa a escuta; hover e clique em nós; inclinação pelo ponteiro (globo) | neural_core.py:502-532; jarvis_hud.py:2588-2589, 2764-2766, 1363-1393 | Parcial (o clique em nó descreve só 3 de 14) | `BrainView` não trata eventos de mouse (brain_view.py inteiro) | AUSENTE | |
| C10 | Painéis gerados pelo cérebro (opacidade por módulo + partículas `FlowLayer`) | neural_core.py:47-49, 250-256, 545-594; jarvis_hud.py:2549-2565, 3046-3065 | Sim | módulos (máximo 3) nascem de uma região com conector animado e somem quando o dado real acaba (scene.py:341, 688-702, 728-808, 1034-1046; brain_view.py:820-876) | PARCIAL | sem partículas; os painéis completos deixaram de existir |

---

## 2. Efeitos e camadas

### 2.1 Estados e sinais reais

| Estado (`backend.STATES`, backend.py:58-67) | Subtítulo (jarvis_hud.py:114-119) | Cor / energia / voz | O que dispara | Atual |
|---|---|---|---|---|
| IDLE | AGUARDANDO COMANDO | `#1E8CFF` · 0,24 · 0,12 | transições do backend (backend.py:153-180, 1090-1100) | REPOUSO, azul profundo (ultron/hud/palette.py:20, 35) |
| WAKE | ATIVANDO INTERFACE | ≈`#33F3FF` · 1 · 0,8 | palavra "Jarvis" (backend.py:1056 → `activate`, 215-224) ou abertura pelo botão (jarvis_hud.py:2853-2854); expande a HUD (2747-2750) | não é estado: o evento WAKE_WORD estimula a região auditiva e expande o HUB (scene.py:626-628; controller.py:44, 180-182) |
| LISTENING | OUVINDO SUA VOZ | `#00F0FF` · 0,75 · 1 | `activate` / `toggle_microphone` (backend.py:840-860) | ESCUTANDO + halo pelo nível real do mic (brain_view.py:331-362) |
| THINKING | PROCESSANDO SOLICITAÇÃO | ≈`#8CF8FF` · 1 · 0,2 | `process_command` | THINKING / PLANNING / CONTEXT / DECIDING (scene.py:32-41) |
| TOOL_EXECUTION | EXECUTANDO AÇÃO | ≈`#8CF8FF` · 1 · 0,35 | agente executando ferramenta | EXECUTANDO, com pulsos e a sinapse do subsistema usado |
| SPEAKING | RESPONDENDO POR VOZ | ≈`#4CF4FF` · 0,9 · 1 | TTS | FALANDO + anéis pelo nível real da voz (brain_view.py:350-362; scene.py:897-900) |
| ERROR | ATENÇÃO NECESSÁRIA | `#FF2A3D` · 0,6 · 0,1 | falhas do backend | ERRO: contorno fixo no tom de falha (brain_view.py:338-343) |
| RETURNING_IDLE | RETORNANDO AO OCIOSO | `#1E8CFF` · 0,24 · 0,12 | minimizar a HUD (backend.py:226-234; jarvis_hud.py:2833) → contração | não existe (recolher é instantâneo) |

**Sinais reais no original**
- Estado: fila `backend.event_queue`, drenada a cada 16 ms (jarvis_hud.py:2976-2983, 3005-3023).
- Nível do microfone: `backend.audio_level`, RMS do bloco PCM mapeado de −60…−10 dB para 0…1 (backend.py:85-100, 1031). É suavizado (jarvis_hud.py:224) e guardado em histórico de 10 amostras/s × 120 (234, 3017-3019).
- `backend.status` com mic/tts/ollama/vision (backend.py:82).
- Telemetria lida a cada 0,25 s (jarvis_hud.py:3014-3016): psutil (CPU, RAM, bateria, rede), nvidia-smi (GPU), netsh (Wi-Fi), ping ao Ollama `/api/tags` (latência e modelos), SQLite (memórias e automações) e tempo desde o início (telemetria.py:1-11, 77-84).
- Log → console e contagem de atividade (jarvis_hud.py:2999-3003); texto do usuário → `SIM.plan` (2758, 2987); resposta → `SIM.keep_open(6)` e `SIM.note` (2991-2992); eventos do copilot (2902-2935).
- **Sem fonte real**: `ENERGY` e `VOICE` são constantes por estado (120-123), e as barras do StateChip misturam o alvo fixo `VOICE` × ruído senoidal com o mic real (881).

**Sinais no atual**: Event Bus → fila limitada → `scene.on_event` (ultron/hud/controller.py:131-184); `STATE_CHANGED` copia só os campos alterados (186-202); a telemetria (mic_level, out_level, listening, speaking, mic_state) é lida a cada `telemetry_ms` do perfil (204-219; ultron/hud/quality.py:48-65).

| ID | Recurso | Original | Funcional? | Atual | Status | Observação |
|---|---|---|---|---|---|---|
| S1 | Estados exibidos, cada um com cor e efeito ligados a sinais | jarvis_hud.py:100-123, 211-224, 2741-2754 | Sim | ultron/hud/palette.py:19-38; scene.py:28-51; brain_view.py:331-376, 796-817 | PRESERVADO | conjunto ampliado (percepção, contexto, memória, imaginação, autorização); sem WAKE/RETURNING_IDLE como estado; sem subtítulos descritivos |
| S2 | Motores de estado visual `neural_hud_engine.py` e `live_hud_state.py` | neural_hud_engine.py:1-101; live_hud_state.py:1-16 | Não (escritos, mas nunca lidos pela HUD) | JARVIS_STATE + Event Bus (controller.py:131-202) | SUBSTITUÍDO | |

### 2.2 Efeitos e camadas

| ID | Efeito | Original | Funcional? | Atual | Status | Observação |
|---|---|---|---|---|---|---|
| E1 | Cor de estado global com transição suave: painéis, textos, anéis e chips usam `anim.color` | jarvis_hud.py:100-111, 211-219 | Sim | halo azul em repouso, ciano em atividade e coral no erro, com troca discreta via cache (brain_view.py:37, 303); a paleta por estado só tinge o TARDIS (tardis.py:269, 452) | PARCIAL | no CORE a cor do estado não tinge painéis nem textos e não interpola |
| E2 | Fundo com gradiente radial + vinheta | jarvis_hud.py:1763-1768, 1789-1792 | Sim | brain_view.py:168-195 | PRESERVADO | atual é estático (em cache), com grão fino |
| E3 | Grade de 40 px | jarvis_hud.py:1769-1773 | Sim (só com o cérebro acordado: `kb = build·1,4`, 1765) | — | AUSENTE | |
| E4 | Scanlines horizontais a cada 3 px (pixmap) | jarvis_hud.py:1732-1744, 1774-1775 | Sim | — | AUSENTE | |
| E5 | Partículas de fundo (80 em tela cheia, 14 no modo compacto) | jarvis_hud.py:1727-1729, 1754-1760, 1776-1782 | Sim | grão estático (brain_view.py:180-183) | AUSENTE | |
| E6 | Faixa de varredura que desce pelo fundo (90 px/s) | jarvis_hud.py:1783-1788 | Sim | — | AUSENTE | |
| E7 | Overlay: molduras em L nos 4 cantos da tela, com alfa pulsante | jarvis_hud.py:1833-1845 | Sim, mas o overlay só aparece com a HUD cheia e `SIM.build > 0,35` (2631-2639) | cantos em L de 10 px só nos módulos (brain_view.py:896-904) | PARCIAL | |
| E8 | Overlay: retícula central (2 círculos + 8 marcas girando 7°/s) | jarvis_hud.py:1847-1859 | Sim | órbitas elípticas estáticas do anel (brain_view.py:319-328) | SUBSTITUÍDO | |
| E9 | Overlay: linha de varredura (115 px/s) | jarvis_hud.py:1861-1867 | Sim | — | AUSENTE | |
| E10 | Overlay: barra de atividade no rodapé (0,72·energia + 0,28·mic) | jarvis_hud.py:1872-1881 | Sim | barra de PROFUNDIDADE 0–9 (brain_view.py:995-1003; scene.py:48-51, 823-833) | SUBSTITUÍDO | outra métrica (profundidade cognitiva) |
| E11 | Overlay: flash curto na troca de estado | jarvis_hud.py:1814-1818, 1883-1889 | Sim | clarão só quando a resposta fica pronta (`release`: scene.py:615-622, 918; brain_view.py:665-674) | PARCIAL | |
| E12 | Overlay: sequência "INITIALIZING CORE 000–100 %" | jarvis_hud.py:1891-1896, 3024-3026 | Ineficaz: são 3 s contados desde a criação do overlay; a HUD inicia oculta (2865-2871) e o overlay só aparece com ela cheia, então quase nunca é visto; não reflete o boot real | boot em 12 fases com eventos reais, trilha de pontos, "JARVIS ONLINE" e regiões acendendo (scene.py:55-61, 279-336, 543-555; brain_view.py:430-439, 1004-1039) | SUBSTITUÍDO | |
| E13 | Entrada escalonada dos painéis (fade + deslize de 28 px, atrasos de 0,3 a 0,9 s, refeita a cada expansão) | jarvis_hud.py:273-275, 283-288, 2514-2522, 2715 | Sim | fade dos módulos + conector que cresce da região (scene.py:981-987; brain_view.py:857-873) | PARCIAL | |
| E14 | Barras superiores e campo de comando que se escondem sozinhos; aparecem com o cérebro ativo, com o mouse perto (topo < 96 px, base < 280 px) ou ao digitar | jarvis_hud.py:2557-2562, 3055-3063 | Sim | barra de entrada sempre visível (window.py:213-219) | AUSENTE | |
| E15 | Visualização do nível de áudio: forma de onda de 12 s, barra ÁUDIO, barras do StateChip, anel do globo | jarvis_hud.py:634-644, 394-397, 880-884, 1481-1495 | Sim (o globo está fora de uso) | halo de escuta pelo mic real + anéis de fala pelo nível real da TTS (brain_view.py:331-362; scene.py:893-904); anel do mic no orbe (orb.py:100-105) | SUBSTITUÍDO | sem histórico nem forma de onda |

**Sub-efeitos do avatar e do globo** (não contados à parte; seguem C1/C2): plataforma de projeção, reator do peito, varredura do corpo, cortes do holograma, partículas de projeção (avatar); feixe de projeção, anel graduado, arcos ativos, poeira orbital, plano de varredura (globo). Todos AUSENTES no atual. O mini-reator do logotipo está em P22.

---

## 3. Painéis e interações

**Contexto do original final**
- **Layout**: três colunas. À esquerda, STATUS, MÓDULOS e DIAGNÓSTICO. No centro, o núcleo e a INTERFACE DE INTERAÇÃO. À direita, REDE, ATIVIDADE, CONSOLE e AUTOMAÇÃO. As colunas laterais têm de 250 a 390 px (jarvis_hud.py:2514-2547).
- **Os painéis laterais só existem quando o cérebro os materializa**: a opacidade vem de `SIM.po[painel]`, e abaixo de 0,1 o painel fica transparente ao mouse (2549-2556, 3046-3054; neural_core.py:47-49, 250-256). Em repouso estão invisíveis, e MÓDULOS só aparece com 3 ou mais módulos reais no plano (neural_core.py:253). A interatividade descrita no CHANGELOG, portanto, só existe nessas janelas de tempo.

**Atual**: o `BrainView` ocupa a janela inteira. A barra de entrada fica embaixo, com até 1000 px (window.py:213-219), e as barras de decisão empilham acima dela (222-232). No máximo 3 módulos aparecem, em colunas à esquerda e à direita (scene.py:341, 1034-1046; brain_view.py:820-835).

| ID | Recurso | Original (arquivo:linha) | Funcional? | Atual (arquivo:linha) | Status | Observação |
|---|---|---|---|---|---|---|
| P1 | Base de painel `HudPanel`: polígono chanfrado (12 px), cantos acentuados de 16 px, quadrado 5×5 na cor do estado, título espaçado, linha em gradiente com brilho branco correndo, selo DEMO | jarvis_hud.py:266-332 | Sim (o selo DEMO nunca aparece: todos os painéis usam `demo=False`, 2514-2522) | módulos: retângulo α0,82, cantos em L de 10 px, título ciano (brain_view.py:896-911) | PARCIAL | sem chanfro e sem varredura na linha do título |
| P2 | STATUS DO SISTEMA: CPU, RAM (% e GB), GPU, ÁUDIO (mic), REDE (↓/↑); barras de 28 segmentos; cor de atenção ≥ 75 % e de erro ≥ 90 %; destaque e tooltip por linha | jarvis_hud.py:336-429 | Sim, com ressalvas: só aparece quando TELEMETRIA entra no plano (neural_core.py:47); a cor "AMBER" da versão final é `#7FE3FF`, ciano claro (jarvis_hud.py:50) | rodapé "CPU · RAM · GPU · MODELO · MIC" + ponto de saúde (brain_view.py:1041-1065); Sistemas › DESEMPENHO E SAÚDE (panels.py:1399-1497) | PARCIAL | sem barras, faixas de cor, tráfego de rede e tooltips |
| P3 | MÓDULOS: 8 módulos reais com LED radial piscante e texto de estado; destaque ao passar o mouse; clique esquerdo escreve a descrição na conversa | jarvis_hud.py:443-579, 2764-2766 | Sim, mas só visível com ≥ 3 módulos no plano | anel de 15 subsistemas com status real e rótulos FALHA/OFF (scene.py:95-104, 545-553, 705-722; brain_view.py:702-747) | PARCIAL | sem hover, tooltip ou clique |
| P4 | MÓDULOS, clique direito: título desabilitado; voz: "Ativar / pausar escuta", "Reiniciar voz"; AUTOMAÇÃO: "Pausar / retomar automação", "Parar tarefa em execução"; todos: "Copiar detalhes" | jarvis_hud.py:494-501, 2768-2779 | Sim (só quando o painel está visível) | — | AUSENTE | |
| P5 | DIAGNÓSTICO: 3 indicadores circulares (INTEGR. = fração de mic/tts/IA ativos; IA (MS) = 1 − ms/500; sinal do Wi-Fi ou REDE ON/OFF) + forma de onda real do microfone (12 s) | jarvis_hud.py:582-644 | Sim (aparece com TELEMETRIA ou GPT no plano) | latências em Sistemas › DESEMPENHO (panels.py:1476-1491); nível instantâneo do mic no halo | PARCIAL | sem indicadores circulares e sem histórico do mic |
| P6 | REDE E CONEXÕES: interface e IP, Wi-Fi (SSID e sinal), Ollama ONLINE com ms ou OFFLINE, minigráficos ↓/↑ de 60 s, aviso para instalar psutil | jarvis_hud.py:648-707 | Sim (aparece com WEB ou GPT no plano) | módulo NETWORK MESH só no estado NETWORK (scene.py:802-808); Sistemas › REDE LOCAL, inventário de aparelhos (panels.py:1102-1270) | PARCIAL | sem tráfego, Wi-Fi e latência do Ollama |
| P7 | HISTÓRICO DE ATIVIDADE: eventos reais em janelas de 5 s, 44 barras ("ÚLTIMOS 4 MIN"), tooltip "n evento(s) — há X s" | jarvis_hud.py:710-751, 2999-3001, 3020-3022 | Sim (aparece com MEMÓRIA, AUTOMAÇÃO ou ARQUIVOS) | — (métricas só em tabela de DESEMPENHO) | AUSENTE | |
| P8 | CONSOLE DE EVENTOS: 300 entradas "[HH:MM:SS] ▸ texto"; filtro sem diferenciar maiúsculas, com botão de limpar; COPIAR (só as linhas visíveis); LIMPAR | jarvis_hud.py:754-816, 2999-3003 | Sim (aparece com CÓDIGO, WINDOWS, AUTOMAÇÃO, ARQUIVOS ou WEB) | — (registros só no arquivo `logs\ultron.log`: ultron/app.py:61-77) | AUSENTE | |
| P9 | Conversa da INTERFACE DE INTERAÇÃO: até 200 linhas, com horário em cada mensagem: "[HH:MM] VOCÊ ▸", "[HH:MM] J.A.R.V.I.S. ▸" e "// sistema" | jarvis_hud.py:929-932, 988-1000 | Sim | transcrição transitória: as 2 últimas falas centralizadas, resposta "digitada" a 70 caracteres/s, some após ~40 s, sem horário (brain_view.py:1067-1089; scene.py:370, 615-625) | SUBSTITUÍDO | sem rolagem nem histórico |
| P10 | Botões rápidos STATUS ("status do sistema") e HORAS ("que horas são") | jarvis_hud.py:921, 934-939, 2586 | Sim | os comandos existem por voz e texto (ultron/cognition/intent_engine.py:129, 324-325), mas sem botões | AUSENTE | |
| P11 | Botão PARAR: `backend.abort_agent()`, que só age com o agente ocupado; Esc faz o mesmo em THINKING/TOOL_EXECUTION | jarvis_hud.py:941, 2587, 3076-3078; backend.py:889-895 | Sim | só por voz ou texto: "pare" / "cancelar" (intent_engine.py:30-32, 100-101; ultron/core/neural_core.py:381-387); sem botão, e o Esc agora recolhe | PARCIAL | |
| P12 | COPIAR RESPOSTA: última resposta para a área de transferência | jarvis_hud.py:942, 977-979 | Sim | — | AUSENTE | |
| P13 | LIMPAR conversa + atalho Ctrl+L | jarvis_hud.py:943, 965-966 | Sim | — | AUSENTE | |
| P14 | Histórico ↑/↓ das mensagens enviadas (50 itens; guarda o rascunho; não repete a última) | jarvis_hud.py:887-911, 984 | Sim | ultron/hud/window.py:70, 110-130 (50 itens) | PRESERVADO | não guarda rascunho nem evita repetição |
| P15 | Campo de texto + Enter + botão enviar | jarvis_hud.py:951-961 | Sim | window.py:75-78 (Enter; placeholder "Diga "Jarvis" ou digite um pedido…") | PRESERVADO | sem botão gráfico de enviar |
| P16 | Botão de microfone (ícone desenhado; na cor do estado quando o mic está ativo) | jarvis_hud.py:820-853, 953-962, 2761-2762 | Sim | botão MIC alternável + Ctrl+M (window.py:80-82, 208; controller.py:397-399) | PRESERVADO | |
| P17 | Indicador de estado (StateChip): LED pulsante + nome do estado + 5 barras de "voz" | jarvis_hud.py:856-884 | Sim (as barras misturam alvo fixo × ruído com o mic real) | rótulo "ESTADO · MODO" sob o cérebro (brain_view.py:796-817); anel do mic no orbe (orb.py:100-105) | PARCIAL | |
| P18 | AUTOMAÇÃO INTELIGENTE: histórico colorido por tipo + cartão da sugestão pendente (EXECUTAR / CONFIRMAR / ANALISAR / OK, IGNORAR, "(+n)") | jarvis_hud.py:2419-2476 | Interface sim. A **análise de tela está quebrada**: `copilot.py` usa `autonomous_perception` sem importar (copilot.py:892, 902, 939), e cada ciclo grava "erro" (988-992) | Sistemas › AUTONOMIA: autorizações permanentes, histórico de pedidos e registro de ações (panels.py:1271-1396); barra de sugestão SIM/NÃO (window.py:133-185, 204; controller.py:216-219); módulo INSIGHT (scene.py:602-608) | SUBSTITUÍDO | |
| P19 | Barra de automação/observador: modos DESATIVADO / ASSISTENTE / AUTÔNOMO SUPERVISIONADO / OBSERVADOR com diálogos de consentimento; PAUSAR/RETOMAR; PARAR TAREFA; INTERVALO (5–60 s); APPS SEM MONITORAMENTO (n); indicador de monitoramento; botão minimizar | jarvis_hud.py:2261-2416; copilot.py:38-45 | Parcial. O modo OBSERVADOR não tem estilo QSS (jarvis_hud.py:135-143) e **quebra a pintura do botão flutuante**: `MODE_COLORS` não tem "observer" (55-59, 2049). O detalhe de tarefa e de contexto nunca aparece, porque `status_snapshot` não devolve "task" nem "context" (copilot.py:259-261 × jarvis_hud.py:2403-2415). A análise de tela também está quebrada (P18) | nível de autonomia Restrita / Equilibrada / Autônoma (panels.py:1275-1296, 1382-1388); observação da tela liga/desliga por voz ou texto (intent_engine.py:139-142; ultron/core/neural_core.py:502-504); `vision_interval` só nas configurações (ultron/config/settings.py:87) | SUBSTITUÍDO | sem consentimento por diálogo, pausa, intervalo na interface ou indicador |
| P20 | Diálogo APPS SEM MONITORAMENTO: lista, ADICIONAR, REMOVER, FECHAR | jarvis_hud.py:2214-2258, 2898-2900 | Sim | `excluded_apps` existe e é aplicado (settings.py:94; ultron/perception/screen.py:118), mas não há tela para editar | PARCIAL | |
| P21 | Indicador "observação suspensa — HUD aberta" (a HUD informa se cobre a tela) | jarvis_hud.py:2609, 2808-2814; copilot.py:206-208, 888-893 | Sim | o sensor de tela aceita `hud_covering` (ultron/perception/screen.py:86-90, 113), mas o HUD nunca fornece essa informação (padrão `lambda: False`, ultron/core/neural_core.py:106) | AUSENTE | |
| P22 | Barra superior, identidade e estado: mini-reator de 3 arcos girando, "J.A.R.V.I.S." com brilho, "JUST A RATHER VERY INTELLIGENT SYSTEM // MARK VII", LED + estado, linha inferior em gradiente com brilho correndo | jarvis_hud.py:1600-1666, 1712-1720 | Sim (some sozinha quando o cérebro dorme) | "JARVIS" e "CORE · HUB PRINCIPAL" no canto (brain_view.py:988-994); estado sob o cérebro (796-817); manchete central (1004-1016) | PARCIAL | sem mini-reator e sem linha animada |
| P23 | Relógio HH:MM:SS e data em pt-BR ("SEG 01 JAN 2026") | jarvis_hud.py:1643-1651 | Sim | — | AUSENTE | |
| P24 | LEDs MIC/TTS/IA + chips BATERIA, REDE, MODELO e SESSÃO (tempo de execução) | jarvis_hud.py:1668-1710 | Sim | rodapé com modelo e "MIC ON / OFF / —" (brain_view.py:1049-1053; controller.py:208-214) | PARCIAL | sem bateria, SSID, tempo de sessão e LEDs de TTS/IA |
| P25 | Troca de tema clicando no logotipo (x < 340) | jarvis_hud.py:61-97, 1604-1611 | **Vestigial**: `THEMES` tem um só tema ("NEURAL BLUE"); o clique alterna AUTOMÁTICO ↔ NEURAL BLUE sem efeito visível, e o tooltip ainda cita "vermelho, amarelo, azul, roxo" (1604) | tema único deliberado "jarvis-blue" (palette.py:8-13; theme.py:1-15; ultron/config/settings.py:41, 126; ULTRON/CHANGELOG_JARVIS.md:52) | SUBSTITUÍDO | os 4 temas automáticos existiram só em versões antigas (Apêndice A) |
| P26 | Tooltips: estilo escuro global + tooltips por elemento (linhas, barras, nós, botões, botão flutuante) | jarvis_hud.py:155-156, 373-376, 489-492, 728-731, 1375-1379, 1980-1982 | Sim | estilo de QToolTip (theme.py:164); tooltips só em botões e no orbe (window.py:80-92, 158-159; orb.py:35) | PARCIAL | nenhum tooltip com dados |

---

## 4. Janela, bandeja, botão flutuante, atalhos, inicialização

| ID | Recurso | Original (arquivo:linha) | Funcional? | Atual (arquivo:linha) | Status | Observação |
|---|---|---|---|---|---|---|
| W1 | Janela principal sem moldura, sempre no topo, translúcida, ocupando a área útil da tela; título "J.A.R.V.I.S. // MARK VII" | jarvis_hud.py:37, 2480-2486, 2658-2661 | Sim | janela comum "JARVIS — Core", 1320×820 (mínimo 820×540), com moldura (window.py:194-199) | SUBSTITUÍDO | |
| W2 | Expansão e contração animadas: a geometria vai do botão flutuante até a tela (1 s, InOutCubic), com o cérebro compacto desenhado durante a transição | jarvis_hud.py:40-41, 2577-2581, 2642-2731 | Sim | expandir e recolher são instantâneos (controller.py:338-350) | AUSENTE | |
| W3 | Orbe compacto `CompactWidget` (340 px): cérebro sem nós + véu escuro; o clique ativa | jarvis_hud.py:1900-1928 | Sim (aparece nas transições) | `OrbWindow` de 104 px com mini-cérebro na mesma rotação, brilho por estado, anel de profundidade, anel do mic e anel âmbar de autorização (orb.py:18-111; brain_view.py:1092-1110) | PRESERVADO | agora é a forma recolhida permanente |
| W4 | Botão flutuante `FloatingButton` (detalhes na nota abaixo da tabela) | jarvis_hud.py:53-59, 1931-2099, 2598-2603, 2877-2896, 3034-3038; copilot.py:116, 244-251 | Sim, exceto no modo OBSERVADOR (KeyError ao pintar, 2049) | `OrbWindow` (orb.py:23-111): clique duplo expande; arrasta livremente, sem encaixe nem persistência (o sinal `moved` em orb.py:26, 60 não está conectado); botão direito abre o menu da bandeja (controller.py:129); some quando o CORE abre (338-343); sem `WindowDoesNotAcceptFocus` (orb.py:31) | PARCIAL | sem indicadores de modo, pausa, monitoramento e sugestões |
| W5 | Aviso flutuante ao lado do botão `SuggestionToast` (340 px, não rouba o foco): a sugestão some em 14 s e continua pendente; o aviso fica até FECHAR; notificações "Agente JARVIS" | jarvis_hud.py:2102-2211, 2913-2930 | Sim | notificação nativa da bandeja para lembretes e notificações (controller.py:170-173, 407-424); sugestão na barra SIM/NÃO dentro da janela (window.py:204; controller.py:216-219) | SUBSTITUÍDO | |
| W6 | Ícone: a bandeja usa o ícone genérico do Qt (`SP_ComputerIcon`); nenhum `.py` carrega os ícones de `assets/` nem `jarvis_deer.ico` | jarvis_hud.py:2783 | Sim (ícone genérico) | ícone desenhado (disco azul, anel ciano, núcleo) em 9 tamanhos, para app, janela e bandeja (window.py:15-56; controller.py:430, 505) | SUBSTITUÍDO | o README_ICONE_JARVIS.md descreve um uso que o fonte final não tem |
| W7 | Bandeja › "Abrir HUD" | jarvis_hud.py:2789, 2937-2938 | Sim | "Abrir o JARVIS CORE" (controller.py:441) | PRESERVADO | |
| W8 | Bandeja › "Minimizar HUD" | jarvis_hud.py:2790, 2940-2941 | Sim | "Orbe compacto" (controller.py:446) | PRESERVADO | |
| W9 | Bandeja › "Pausar / retomar automação" | jarvis_hud.py:2791 | Sim (interface) | — (o item "Autonomia e autorizações" só abre o painel: controller.py:445) | AUSENTE | |
| W10 | Bandeja › "Ativar / desativar escuta" | jarvis_hud.py:2792 | Sim | "Microfone", marcável (controller.py:448-451); há também "Voz do JARVIS" para silenciar a fala (452-455) | PRESERVADO | |
| W11 | Bandeja › "Configurações" (caixa com modelo, índice do mic e dica de autostart) | jarvis_hud.py:2793, 2943-2950 | Sim | "Sistemas", "Diagnóstico de voz", "Autonomia", "Qualidade visual" e "Diagnóstico" (controller.py:442-445, 456-465, 470-478) | SUBSTITUÍDO | |
| W12 | Bandeja › "Reiniciar voz" | jarvis_hud.py:2794, 2952-2953; backend.py:1103-1119 | Sim | sem item próprio; a captura reabre ao trocar de microfone em Sistemas › VOZ › USAR ESTE (voice_panel.py:45; ultron/voice/processor.py:240-259) e pelo supervisor automático | PARCIAL | |
| W13 | Bandeja › "Iniciar com Windows" (marcável; desfaz a marcação se o Registro falhar) | jarvis_hud.py:2795-2799, 2955-2963 | Sim | — | AUSENTE | a opção existe fora da bandeja (W20) |
| W14 | Bandeja › "Sair" | jarvis_hud.py:2801, 2970-2973, 3083-3092 | Sim | "Sair" (controller.py:467, 480-494) | PRESERVADO | |
| W15 | Clique ou duplo clique na bandeja abre a HUD; cabeçalho "J.A.R.V.I.S." desabilitado; tooltip | jarvis_hud.py:2785-2788, 2803, 2965-2968 | Sim | o clique expande; tooltip "JARVIS"; clicar numa notificação abre TARDIS › notificações (controller.py:431-435) | PRESERVADO | sem cabeçalho no menu |
| W16 | F11 alterna tela cheia; se a HUD não estiver cheia, chama `backend.activate()` | jarvis_hud.py:2592, 3067-3074 | Sim | window.py:206, 237-238 | PRESERVADO | não acorda o assistente |
| W17 | Esc: interrompe o agente em THINKING/TOOL_EXECUTION, senão sai da tela cheia; nunca minimiza | jarvis_hud.py:2593, 3076-3081 | Sim | Esc recolhe para o orbe (window.py:207) | SUBSTITUÍDO | |
| W18 | Fechar a janela = minimizar (o botão flutuante permanece) | jarvis_hud.py:3083-3094 | Sim | esconde e mostra o orbe (window.py:243-249; controller.py:385-389) | PRESERVADO | |
| W19 | Instância única via mutex `Local\JARVIS.PersonalAssistant`; a segunda instância sai em silêncio | backend.py:1122-1142; jarvis_hud.py:3107-3108 | Sim (Windows) | ultron/platform/single_instance.py:14-45; ultron/app.py:313-315 | PRESERVADO | o mutex mudou para `Local\ULTRON.NeuralCore`: original e atual não se bloqueiam e disputariam o microfone |
| W20 | Autostart: HKCU…\Run, valor "JARVIS" = pythonw `jarvis_hud.py --boot`; CLI on/off/status/check; marcação na bandeja | autostart.py:14-96; jarvis_hud.py:2795-2799, 2955-2963 | Sim | ultron/platform/autostart.py:12-92 (valor "JARVIS" = pythonw `main.py --boot`; remove a entrada antiga "ULTRON"); `START_JARVIS.bat --autostart/--no-autostart` (ULTRON/README_JARVIS.md:73); configuração `startup` (ultron/config/settings.py:139; ultron/core/neural_core.py:734-737) | PARCIAL | sem opção na bandeja e sem `check`; o mesmo nome de valor "JARVIS" faz o atual sobrescrever a entrada do original |
| W21 | Log com pythonw: stdout/stderr redirecionados para `jarvis.log`, girado para `jarvis.old.log` acima de 5 MB | jarvis_hud.py:3098-3106 | Sim | RotatingFileHandler `%LOCALAPPDATA%\ULTRON\logs\ultron.log`, 5 MB × 3 (ultron/app.py:61-77) | PARCIAL | sem redirecionar stdout/stderr e sem `excepthook`: com pythonw, tracebacks não capturados se perdem (ex.: erro em `paintEvent`) |
| W22 | Inicia só com o botão flutuante (`start_minimized`); a palavra "Jarvis" expande a HUD | jarvis_hud.py:2865-2871, 3113, 2747-2750 | Sim | por padrão abre o CORE; recolhido só com `--boot` ou `hud_start_minimized` (ultron/app.py:329-330; settings.py:130); expande sozinho em WAKE_WORD ou pedido de autorização (controller.py:44, 180-182) | PARCIAL | |
| W23 | A HUD não se recolhe sozinha (IDLE_TIMEOUT removido; se minimizada no meio de uma tarefa, volta ao ocioso ao terminar) | jarvis_hud.py:38-39, 3029-3033 | Sim | não há temporizador de recolhimento (controller.py) | PRESERVADO | |
| W24 | Scripts `.bat` (detalhes na nota abaixo da tabela) | START_JARVIS.bat, Abrir_JARVIS.bat, INSTALAR_JARVIS.bat, configurar_openai.bat, ATIVAR/DESATIVAR/TESTAR_TELA_JARVIS.bat | Parcial: START_JARVIS quebrado; Abrir_JARVIS só funciona na máquina do autor | ULTRON/START_JARVIS.bat (pythonw; --console, --status, --stop, --diagnose, --autostart…), INSTALL_JARVIS.bat, ATUALIZAR_JARVIS.bat, DIAGNOSTICO_JARVIS.bat (ULTRON/README_JARVIS.md:62-75) | SUBSTITUÍDO | |

**Nota W4, botão flutuante do original**
- Janela de 60 px com máscara circular; sem moldura, sempre no topo, sem roubar o foco.
- Clique = abrir ou minimizar a HUD. Arrastar mais de 6 px move o botão; ao soltar, ele encaixa no canto mais próximo, e o canto fica salvo em `copilot.json`.
- Botão direito abre um menu: Abrir/Minimizar, modos, pausar, parar tarefa, ver sugestão.
- Indicadores: ícone conforme a HUD aberta/fechada, anel vermelho quando a tela está sendo monitorada, ponto de modo, sinal de pausa e contador de sugestões.
- A cada ~1,5 s reafirma "sempre no topo" via `SetWindowPos`.

**Nota W24, scripts `.bat` do original**
- **START_JARVIS.bat** está **quebrado**: `main.py` → `core/runtime.start_gui` → `JarvisBrain.start` → `goal_manager.summary()`, que não existe (core/brain.py:29; goal_manager.py só define create/current/update/finish/history). Falha antes da HUD abrir; ULTRON/ARCHITECTURE_REPORT.md:131 registra o mesmo.
- **Abrir_JARVIS.bat** usa o caminho fixo `C:\Users\pedro\Desktop\JARVIS`, com console visível.
- **INSTALAR_JARVIS.bat** cria o venv Python 3.11 e instala os requirements.
- **configurar_openai.bat** grava com `setx` as variáveis OPENAI_API_KEY, JARVIS_AI_PROVIDER=openai e JARVIS_OPENAI_MODEL=gpt-5.6-sol.
- **ATIVAR/DESATIVAR/TESTAR_TELA** hoje equivalem a ligar/desligar o autostart da HUD e abrir a HUD.

---

## 5. Tela de sessão (PIN)

**O que os documentos descrevem** (README_TELA_JARVIS.md:3-45; LEIA-ME.txt:1-16)
- Tela visual de bloqueio que aparece depois do login do Windows e inicia com a sessão.
- Ocupa a tela inteira e usa o ícone `jarvis_deer.ico`.
- Na primeira execução pede para criar um PIN; nas seguintes pede o PIN.
- **Só depois de autenticar** inicia `jarvis_hud.py`.
- O PIN fica salvo "apenas como hash SHA-256 com salt em `%LOCALAPPDATA%\JARVIS\lock.json`" (README_TELA_JARVIS.md:13).
- Avisa que não substitui Win+L, Ctrl+Alt+Del nem o Winlogon (README_TELA_JARVIS.md:17; LEIA-ME.txt:14-16).
- Uso: `jarvis_lock_setup.py on|off|status` (via ATIVAR/DESATIVAR_TELA_JARVIS.bat) e `jarvis_lock.py` para testar (TESTAR_TELA_JARVIS.bat).

**O que o código realmente faz: são stubs de compatibilidade**
- `jarvis_lock.py` (29 linhas): a docstring diz que "o antigo protetor de sessão foi desativado… sem tela de PIN, sem bloqueio e sem tela de proteção" (1-6). `main()` só executa `subprocess.call([sys.executable, "jarvis_hud.py", "--boot"], cwd=<pasta>)`, de forma bloqueante, e devolve o código de saída (17-25).
- `jarvis_lock_setup.py` (50 linhas) grava em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` o valor **"JARVIS"** = `"<pythonw.exe ao lado do python>" "<pasta>\jarvis_hud.py" --boot` (12-27), com off/status (30-45). É **o mesmo valor** que `autostart.py` usa (autostart.py:14-24), então ATIVAR_TELA hoje só liga o autostart da HUD.

**Verificabilidade**: não existe implementação de PIN em lugar nenhum.
- Nenhum `.py` do export cria `lock.json` nem faz hash de PIN; os únicos usos de `hashlib` são em proactive_assistance.py e autonomous_perception.py, para outros fins.
- O commit `53e5a31` tem as mesmas versões stub e nenhum `.pyc` de `jarvis_lock`.
- `jarvis_deer.ico` existe (6 tamanhos, PNG), mas nenhum `.py` o referencia.
- Portanto, **o formato do `lock.json` (campos), o tamanho do sal, as iterações e o fluxo da tela não podem ser verificados**: resta só a frase do README.
- Recomendação, não evidência: um SHA-256 simples de um PIN curto é fraco contra força bruta offline. Se o recurso voltar, use PBKDF2 ou scrypt com sal aleatório e limite de tentativas.

**Atual**: removida de propósito. ULTRON/ARCHITECTURE_REPORT.md:247 registra "`jarvis_lock*.py`, tela de PIN · removidos · já estavam desativados no legado", e não há nenhuma ocorrência de PIN ou `lock.json` em ULTRON.

| ID | Recurso | Original (arquivo:linha) | Funcional? | Atual | Status | Observação |
|---|---|---|---|---|---|---|
| L1 | Tela de bloqueio: tela cheia, criar/pedir PIN, abrir a HUD só após autenticar | README_TELA_JARVIS.md:5-12; jarvis_lock.py:1-29 (stub) | Não (desativada no próprio original) | — (ULTRON/ARCHITECTURE_REPORT.md:247) | AUSENTE | removida de propósito |
| L2 | `%LOCALAPPDATA%\JARVIS\lock.json` com SHA-256 + sal | README_TELA_JARVIS.md:13 | Não verificável (sem código) | — | AUSENTE | |
| L3 | Início com o Windows pela tela de sessão | jarvis_lock_setup.py:12-50; ATIVAR/DESATIVAR/TESTAR_TELA_JARVIS.bat | Sim, mas aponta direto para a HUD | ultron/platform/autostart.py (mesmo valor Run "JARVIS") | SUBSTITUÍDO | |

---

## 6. Resumo

**Contagem por status** (80 recursos da versão final do original; cópias antigas fora da conta)

| Seção | PRESERVADO | PARCIAL | AUSENTE | SUBSTITUÍDO | Total |
|---|---|---|---|---|---|
| 1. Elementos centrais (C1–C10) | 3 | 4 | 3 | 0 | 10 |
| 2. Estados, efeitos e camadas (S1–S2, E1–E15) | 2 | 4 | 6 | 5 | 17 |
| 3. Painéis e interações (P1–P26) | 3 | 11 | 8 | 4 | 26 |
| 4. Janela, bandeja, botão, atalhos, início (W1–W24) | 10 | 5 | 3 | 6 | 24 |
| 5. Tela de sessão (L1–L3) | 0 | 0 | 2 | 1 | 3 |
| **Total** | **18** | **24** | **22** | **16** | **80** |

**Itens PARCIAL (24)**

*Elementos centrais e efeitos*
- C4 Gênese do cérebro: os nós surgem por fase real de boot, mas sem voo a partir do núcleo e sem sinapses desenhadas progressivamente.
- C5 Núcleo e sinais: sem emissão contínua de faíscas nem frente de onda ao ser chamado.
- C7 Rota Ollama ↔ GPT: só texto (modelo e LOCAL), sem animação de migração.
- C10 Painéis gerados pelo cérebro: módulos nascem de regiões com conector animado, sem partículas e sem os painéis completos.
- E1 Cor de estado: não tinge o HUD inteiro nem interpola.
- E7 Molduras de canto: só nos módulos, não nos cantos da tela.
- E11 Flash: só na resposta pronta, não em toda troca de estado.
- E13 Entrada dos painéis: fade + conector, sem deslize escalonado.

*Painéis e interações*
- P1 Moldura de painel: sem chanfro e sem varredura no título.
- P2 STATUS DO SISTEMA: só texto CPU/RAM/GPU no rodapé + tabela de saúde; sem barras, faixas de cor, rede e tooltips.
- P3 MÓDULOS: o anel de subsistemas mostra o status, mas sem hover nem clique.
- P5 DIAGNÓSTICO: latências em tabela; sem indicadores circulares e sem forma de onda do mic.
- P6 REDE: inventário e módulo NETWORK MESH; sem tráfego, Wi-Fi e latência do Ollama.
- P11 PARAR: só pelos comandos "pare"/"cancelar"; sem botão, e o Esc mudou.
- P17 StateChip: rótulo de estado + anel do mic no orbe; sem LED e barras.
- P20 Apps sem monitoramento: a configuração `excluded_apps` existe, sem tela para editar.
- P22 Barra superior: identidade e estado preservados; sem mini-reator e sem linha animada.
- P24 LEDs e chips: só modelo e estado do MIC; sem bateria, SSID, sessão e LEDs de TTS/IA.
- P26 Tooltips: o estilo foi mantido; nenhum tooltip com dados.

*Janela, bandeja e inicialização*
- W4 Botão flutuante → orbe: duplo clique, sem encaixe/persistência de posição e sem indicadores de modo/monitoramento/sugestões; some com o CORE aberto.
- W12 Reiniciar voz: só indireto (USAR ESTE ou supervisor).
- W20 Autostart: só por `.bat`, CLI ou configuração; sem opção na bandeja e sem `check`.
- W21 Log com pythonw: arquivo com rotação, mas sem capturar stdout/stderr nem exceções não tratadas.
- W22 Inicialização: abre o CORE por padrão; recolhido só com `--boot` ou configuração.

**Itens AUSENTE (22)**

*Elementos centrais*
- C1 Avatar humanoide (já era código morto no original).
- C2 Globo wireframe (já era código morto no original).
- C9 Interação com o núcleo: clique para o microfone, tooltip e clique em nós, inclinação pelo ponteiro.

*Efeitos*
- E3 Grade de 40 px · E4 Scanlines de 3 px · E5 Partículas de fundo · E6 Varredura do fundo · E9 Linha de varredura do overlay.
- E14 Barras que se escondem e reaparecem com o mouse.

*Painéis e interações*
- P4 Menu de clique direito dos MÓDULOS.
- P7 HISTÓRICO DE ATIVIDADE.
- P8 CONSOLE DE EVENTOS (filtro, COPIAR, LIMPAR).
- P10 Botões rápidos STATUS e HORAS.
- P12 COPIAR RESPOSTA.
- P13 LIMPAR conversa + Ctrl+L.
- P21 Indicador "observação suspensa — HUD aberta" (a sonda do HUD nem é ligada: `hud_probe` padrão, ultron/core/neural_core.py:106).
- P23 Relógio e data.

*Janela e bandeja*
- W2 Animação de expansão e contração.
- W9 Bandeja › Pausar/retomar automação.
- W13 Bandeja › Iniciar com Windows.

*Tela de sessão*
- L1 Tela de bloqueio com PIN.
- L2 `lock.json` (SHA-256 + sal), que não é verificável.

**Itens SUBSTITUÍDO de propósito (16)**
- S2 Motores de estado visual → JARVIS_STATE + Event Bus.
- E8 Retícula → órbitas estáticas do anel.
- E10 Barra de atividade → barra de PROFUNDIDADE 0–9.
- E12 Boot 0–100 % → 12 fases ligadas a eventos reais.
- E15 Visualização de áudio → halo pelo mic real e anéis pela voz real.
- P9 Conversa com horário → transcrição transitória.
- P18 Painel AUTOMAÇÃO INTELIGENTE → aba AUTONOMIA + barra SIM/NÃO + módulo INSIGHT.
- P19 Barra de modos do copilot → nível de autonomia + observação por voz.
- **P25 Troca de tema → tema único azul profundo/ciano.** É uma decisão deliberada (ULTRON/CHANGELOG_JARVIS.md:52), e no original final a troca já era vestigial: só havia um tema.
- W1 Janela sem moldura e sempre no topo → janela comum.
- W5 Aviso ao lado do botão → notificação nativa + barra de sugestão.
- W6 Ícone genérico → ícone desenhado.
- W11 Caixa "Configurações" → Sistemas e Diagnóstico.
- W17 Esc → recolher para o orbe.
- W24 Scripts `.bat` → novos scripts.
- L3 Autostart da tela de sessão → autostart atual.

**Itens PRESERVADO (18)**
- Elementos e efeitos: C3 (cérebro de partículas, com a mesma família de malha), C6, C8, S1, E2.
- Interação: P14, P15, P16.
- Janela e bandeja: W3, W7, W8, W10, W14, W15, W16, W18, W19, W23.

**Funcional × incompleto no original (C)**
1. `START_JARVIS.bat`/`main.py` estão **quebrados**: `JarvisBrain.start` chama `goal_manager.summary()`, que não existe (core/brain.py:29). O caminho que funciona é rodar `jarvis_hud.py` direto (Abrir_JARVIS.bat, com caminho fixo, ou a chave Run do autostart).
2. **Observador/automação**: a análise de tela está quebrada por `autonomous_perception` não importado (copilot.py:892, 902, 939), e cada ciclo grava "erro". O modo OBSERVADOR também gera **KeyError ao pintar o botão flutuante** (`MODE_COLORS`, jarvis_hud.py:55-59, 2049) e não tem estilo QSS. O detalhe de tarefa/contexto da barra nunca aparece (copilot.py:259-261).
3. A sequência "INITIALIZING CORE 0–100 %" e a gênese do cérebro contam a partir do início do processo, enquanto a HUD começa oculta; na prática **quase nunca são vistas** (jarvis_hud.py:3024-3026, 2865-2871; neural_core.py:95, 206).
4. **Troca de tema vestigial**: um único tema, e o tooltip cita cinco (jarvis_hud.py:63-70, 1604). A cor "AMBER" da versão final é `#7FE3FF` (ciano claro), não âmbar (50).
5. Os painéis só existem quando o cérebro os materializa (MÓDULOS precisa de 3 ou mais módulos no plano), o que limita a interatividade descrita no CHANGELOG. O clique em nós descreve só 3 de 14. `vstate` mostra VERIFYING ao falar e WAITING no erro.
6. O **avatar não reage ao áudio** (o mic aparece só como texto, 1241), tem código morto e uma assimetria nos braços. Avatar e globo **não são instanciados** na versão final.
7. A **tela de PIN é um stub**: a implementação nunca chegou ao export nem ao git, então o formato do `lock.json` não é verificável. `neural_hud_engine.py` e `live_hud_state.py` não são lidos pela HUD. Os ícones de `assets/` e `jarvis_deer.ico` não são usados no fonte final.
8. **Funcionais pela leitura**: STATUS, MÓDULOS (com menu), DIAGNÓSTICO, REDE, ATIVIDADE, CONSOLE (filtro/COPIAR/LIMPAR), conversa (STATUS/HORAS/PARAR/COPIAR RESPOSTA/LIMPAR, ↑/↓, Ctrl+L, horários), botão flutuante (fora do modo OBSERVADOR), bandeja, F11/Esc, mutex, log com pythonw, início minimizado, fechar = minimizar e autostart. Nenhum desses itens foi validado em tela real.

**Notas de método**: análise estática, sem nada executado. O repositório não foi alterado (`git status` vazio). Durante a auditoria criei dois arquivos temporários no scratchpad com strings de `.pyc`; eles já foram removidos e só este relatório permanece.

---

## Apêndice A — Recursos que só existiam em versões antigas (não contados)

- **Reator circular "NEURAL CORE // SIM"** (jarvis_hud_BACKUP_FUNCIONANDO.py:572-754; idêntico em jarvis_hud_ANTES_DA_INTERFACE_REAL.py): varredura cônica, anéis tracejados, 120 marcas, arcos segmentados com 5 raios e velocidades, divisões radiais, hexágono e triângulo girando, ondas de energia, **anel de áudio simulado** (`anim.voice` × senos), "bits" ao pensar, 70 partículas orbitais e centro luminoso. Os textos "FREQ x THz", "THRU" e "PHASE" eram inventados. Atual: ausente.
- **4 temas que trocavam sozinhos a cada 19 s** (14 s parado + 5 s de transição): vermelho `#FF2A3D` → amarelo `#FFC21A` → azul `#2D5BFF` → roxo `#A63DFF` (_backup_antes_do_copilot/jarvis_hud.py:47-79). A trava por clique no logotipo só existiu na versão "holograma" (CHANGELOG_HUD_HOLOGRAMA.md:21), cujo backup não está no export. Atual: tema único.
- **Recolhimento automático após 7 s ocioso** (`IDLE_TIMEOUT = 7`, jarvis_hud_BACKUP_FUNCIONANDO.py:31, 1317): removido de propósito (LEIA-ME_ATUALIZACAO_HUD_COPILOT.md:17). O atual também não recolhe sozinho.
- **Ícone oficial carregado** em janela, bandeja e botão flutuante (`JARVIS_ICON_PATH`, `JARVIS_FAB_PNG`, `setWindowIcon`): existe só no bytecode `JARVIS/__pycache__/jarvis_hud.cpython-313.pyc` do commit `53e5a31`, uma versão intermediária com copilot e 4 temas, sem avatar e sem overlay. O fonte final não tem esse código. Atual: ícone procedural.
- **Indicadores SYSTEM/CORE/PERCEPTION/VERIFICATION** do overlay (README_FASE_12_HUD_CINEMATIC.md:10): removidos no próprio original (jarvis_hud.py:1869-1870).
- **Tkinter `interface.py`**: HUD de 1200×700 com título, núcleo pulsante (2 anéis, núcleo e 8 pontos orbitando), painéis "SYSTEM STATUS" e "JARVIS LOG" com **valores fixos**, relógio e linhas (interface.py:66-181, 209-485). `Jarvis.py` não tem interface gráfica. Ambos foram substituídos.

## Apêndice B — Recursos do atual sem equivalente no original (contexto)

- TARDIS, a memória espacial (ultron/hud/tardis.py).
- Painel de Sistemas com VOZ (diagnóstico em 8 etapas, calibração, escolha de microfone), REDE LOCAL, AUTONOMIA e DESEMPENHO (ultron/hud/systems_panel.py:14-40).
- Barra de autorização AUTORIZAR / NEGAR / SEMPRE (24 h), com contagem regressiva no módulo (window.py:133-185; brain_view.py:913-919).
- Perfis de qualidade visual com fps adaptativo (ultron/hud/quality.py).
- Atalhos Ctrl+M, F2 e F3 (window.py:208-210); silenciar a fala do JARVIS ("VOZ"); `--status` e `--stop` pela linha de comando (ultron/platform/control.py).
