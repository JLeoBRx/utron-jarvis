# Scanner de cadernos — "Fotografar meu caderno"

## Como usar

1. Abra **Fotografar meu caderno** pelo Dashboard, por uma disciplina, pela aba
   *Materiais* de uma prova ou pela Biblioteca. Quando aberto dentro de uma
   disciplina/prova, esses campos já vêm preenchidos.
2. Escolha como capturar:
   - **Abrir câmera**: câmera ao vivo dentro do app, para fotografar várias páginas
     em sequência (com lanterna e troca de câmera quando o aparelho permite);
   - **Escolher da galeria**: várias fotos de uma vez;
   - **Usar o aplicativo de câmera do aparelho**: abre a câmera nativa do celular.
3. Cada foto é analisada no próprio aparelho: a folha é **detectada e recortada
   automaticamente** quando há segurança (folha clara sobre fundo mais escuro).
4. Toque numa página para editar: **girar**, **recortar arrastando os 4 cantos**
   (com correção de perspectiva), **detectar página**, **página inteira**,
   iluminação (**Original · Realçar · Documento · P&B**), brilho e contraste.
5. Reordene (‹ ›), exclua ou adicione páginas.
6. **Revisar e salvar**: confira todas as páginas, escolha disciplina, prova
   (opcional) e o nome do assunto, e salve.

O caderno vira um material do tipo **Caderno** na Biblioteca (e na aba *Materiais*
da prova), com as páginas na ordem escolhida, a versão tratada e a **foto
original**.

### Rascunho automático

Enquanto você fotografa, as páginas ficam salvas **no próprio aparelho**. Se a aba
fechar, o celular recarregar ou a bateria acabar, ao abrir o scanner de novo
aparece "Rascunho recuperado". O rascunho é apagado ao salvar (ou em
*Descartar rascunho*).

### Permissão da câmera

| Situação | O que o app faz |
|---|---|
| Permissão concedida | Câmera ao vivo |
| Permissão negada (ou bloqueada antes) | Explica como liberar (Android/Chrome e iPhone/Safari) e oferece **Tentar novamente**, **câmera do sistema** e **galeria** |
| Sem câmera / câmera em uso por outro app | Mensagem específica + alternativas |
| Página sem HTTPS | Câmera do navegador indisponível → câmera do sistema e galeria (na Netlify o site é HTTPS) |

O cabeçalho `Permissions-Policy: camera=(self)` (em `netlify.toml`) permite a
câmera apenas para o próprio site.

### Fotos do iPhone (HEIC)

O seletor de imagens do Safari normalmente converte HEIC para JPEG. Se chegar um
HEIC, o **original é guardado** (o bucket aceita HEIC/HEIF); navegadores que não
conseguem abrir HEIC mostram um aviso para enviar em JPEG ("Mais compatível").

---

## Como funciona (técnico)

```
foto (câmera/galeria) ──► ORIGINAL intocado ─────────────────────────────┐
        │                                                                  │
        └► decodificar (respeita EXIF) → imagem-base 1400 px               │
              ├► detecção da folha (Otsu + maior região clara + cantos)    │
              └► Web Worker: girar → recortar/perspectiva → iluminação     │
                          → brilho/contraste → prévia                      │
salvar ─► versão final (original lido em até 3200 px → tratada 2400 px JPEG)│
        ─► Storage:  <user>/<disciplina>/cadernos/<scan>/<página>-original.* ◄┘
                     <user>/<disciplina>/cadernos/<scan>/<página>-tratada.jpg
        ─► notebook_scans (status "capturado") + notebook_scan_pages (ordem,
           dimensões, edições aplicadas) + materials (kind "digitalizacao")
```

| Arquivo | Responsabilidade |
|---|---|
| `src/features/scanner/imaging/geometry.ts` | quadriláteros, homografia (8×8), rotação de pontos |
| `.../imaging/raster.ts` | girar, reduzir (média de área), correção de perspectiva bilinear |
| `.../imaging/enhance.ts` | realce automático, remoção de sombras (mapa de iluminação com dilatação + suavização), P&B suave |
| `.../imaging/detect.ts` | detecção da folha e nível de confiança (só recorta sozinho com confiança ≥ 0,75) |
| `.../imaging/worker.ts` | processamento fora da thread principal (tela não trava) |
| `.../CameraCapture.tsx` | câmera ao vivo (`getUserMedia`, `ImageCapture.takePhoto` quando disponível) |
| `.../PageEditor.tsx` | editor (cantos arrastáveis por toque, mouse ou teclado) |
| `.../useScannerPages.ts` / `draftStore.ts` | páginas, prévias e rascunho em IndexedDB |
| `src/data/services/scans.ts` | salvamento **idempotente** (repetir após falha não duplica) e cancelamento limpo |

Tudo é feito no aparelho — nenhuma foto sai para serviços de terceiros.

---

## Preparação para a leitura por IA (Fase 7)

Implementado agora (sem chamar nenhum modelo):

- **Dados prontos**: originais intocados + versões tratadas no Storage privado,
  ordem das páginas, dimensões, origem (câmera/galeria) e edições aplicadas em
  `notebook_scan_pages`; status da digitalização (`capturado` → `processando` →
  `aguardando_revisao` → `revisado` → `concluido` / `erro`).
- **Contrato** em `src/data/ai/scanReading.ts`:
  - `SCAN_READING_INSTRUCTIONS` — regras de fidelidade (não inventar, não alterar
    números, marcar trechos ilegíveis, fórmulas em LaTeX, separar complementos);
  - `buildScanReadingRequest()` — monta o pedido com as páginas na ordem (imagem
    tratada para leitura + original para conferência);
  - `scanReadingResultSchema` — formato **obrigatório** da resposta (blocos por
    página com tipo, conteúdo, confiança e incerteza; assuntos; fórmulas; pontos
    para revisão) e `scanReadingJsonSchema()` para *structured outputs*;
  - `parseScanReadingResult()` — rejeita respostas fora do contrato ou que citem
    páginas inexistentes.
- **Modo manual** (já funciona): no caderno salvo, *Baixar páginas (.zip)* e
  *Copiar instruções de leitura* para usar no Claude.

Na Fase 7, uma função no servidor (Netlify) receberá o `scan_id` com o JWT do
usuário, lerá as imagens com a chave de serviço, chamará o modelo multimodal com
o pedido acima, validará a resposta, registrará o consumo em `ai_operations` e
gravará o resultado em `notebook_scans.recognized` / `notebook_scan_pages`,
levando a digitalização para "aguardando sua conferência".
