# Arquitetura

## Visão geral

```
┌──────────────────────── Navegador (React SPA na Netlify) ───────────────────────┐
│  features/ (páginas)  →  data/hooks.ts (TanStack Query)  →  data/services/       │
│                                                     │                            │
│                                     DataBackend (interface única)                │
│                                  ┌──────────┴───────────┐                        │
│                          SupabaseBackend            LocalBackend                 │
└──────────────────────────────────┼───────────────────────┼───────────────────────┘
                                   │ HTTPS + JWT do usuário │ IndexedDB (Dexie)
                      ┌────────────┴────────────┐           (modo local)
                      │ Supabase                │
                      │  Auth · PostgREST · RLS │
                      │  PostgreSQL · Storage   │
                      └────────────┬────────────┘
                                   │ (Fase 7)
                      Netlify Functions ── API da Anthropic (chave só no servidor)
```

## Stack

| Camada | Tecnologia | Motivo |
|---|---|---|
| UI | React 19, TypeScript (strict), Vite 8 | padrão moderno, tipagem forte |
| Estilo | Tailwind CSS v4 + tokens CSS (`src/index.css`) | tema claro/escuro por variáveis, sem duplicar estilos |
| Componentes | Radix UI (diálogo, menus, dicas) + kit próprio (`components/ui`) | acessibilidade (teclado, leitores de tela) |
| Rotas | React Router 7 | URLs próprias para cada disciplina, prova e aba |
| Dados | TanStack Query | cache, novas tentativas em falhas de rede, atualização após cada alteração |
| Formulários | react-hook-form + zod | mesma validação na tela e nos serviços |
| Banco | Supabase (PostgreSQL 15+/17, Auth, Storage) | RLS por usuário, bucket privado |
| Modo local | Dexie (IndexedDB) | uso imediato sem servidor; **não** usa localStorage como banco |
| Hospedagem | Netlify (`netlify.toml` na raiz do repositório) | SPA + cabeçalhos de segurança |
| Visualizadores | pdf.js (PDF), docx-preview (Word) — carregados sob demanda | PDF funciona também no celular (o Chrome do Android não exibe PDF embutido) |
| Compactação | fflate | backup .zip com arquivos; download das páginas do caderno |

## Camada de dados

Toda a aplicação conversa com uma única interface, `DataBackend`
(`src/data/backend/types.ts`): `list`, `get`, `count`, `insert`, `insertMany`,
`update`, `remove` e `storage` (upload, download, URL, remoção).

- **`SupabaseBackend`** — modo principal. Traduz erros do PostgreSQL para mensagens
  em português (`mapPostgrestError`), pagina leituras grandes e usa URLs assinadas
  para arquivos.
- **`LocalBackend`** — ativo quando o Supabase não está configurado. Reproduz as
  regras do banco a partir de `relations.ts`: chaves estrangeiras (inclusive
  compostas), cascata, `SET NULL` e unicidade. Os mesmos cenários são testados nos
  dois adaptadores.

Os **serviços** (`src/data/services/`) concentram as regras de negócio e validam a
entrada com os esquemas zod de `schemas.ts`, cujos limites espelham as restrições
`CHECK` do SQL.

## Banco de dados

Migrações em `supabase/migrations/` (aplicar em ordem). 20 tabelas:

| Grupo | Tabelas |
|---|---|
| Organização | `profiles`, `academic_years`, `subjects`, `exams`, `exam_topics` |
| Biblioteca | `materials` (arquivo, link ou caderno digitalizado), `material_versions` (arquivos substituídos) |
| Resumos | `summaries`, `summary_versions`, `summary_sources` |
| Aprendizado | `flashcards`, `flashcard_reviews`, `questions`, `quizzes`, `quiz_attempts` |
| Planejamento | `study_sessions`, `calendar_events` |
| Scanner | `notebook_scans`, `notebook_scan_pages` |
| IA | `ai_operations` (registro de consumo; escrita só pelo servidor) |

### Regras de integridade

- **Isolamento por usuário**: todo registro tem `user_id` (padrão `auth.uid()`) e
  chaves compostas `(pai_id, user_id)` — é impossível referenciar dados de outra conta.
- **Não misturar provas**: `materials`, `summaries`, `flashcards`, `questions`,
  `quizzes`, `study_sessions`, `calendar_events` e `notebook_scans` referenciam
  `(exam_id, subject_id)`. O banco recusa vincular um item a uma prova de outra disciplina.
