# Testes

| Suíte | Comando | O que cobre |
|---|---|---|
| Unitários | `npm run test` | regras de dados no adaptador local (chaves, cascata, unicidade), cadastro das 20 disciplinas, backup, progresso, datas |
| Banco real | `npm run test:db` | migrações, RLS entre usuários, chaves compostas, SET NULL, erros traduzidos, Storage privado, migração local → nuvem |
| Ponta a ponta | `npm run test:e2e` | fluxos completos no navegador (modo local + celular) |
| Ponta a ponta (nuvem) | ver abaixo | cadastro, login, persistência e logout com Supabase real |

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

## Resultado da última execução

- Unitários: 22/22 ✔
- Banco real: 15/15 ✔
- E2E: 11/11 ✔ (local 9, celular 1, Supabase 1). O fluxo da nuvem foi repetido 12
  vezes seguidas sem falhas, sem respostas 401/403/5xx nem erros no console.
