# Design system do SAFRA (desktop, cena 3D, ORBE e web)

**Fonte única:** `ultron/hud/design/tokens.json`. O CSS da cena 3D e da web é gerado dele
(`python tools/gerar_tokens.py` → `ultron/hud/scene3d/web/css/tokens.css`); a paleta do Qt
(`ultron/hud/palette.py`, de onde `theme.py` gera as folhas de estilo) e a paleta 3D (`web/js/materials.js`) usam
os mesmos valores — `tests/test_scene3d.py` (`DesignTokensTest`) falha se alguém divergir.

> Histórico: até a versão 2 (JARVIS) a identidade era azul/ciano. A versão 3 (SAFRA) é vermelha. As decisões e
> o mapeamento das cores estão em `docs/technical/RELATORIO_TECNICO.md` (decisões D2–D4).

## Cores

| Token | Valor | Uso | Contraste sobre `space` |
|---|---|---|---|
| `space` | `#07070A` | fundo (preto) | — |
| `abyss` / `deep` / `graphite` | `#0F1013` / `#17181C` / `#23252B` | camadas, superfícies, superfícies elevadas | — |
| `muted` | `#5C1A24` | contornos e estados apagados (bordô escuro) | — |
| `wine` | `#7A0F1F` | bordô: repouso, profundidade | — |
| `primary` | `#EA2840` | **vermelho SAFRA**: atividade, escuta, dados em movimento, holograma | 4,67:1 (títulos e texto grande) |
| `glow` | `#FF5C6C` | brilho, destaque, fala, confirmação | 6,7:1 |
| `energy` | `#FF3B6B` | vermelho-framboesa: pensar, planejar, executar | 5,8:1 |
| `text` / `dim_text` | `#F4F4F5` / `#A1A1AA` | texto principal (branco) e secundário (cinza) | 18,3:1 / 7,9:1 |
| `alert` | `#F7C948` | âmbar: atenção, autorização pendente | 12,8:1 |
| `error` | `#FF7B1C` | laranja: falha real (fora da família do vermelho, para não se confundir com a identidade) | 7,8:1 |
| `ultron`, `ultron_glow`, `ultron_deep`, `ultron_metal` | `#8B5CF6`, `#B794FF`, `#1C0F33`, `#A9B0BC` | **somente** o Protocolo ULTRON (violeta e cromo) | — |
| `state.online/offline/pending/failed` | verde, cinza, âmbar, laranja | indicadores de conexão (web e desktop) | — |

Contrastes calculados pela fórmula da WCAG 2.1 (`palette.contrast`); o teste de identidade confere o mínimo de
4,5:1 para o texto principal e secundário.

## Regras

* **Geometria:** cantos quase retos (`radius.s` 2 px; `m` 6 px), filete vermelho à esquerda dos painéis de vidro,
  marcador de estado em losango. Sem caixas dentro de caixas.
* **Tipografia:** `font.family` (Segoe UI no Windows); rótulos em maiúsculas com `label_spacing`; tamanhos
  `xs` 10 · `s` 12 · `m` 15 · `l` 20 px.
* **Vidro:** painéis grafite translúcidos (`glass.fill`, borda `glass.edge`, desfoque `glass.blur`).
* **Estados:** cor + texto sempre juntos (nunca só cor). Indicador ativo só com dado real; sem dado, "—" ou o
  motivo.
* **Movimento:** `motion.fast` 140 ms (hover), `base` 280 ms (trocas), `slow` 560 ms (estado); `ease` comum.
  Nada pisca em loop sem um evento real por trás; respeitar o perfil Econômico e "efeitos pesados".
* **Âmbar** é atenção/autorização; **laranja** é falha real; **violeta** é ULTRON. O vermelho é a identidade —
  nunca usado sozinho para indicar erro. Demonstrações levam o aviso "DEMONSTRAÇÃO".
* **TARDIS:** a cabine externa mantém o azul da nave (identidade preservada); o interior usa o latão e o âmbar dos
  roundels com a energia e as telas em vermelho SAFRA.
* **Legibilidade antes do efeito:** brilho e partículas nunca passam por cima de texto; contraste do texto
  principal ≥ 4,5:1.
