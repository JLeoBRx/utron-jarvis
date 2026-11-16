# Configuração — Supabase e Netlify

Sem nenhuma configuração, a Central de Estudos funciona em **modo local**: os dados
ficam no banco do navegador (IndexedDB) daquele dispositivo. Para usar o **banco na
nuvem** (sincronizado, com login e backup no servidor), siga os passos abaixo.

> Tempo estimado: 15 minutos. Custo: o plano gratuito do Supabase e da Netlify atende
> ao uso pessoal.

---

## 1. Criar o projeto no Supabase

1. Acesse <https://supabase.com>, crie uma conta e clique em **New project**.
2. Escolha um nome (ex.: `central-de-estudos`), uma senha forte para o banco e a
   região mais próxima (ex.: *South America (São Paulo)*).
3. Aguarde o projeto ficar pronto.

## 2. Criar as tabelas (aplicar as migrações)

As migrações estão em `supabase/migrations/` e devem ser aplicadas **nesta ordem**:

| Ordem | Arquivo | O que faz |
|---|---|---|
| 1 | `20261116120000_esquema_inicial.sql` | 19 tabelas, chaves, índices e políticas RLS |
| 2 | `20261116120100_storage_materiais.sql` | bucket privado `materiais` e suas políticas |

Escolha **uma** das formas:

**A) Pelo painel (mais simples)**
1. No Supabase, abra **SQL Editor → New query**.
2. Cole o conteúdo do arquivo 1 e clique em **Run**. Repita com o arquivo 2.

**B) Pela Supabase CLI**
```bash
npx supabase link --project-ref SEU_PROJECT_REF
```
```bash
npx supabase db push
```

**C) Pelo script do projeto** (usa a *connection string* do banco)
```bash
DATABASE_URL="postgresql://postgres.SEU_REF:SENHA@HOST:5432/postgres" npm run db:migrate
```
A connection string fica em **Connect** (botão no topo do painel) → *Session pooler*.

## 3. Configurar a autenticação

Em **Authentication → URL Configuration**:
- **Site URL**: o endereço do site na Netlify (ex.: `https://central-de-estudos.netlify.app`).
- **Redirect URLs**: adicione o mesmo endereço e, para desenvolvimento, `http://localhost:5173`.

Em **Authentication → Sign In / Providers → Email**:
- Mantenha **Email** habilitado.
- **Confirm email**: recomendado deixar ligado (a conta é confirmada pelo link enviado ao e-mail).

> Uso pessoal: depois de criar sua conta, você pode desativar novos cadastros em
> **Authentication → Sign In / Providers → Allow new users to sign up**.

## 4. Copiar as chaves PÚBLICAS

Em **Project Settings → API Keys** (ou **Data API**):
- **Project URL** → vai em `VITE_SUPABASE_URL`
- **Publishable key** (`sb_publishable_...`) — ou a antiga **anon key** → vai em
  `VITE_SUPABASE_PUBLISHABLE_KEY`

> ⚠️ **Nunca** use a *secret key* / *service_role* no frontend. Ela ignora todas as
> regras de segurança. O app detecta esse erro e se recusa a iniciar.

## 5. Rodar localmente com o Supabase (opcional)

Crie o arquivo `central-de-estudos/.env.local` (não vai para o Git):
```
VITE_SUPABASE_URL=https://SEU_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```
```bash
npm install
```
```bash
npm run dev
```

## 6. Publicar na Netlify

1. Em <https://app.netlify.com>: **Add new site → Import an existing project** e
   conecte este repositório do GitHub.
2. As configurações de build já estão no `netlify.toml` da raiz do repositório
   (pasta-base `central-de-estudos`, comando `npm run build`, pasta `dist`).
3. Em **Site configuration → Environment variables**, cadastre:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`
4. Faça o deploy (**Deploys → Trigger deploy**). Variáveis `VITE_` são lidas no
   momento do build: depois de alterá-las, faça um novo deploy.
5. Volte ao passo 3 e confira se a **Site URL** do Supabase é o endereço final.

## 7. Migrar os dados do modo local para a nuvem

1. No navegador onde você usou o modo local: **Configurações → Dados e backup →
   Exportar backup (JSON)**.
2. Abra o site já conectado ao Supabase e crie sua conta.
3. Na tela de boas-vindas, **não** preencha o formulário: clique em
   **“Já tenho um backup — restaurar”** e selecione o arquivo. O ano letivo, as
   disciplinas, as provas e os conteúdos são recriados exatamente como estavam.

Para restaurar mais tarde (com a conta já em uso), use **Configurações → Dados e
backup → Importar backup**. A importação nunca sobrescreve registros existentes.

---

## Integração com IA (Fase 7) — o que será necessário

Ainda **não** é preciso configurar nada. Quando a Fase 7 for implementada:

| Variável (somente servidor/Netlify) | Para quê |
|---|---|
| `ANTHROPIC_API_KEY` | chave da API da Anthropic (console.anthropic.com) |
| `SUPABASE_SERVICE_ROLE_KEY` | permite que a função do servidor registre o consumo em `ai_operations` |
| `ANTHROPIC_MODEL` | modelo a usar (configurável, sem alterar código) |

Essas variáveis **não** usam o prefixo `VITE_` e nunca chegam ao navegador.