- **Preservar materiais**: excluir uma prova apaga conteúdos, flashcards, questões,
  simulados e eventos, mas **mantém materiais e resumos** na disciplina
  (`ON DELETE SET NULL (exam_id)`).
- **Mover prova de disciplina** só é permitido se não houver itens vinculados a ela.
- **Unicidade**: um nome de disciplina por ano letivo; um ano letivo ativo por usuário.
- **Código institucional**: `NULL` significa "a confirmar" — nunca é inventado.
- **Caderno digitalizado**: o material `digitalizacao` aponta para `(scan_id, subject_id)` — a
  digitalização e o material pertencem obrigatoriamente à mesma disciplina.

### Segurança

- **RLS** em todas as tabelas: `user_id = auth.uid()` para leitura e escrita.
- O papel `anon` (sem login) não tem acesso a nenhuma tabela.
- `ai_operations`: o usuário só **lê**; apenas o servidor (service role) grava.
- **Storage**: bucket privado `materiais`, arquivos em `<user_id>/…`, políticas que
  restringem cada usuário à própria pasta, limite de 50 MB e tipos permitidos
  (PDF, DOCX, PPTX, TXT, PNG, JPEG, WEBP).
- O frontend recebe apenas a chave **pública**; se uma chave secreta for configurada
  por engano, o app bloqueia a inicialização.

## Progresso

Calculado em `src/lib/progress.ts` a partir do status de cada conteúdo
(não estudado 0 · estudando ⅓ · revisado ⅔ · dominado 1). O progresso geral e o de
cada disciplina consideram apenas provas **pendentes**. Sem conteúdos, o progresso é
"—" (sem dados), nunca 0%. Flashcards e simulados entram no cálculo na Fase 5.

## Integração com IA (planejada — Fase 7)

- **Netlify Functions** recebem as requisições do app com o JWT do usuário, validam
  a sessão no Supabase, verificam limites de uso e chamam a API da Anthropic.
- `ANTHROPIC_API_KEY` e `SUPABASE_SERVICE_ROLE_KEY` existem **somente** no servidor.
- Cada chamada é registrada em `ai_operations` (operação, modelo, tokens, custo
  estimado, erro), permitindo controle de consumo.
- O modelo é configurável (`ANTHROPIC_MODEL`).
- Respostas estruturadas (JSON validado) separam **conteúdo do professor**,
  **explicação complementar** e **fonte externa**, e marcam trechos de baixa confiança.
- **Modo manual** (Fase 4, sem API): exportar materiais, copiar prompts prontos e
  importar resumos/questões produzidos no Claude.

## Biblioteca (Fase 3)

- **Envio**: o arquivo vai primeiro ao Storage e só então o registro é criado; se o
  registro falhar, o arquivo é removido (nada fica órfão). Tipo identificado pela
  extensão quando o celular não informa o MIME; o Blob é reetiquetado com o tipo
  correto antes do envio (exigência do bucket).
- **Caminhos**: `<user>/<disciplina>/materiais/<material>/v<versão>-<nome-seguro>` —
  o primeiro segmento é o usuário (verificado pelas políticas do bucket).
- **Substituição**: o arquivo atual é registrado em `material_versions` e continua
  disponível; o material passa a apontar para o novo arquivo (versão + 1).
- **Exclusão**: remove registro, versões e arquivos (inclusive fotos de cadernos).
- **Visualização**: arquivos são baixados pela sessão do usuário (bucket privado);
  "Abrir" usa URL assinada temporária.
- **Backup v2 (.zip)**: `backup.json` + `arquivos/…`. Na importação, os caminhos são
  transferidos para a pasta do usuário atual e cada arquivo é enviado antes do
  registro que aponta para ele. Backups v1 (.json) continuam aceitos.

## Scanner de cadernos (Fase 3) e leitura por IA (Fase 7)

Detalhes em [`SCANNER.md`](SCANNER.md). Resumo: captura (câmera ao vivo, câmera do
sistema, galeria), processamento no aparelho em Web Worker (perspectiva, iluminação,
detecção automática), rascunho em IndexedDB, salvamento idempotente com a foto
**original** e a versão tratada, e o contrato de dados (`src/data/ai/scanReading.ts`)
que a Fase 7 usará para enviar as imagens a um modelo multimodal — nada de IA é
simulado.
