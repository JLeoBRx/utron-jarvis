# Central de Estudos

Plataforma pessoal de organização escolar e preparação para provas.

```
ANO LETIVO → DISCIPLINA → PROVA → CONTEÚDOS → MATERIAIS → RESUMOS
           → FLASHCARDS → EXERCÍCIOS → SIMULADOS → RESULTADOS
```

## Estado atual (Fases 1, 2 e 3 concluídas)

| Disponível agora | Próximas fases |
|---|---|
| Dashboard com indicadores reais, próximas provas, preparação por disciplina e atividades | Resumos com versões e modo manual de IA (Fase 4) |
| 20 disciplinas oficiais (Formação Geral / Técnica), com busca, filtros, edição e arquivamento | Flashcards, exercícios, simulados e desempenho (Fase 5) |
| Provas: cadastro, filtros, página própria com 8 abas, status, prioridade, nota | Calendário e metas (Fase 6) |
| Conteúdos por prova, com status de estudo, anotações e reordenação | PDFs e leitura/geração com Claude (Fase 7) |
| **Biblioteca**: PDF, DOCX, PPTX, TXT, imagens e links; visualização, download, substituição preservando o original, filtros | Testes finais e publicação (Fase 8) |
| **Fotografar meu caderno**: câmera ao vivo, galeria, recorte com perspectiva, iluminação, reordenação, rascunho automático | |
| Banco PostgreSQL (Supabase) com RLS **ou** modo local (IndexedDB); backup .zip com arquivos | |

Veja o checklist completo em [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Começar

```bash
npm install
```
```bash
npm run dev
```
Abra <http://localhost:5173>. Sem configuração, o app roda em **modo local**.
Para usar a nuvem (Supabase) e publicar na Netlify, siga
[`docs/CONFIGURACAO.md`](docs/CONFIGURACAO.md).

## Scripts

| Comando | Descrição |
|---|---|
| `npm run dev` | servidor de desenvolvimento |
| `npm run build` | checagem de tipos + build de produção (`dist/`) |
| `npm run test` | testes unitários (Vitest) |
| `npm run test:db` | testes de integração com Supabase real (requer Docker) |
| `npm run test:e2e` | testes de ponta a ponta (Playwright) |
| `npm run supabase:local:up` | sobe o Supabase local de teste (Docker) e aplica as migrações |
| `npm run db:migrate` | aplica as migrações em um banco (`DATABASE_URL`) |

Detalhes em [`docs/TESTES.md`](docs/TESTES.md).

## Documentação

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — stack, camadas, banco de dados, segurança, biblioteca e plano da IA
- [`docs/SCANNER.md`](docs/SCANNER.md) — uso e funcionamento do “Fotografar meu caderno” e o contrato para a leitura por IA
- [`docs/CONFIGURACAO.md`](docs/CONFIGURACAO.md) — Supabase, Netlify e variáveis de ambiente
- [`docs/TESTES.md`](docs/TESTES.md) — como testar
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — tarefas concluídas e pendentes

## Estrutura

```
central-de-estudos/
├── supabase/migrations/   esquema SQL, RLS e Storage
├── src/
│   ├── app/               providers, rotas, sessão, tema, menu
│   ├── components/        ui/ (kit), layout/ (shell), domain/ (selos, tags)
│   ├── data/
│   │   ├── ai/            contrato da leitura de cadernos por IA (Fase 7)
│   │   ├── backend/       interface única + adaptadores Supabase e local
│   │   ├── services/      regras de negócio (disciplinas, provas, backup…)
│   │   ├── seed/          as 20 disciplinas oficiais
│   │   ├── schemas.ts     validação (zod) = restrições do banco
│   │   └── types.ts       tipos das tabelas
│   ├── features/          páginas (dashboard, disciplinas, provas, biblioteca, scanner, …)
│   │   └── scanner/imaging/  processamento de imagem (perspectiva, iluminação, detecção)
│   └── lib/               datas, progresso, cores, erros, utilitários
├── tests/
│   ├── db/                integração com Supabase real
│   ├── e2e/               Playwright (local, celular, Supabase)
│   └── supabase-local/    Supabase mínimo em Docker para testes
└── docs/
```
