# Testes

| Suíte | Comando | O que cobre |
|---|---|---|
| Unitários | `npm run test` | regras de dados (chaves, cascata, unicidade), 20 disciplinas, backup .zip, progresso, datas, materiais (envio/versões/exclusão), scanner (salvamento idempotente), contrato da IA, processamento de imagem (perspectiva, sombras, detecção), atualização do banco local v1→v2 |
| Banco real | `npm run test:db` | migrações, RLS, chaves compostas, Storage privado, upload de PDF/DOCX/PPTX/imagem, versões, scanner, HEIC, backup local → nuvem com arquivos |
| Ponta a ponta | `npm run test:e2e` | fluxos completos: modo local, biblioteca, scanner, **câmera** (concedida e negada), celular |
| Ponta a ponta (nuvem) | ver abaixo | cadastro, login, biblioteca e scanner com Supabase real |

### Câmera nos testes

O Chromium usa uma **câmera falsa** que transmite um vídeo sintético de uma página
de caderno (gerado em `tests/e2e/fixtures/images.ts`, nenhuma foto real):
- projetos `camera` e `camera-celular`: permissão concedida — fotografa várias
  páginas, verifica o recorte automático e salva;
- projeto `camera-negada`: Chromium completo com a câmera **bloqueada** para o site
  (o navegador devolve `NotAllowedError`) — verifica a orientação e as alternativas.

## Supabase local de teste (Docker)

`tests/supabase-local/` contém um Supabase mínimo — PostgreSQL (`supabase/postgres`),
Auth (GoTrue), PostgREST e Storage — e um gateway HTTP (`gateway.mjs`) que faz o
papel do Kong (rotas `/auth/v1`, `/rest/v1`, `/storage/v1`, CORS).

```bash
npm run supabase:local:up
```
```bash
npm run test:db
```

E2E no modo nuvem (o Playwright sobe o gateway e um app apontando para o Supabase local):
```bash
E2E_SUPABASE=1 E2E_SUPABASE_ANON_KEY=$(node -e "import('./tests/supabase-local/keys.mjs').then(m=>console.log(m.ANON_KEY))") npm run test:e2e
```

Para apagar os dados de teste e recomeçar: `npm run supabase:local:reset`.
As chaves desse ambiente são fixas e **servem só para testes locais**.

## Resultado da última execução (Fase 3)

- Unitários + banco real: **77/77** ✔
- E2E: **25/25** ✔ — local (biblioteca, scanner, fluxos anteriores), celular,
  câmera (desktop e celular), câmera negada e nuvem (Supabase).
- Build de produção conferido: visualizadores e Web Worker carregam sob demanda.
