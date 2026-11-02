# Design system do JARVIS (desktop, cena 3D, ORBE e web)

**Fonte única:** `ultron/hud/design/tokens.json`. O CSS da cena 3D e da web é gerado dele
(`python tools/gerar_tokens.py` → `ultron/hud/scene3d/web/css/tokens.css`); a paleta do Qt
(`ultron/hud/palette.py`) e a paleta 3D (`web/js/materials.js`) usam os mesmos valores — `tests/test_scene3d.py`
(`DesignTokensTest`) falha se alguém divergir.

## Cores

| Token | Valor | Uso |
|---|---|---|
| `space` | `#030712` | fundo (preto azulado) |
| `abyss` / `deep` | `#071426` / `#0B1F3A` | painéis, camadas |
| `tech` | `#075985` | contornos, estados apagados |
| `cyan` | `#00D9FF` | identidade do JARVIS: atividade, dados, holograma |
| `glow` | `#67F3FF` | brilho, destaque, íris |
| `electric` | `#168BFF` | pensar/executar, energia secundária |
| `ice` | `#DCEEFF` | texto (branco azulado) |
| `dim_text` | `#7F9BB7` | texto secundário |
| `alert` | `#FFB547` | âmbar: alertas, autorização pendente, TARDIS |
| `error` | `#FF5D73` | falha real |
| `ultron`, `ultron_wine`, `ultron_metal`, `ultron_glow` | `#FF1F3D`, `#4A0712`, `#8C929C`, `#FF5A6B` | **somente** o Protocolo ULTRON |
| `state.online/offline/pending/failed` | verde, cinza, âmbar, coral | indicadores de conexão (web e desktop) |

## Regras

* **Tipografia:** `font.family` (Segoe UI no Windows); rótulos em maiúsculas com `label_spacing`; tamanhos
  `xs` 10 · `s` 12 · `m` 15 · `l` 20 px.
* **Vidro:** painéis translúcidos (`glass.fill`, borda `glass.edge`, desfoque `glass.blur`), raio `radius.m`,
  sem caixas dentro de caixas.
* **Estados:** cor + texto sempre juntos (nunca só cor). Indicador ativo só com dado real; sem dado, "—" ou o
  motivo.
* **Movimento:** `motion.fast` 160 ms (hover), `base` 300 ms (trocas), `slow` 600 ms (estado); `ease`
  comum. Nada pisca em loop sem um evento real por trás; respeitar perfil Econômico e "efeitos pesados".
* **Âmbar** é para alerta/autorização/TARDIS; **vermelho** é falha real ou ULTRON (rotulado como evento
  visual). Demonstrações levam o aviso "DEMONSTRAÇÃO".
* **Legibilidade antes do efeito:** brilho e partículas nunca passam por cima de texto; contraste do texto
  principal sobre o vidro ≥ 4,5:1.
