-- =============================================================================
-- CENTRAL DE ESTUDOS — Esquema inicial do banco de dados (PostgreSQL / Supabase)
-- =============================================================================
--
-- Hierarquia:
--   ANO LETIVO → DISCIPLINA → PROVA → CONTEÚDOS / MATERIAIS / RESUMOS /
--   FLASHCARDS / EXERCÍCIOS / SIMULADOS → RESULTADOS
--
-- Convenções:
--   * Toda tabela possui `id uuid` e `user_id uuid` (dono do registro).
--   * `user_id` assume `auth.uid()` por padrão e é protegido por RLS.
--   * Chaves estrangeiras COMPOSTAS garantem integridade:
--       - (parent_id, user_id)    → um registro só referencia registros do mesmo usuário;
--       - (exam_id, subject_id)   → um material/resumo só pode ser vinculado a uma
--                                   prova da MESMA disciplina (não mistura provas).
--   * Enumerações usam `text` + CHECK (evoluem sem migrações complexas).
--   * Excluir uma prova NÃO apaga materiais nem resumos: eles permanecem na
--     disciplina, apenas desvinculados da prova (ON DELETE SET NULL (exam_id)).
--     Requer PostgreSQL 15+ (Supabase usa 15/17).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Funções utilitárias
-- -----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- -----------------------------------------------------------------------------
-- Perfis (dados do usuário além de auth.users)
-- -----------------------------------------------------------------------------
create table public.profiles (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null unique default auth.uid() references auth.users (id) on delete cascade,
  display_name text check (display_name is null or char_length(display_name) <= 80),
  preferences  jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- Anos letivos
-- -----------------------------------------------------------------------------
create table public.academic_years (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name        text not null check (char_length(btrim(name)) between 1 and 60),
  start_date  date,
  end_date    date,
  is_active   boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (id, user_id),
  check (start_date is null or end_date is null or end_date >= start_date)
);
-- No máximo um ano letivo ativo por usuário.
create unique index academic_years_one_active_per_user
  on public.academic_years (user_id) where is_active;
create unique index academic_years_unique_name
  on public.academic_years (user_id, lower(btrim(name)));

-- -----------------------------------------------------------------------------
-- Disciplinas
-- -----------------------------------------------------------------------------
create table public.subjects (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null default auth.uid() references auth.users (id) on delete cascade,
  academic_year_id  uuid not null,
  name              text not null check (char_length(btrim(name)) between 1 and 120),
  -- Código institucional. NULL = "código a confirmar" (nunca inventar).
  code              text check (code is null or char_length(btrim(code)) between 1 and 40),
  category          text not null check (category in ('formacao_geral', 'formacao_tecnica')),
  description       text check (description is null or char_length(description) <= 2000),
  teacher           text check (teacher is null or char_length(teacher) <= 120),
  color             text not null default 'slate' check (color ~ '^[a-z]{3,16}$'),
  position          integer not null default 0,
  archived_at       timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (id, user_id),
  foreign key (academic_year_id, user_id)
    references public.academic_years (id, user_id) on delete cascade
);
create index subjects_user_idx on public.subjects (user_id);
create index subjects_year_idx on public.subjects (academic_year_id);
create unique index subjects_unique_name_per_year
  on public.subjects (academic_year_id, lower(btrim(name)));

-- -----------------------------------------------------------------------------
-- Provas / avaliações
-- -----------------------------------------------------------------------------
create table public.exams (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id   uuid not null,
  title        text not null check (char_length(btrim(title)) between 1 and 160),
  exam_date    date,            -- NULL = data ainda não definida (nunca inventar)
  exam_time    time,
  teacher      text check (teacher is null or char_length(teacher) <= 120),
  description  text check (description is null or char_length(description) <= 4000),
  priority     text not null default 'media'
               check (priority in ('baixa', 'media', 'alta')),
  status       text not null default 'nao_iniciada'
               check (status in ('nao_iniciada', 'em_preparacao', 'em_revisao',
                                 'preparacao_concluida', 'realizada')),
  score        numeric(6, 2) check (score is null or score >= 0),
  max_score    numeric(6, 2) check (max_score is null or max_score > 0),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (id, user_id),
  unique (id, subject_id),
  check (score is null or max_score is null or score <= max_score),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade
);
create index exams_user_idx on public.exams (user_id);
create index exams_subject_idx on public.exams (subject_id);
create index exams_date_idx on public.exams (user_id, exam_date);

-- -----------------------------------------------------------------------------
-- Conteúdos cobrados em cada prova
-- -----------------------------------------------------------------------------
create table public.exam_topics (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  exam_id     uuid not null,
  title       text not null check (char_length(btrim(title)) between 1 and 200),
  notes       text check (notes is null or char_length(notes) <= 4000),
  status      text not null default 'nao_estudado'
              check (status in ('nao_estudado', 'estudando', 'revisado', 'dominado')),
  position    integer not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (id, user_id),
  unique (id, exam_id),
  foreign key (exam_id, user_id)
    references public.exams (id, user_id) on delete cascade
);
create index exam_topics_exam_idx on public.exam_topics (exam_id);
create index exam_topics_user_idx on public.exam_topics (user_id);

-- -----------------------------------------------------------------------------
-- Biblioteca de materiais (arquivos e links)
-- -----------------------------------------------------------------------------
create table public.materials (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id    uuid not null,
  exam_id       uuid,           -- NULL = material geral da disciplina
  kind          text not null check (kind in ('arquivo', 'link')),
  category      text not null check (category in ('slides', 'caderno', 'exercicios', 'atividades',
                                                  'provas_anteriores', 'apostilas', 'complementares')),
  title         text not null check (char_length(btrim(title)) between 1 and 200),
  description   text check (description is null or char_length(description) <= 4000),
  origin        text check (origin is null or char_length(origin) <= 200),
  file_name     text,
  mime_type     text,
  size_bytes    bigint check (size_bytes is null or size_bytes >= 0),
  storage_path  text unique,
  url           text check (url is null or url ~* '^https?://'),
  version       integer not null default 1 check (version >= 1),
  replaced_at   timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (id, user_id),
  unique (id, subject_id),
  check (
    (kind = 'arquivo' and storage_path is not null and url is null) or
    (kind = 'link'    and url is not null and storage_path is null)
  ),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  -- Só permite vincular a uma prova da MESMA disciplina.
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete set null (exam_id)
);
create index materials_user_idx on public.materials (user_id);
create index materials_subject_idx on public.materials (subject_id);
create index materials_exam_idx on public.materials (exam_id);

-- -----------------------------------------------------------------------------
-- Resumos e histórico de versões
-- -----------------------------------------------------------------------------
create table public.summaries (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id       uuid not null,
  exam_id          uuid,
  title            text not null check (char_length(btrim(title)) between 1 and 200),
  status           text not null default 'rascunho'
                   check (status in ('rascunho', 'em_revisao', 'concluido')),
  content          text not null default '',   -- Markdown + LaTeX (versão atual)
  current_version  integer not null default 0 check (current_version >= 0),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (id, user_id),
  unique (id, subject_id),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete set null (exam_id)
);
create index summaries_user_idx on public.summaries (user_id);
create index summaries_subject_idx on public.summaries (subject_id);
create index summaries_exam_idx on public.summaries (exam_id);

create table public.summary_versions (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null default auth.uid() references auth.users (id) on delete cascade,
  summary_id           uuid not null,
  version_number       integer not null check (version_number >= 1),
  content              text not null,
  change_note          text check (change_note is null or char_length(change_note) <= 1000),
  source_material_ids  uuid[] not null default '{}',
  created_by           text not null default 'usuario'
                       check (created_by in ('usuario', 'importacao', 'ia')),
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (summary_id, version_number),
  foreign key (summary_id, user_id)
    references public.summaries (id, user_id) on delete cascade
);
create index summary_versions_summary_idx on public.summary_versions (summary_id);

-- Quais materiais alimentaram cada resumo (rastreabilidade das fontes).
create table public.summary_sources (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  summary_id   uuid not null,
  material_id  uuid not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (summary_id, material_id),
  foreign key (summary_id, user_id)
    references public.summaries (id, user_id) on delete cascade,
  foreign key (material_id, user_id)
    references public.materials (id, user_id) on delete cascade
);
create index summary_sources_material_idx on public.summary_sources (material_id);

-- -----------------------------------------------------------------------------
-- Flashcards (preparado para repetição espaçada — SM-2)
-- -----------------------------------------------------------------------------
create table public.flashcards (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id        uuid not null,
  exam_id           uuid,
  topic_id          uuid,
  summary_id        uuid,
  question          text not null check (char_length(btrim(question)) between 1 and 4000),
  answer            text not null check (char_length(btrim(answer)) between 1 and 8000),
  category          text check (category is null or char_length(category) <= 120),
  difficulty        text not null default 'medio' check (difficulty in ('facil', 'medio', 'dificil')),
  origin            text not null default 'manual' check (origin in ('manual', 'importado', 'ia')),
  ease_factor       numeric(4, 2) not null default 2.50 check (ease_factor >= 1.30),
  interval_days     integer not null default 0 check (interval_days >= 0),
  repetitions       integer not null default 0 check (repetitions >= 0),
  due_at            timestamptz,
  last_result       text check (last_result is null or last_result in ('nao_sei', 'duvidas', 'parcial', 'sei_bem')),
  last_reviewed_at  timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (id, user_id),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete cascade,
  foreign key (topic_id, exam_id)
    references public.exam_topics (id, exam_id) on delete set null (topic_id),
  foreign key (summary_id, subject_id)
    references public.summaries (id, subject_id) on delete set null (summary_id),
  check (topic_id is null or exam_id is not null)
);
create index flashcards_user_idx on public.flashcards (user_id);
create index flashcards_subject_idx on public.flashcards (subject_id);
create index flashcards_exam_idx on public.flashcards (exam_id);
create index flashcards_due_idx on public.flashcards (user_id, due_at);

create table public.flashcard_reviews (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  flashcard_id  uuid not null,
  result        text not null check (result in ('nao_sei', 'duvidas', 'parcial', 'sei_bem')),
  reviewed_at   timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  foreign key (flashcard_id, user_id)
    references public.flashcards (id, user_id) on delete cascade
);
create index flashcard_reviews_card_idx on public.flashcard_reviews (flashcard_id);
create index flashcard_reviews_user_idx on public.flashcard_reviews (user_id, reviewed_at);

-- -----------------------------------------------------------------------------
-- Banco de questões (exercícios)
-- -----------------------------------------------------------------------------
create table public.questions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id      uuid not null,
  exam_id         uuid,
  topic_id        uuid,
  summary_id      uuid,
  type            text not null check (type in ('multipla_escolha', 'verdadeiro_falso', 'discursiva',
                                                'calculo', 'associacao', 'lacunas',
                                                'interpretacao', 'problema')),
  statement       text not null check (char_length(btrim(statement)) between 1 and 12000),
  options         jsonb not null default '[]'::jsonb,   -- alternativas / pares / lacunas
  correct_answer  jsonb,                                -- formato depende do tipo
  explanation     text check (explanation is null or char_length(explanation) <= 12000),
  difficulty      text not null default 'medio' check (difficulty in ('facil', 'medio', 'dificil')),
  topic_label     text check (topic_label is null or char_length(topic_label) <= 200),
  origin          text not null default 'manual' check (origin in ('manual', 'importado', 'ia')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (id, user_id),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete cascade,
  foreign key (topic_id, exam_id)
    references public.exam_topics (id, exam_id) on delete set null (topic_id),
  foreign key (summary_id, subject_id)
    references public.summaries (id, subject_id) on delete set null (summary_id),
  check (topic_id is null or exam_id is not null)
);
create index questions_user_idx on public.questions (user_id);
create index questions_subject_idx on public.questions (subject_id);
create index questions_exam_idx on public.questions (exam_id);

-- -----------------------------------------------------------------------------
-- Simulados e tentativas
-- -----------------------------------------------------------------------------
create table public.quizzes (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id          uuid not null,
  exam_id             uuid,
  title               text not null check (char_length(btrim(title)) between 1 and 200),
  question_ids        uuid[] not null default '{}',
  topic_ids           uuid[] not null default '{}',
  difficulty          text check (difficulty is null or difficulty in ('facil', 'medio', 'dificil', 'misto')),
  time_limit_minutes  integer check (time_limit_minutes is null or time_limit_minutes between 1 and 600),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (id, user_id),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete cascade
);
create index quizzes_user_idx on public.quizzes (user_id);
create index quizzes_exam_idx on public.quizzes (exam_id);

create table public.quiz_attempts (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  quiz_id          uuid not null,
  status           text not null default 'em_andamento' check (status in ('em_andamento', 'finalizada')),
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  elapsed_seconds  integer not null default 0 check (elapsed_seconds >= 0),
  answers          jsonb not null default '{}'::jsonb,   -- progresso salvo: { question_id: resposta }
  results          jsonb,                                -- correção (somente após finalizar)
  score            numeric(5, 2) check (score is null or score between 0 and 100),
  correct_count    integer check (correct_count is null or correct_count >= 0),
  wrong_count      integer check (wrong_count is null or wrong_count >= 0),
  total_count      integer check (total_count is null or total_count >= 0),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  check (status = 'em_andamento' or finished_at is not null),
  foreign key (quiz_id, user_id)
    references public.quizzes (id, user_id) on delete cascade
);
create index quiz_attempts_quiz_idx on public.quiz_attempts (quiz_id);
create index quiz_attempts_user_idx on public.quiz_attempts (user_id, finished_at);

-- -----------------------------------------------------------------------------
-- Sessões de estudo e calendário
-- -----------------------------------------------------------------------------
create table public.study_sessions (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id        uuid,
  exam_id           uuid,
  started_at        timestamptz not null,
  duration_minutes  integer not null check (duration_minutes between 1 and 1440),
  activity          text not null default 'outro'
                    check (activity in ('leitura', 'resumo', 'flashcards', 'exercicios',
                                        'simulado', 'revisao', 'outro')),
  notes             text check (notes is null or char_length(notes) <= 2000),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  check (exam_id is null or subject_id is not null),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete set null (exam_id)
);
create index study_sessions_user_idx on public.study_sessions (user_id, started_at);

create table public.calendar_events (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id    uuid,
  exam_id       uuid,
  type          text not null check (type in ('sessao_estudo', 'meta', 'lembrete', 'revisao', 'outro')),
  title         text not null check (char_length(btrim(title)) between 1 and 200),
  description   text check (description is null or char_length(description) <= 4000),
  starts_at     timestamptz not null,
  ends_at       timestamptz,
  all_day       boolean not null default false,
  priority      text not null default 'media' check (priority in ('baixa', 'media', 'alta')),
  remind_at     timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  check (ends_at is null or ends_at >= starts_at),
  check (exam_id is null or subject_id is not null),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete cascade
);
create index calendar_events_user_idx on public.calendar_events (user_id, starts_at);

-- -----------------------------------------------------------------------------
-- Scanner inteligente de cadernos
-- -----------------------------------------------------------------------------
create table public.notebook_scans (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  subject_id   uuid not null,
  exam_id      uuid,
  summary_id   uuid,
  topic_label  text check (topic_label is null or char_length(topic_label) <= 200),
  status       text not null default 'capturado'
               check (status in ('capturado', 'processando', 'aguardando_revisao',
                                 'revisado', 'concluido', 'erro')),
  page_count   integer not null default 0 check (page_count >= 0),
  recognized   jsonb,      -- resultado estruturado da leitura (texto, fórmulas, trechos duvidosos)
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (id, user_id),
  foreign key (subject_id, user_id)
    references public.subjects (id, user_id) on delete cascade,
  foreign key (exam_id, subject_id)
    references public.exams (id, subject_id) on delete set null (exam_id),
  foreign key (summary_id, subject_id)
    references public.summaries (id, subject_id) on delete set null (summary_id)
);
create index notebook_scans_user_idx on public.notebook_scans (user_id);

create table public.notebook_scan_pages (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  scan_id          uuid not null,
  position         integer not null check (position >= 0),
  original_path    text not null,   -- fotografia original (sempre preservada)
  processed_path   text,            -- versão recortada/realçada
  material_id      uuid,
  recognized_text  text,
  confidence       numeric(4, 3) check (confidence is null or confidence between 0 and 1),
  needs_review     boolean not null default false,
  review_notes     jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  foreign key (scan_id, user_id)
    references public.notebook_scans (id, user_id) on delete cascade,
  foreign key (material_id, user_id)
    references public.materials (id, user_id) on delete set null (material_id)
);
create index notebook_scan_pages_scan_idx on public.notebook_scan_pages (scan_id, position);

-- -----------------------------------------------------------------------------
-- Registro de operações de IA (controle de custos/consumo).
-- Escrito SOMENTE pelo backend (service role); o usuário apenas lê.
-- -----------------------------------------------------------------------------
create table public.ai_operations (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  operation           text not null check (char_length(operation) between 1 and 80),
  model               text,
  status              text not null default 'pendente'
                      check (status in ('pendente', 'executando', 'sucesso', 'erro')),
  input_tokens        integer check (input_tokens is null or input_tokens >= 0),
  output_tokens       integer check (output_tokens is null or output_tokens >= 0),
  estimated_cost_usd  numeric(10, 4) check (estimated_cost_usd is null or estimated_cost_usd >= 0),
  related_table       text,
  related_id          uuid,
  error               text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  finished_at         timestamptz
);
create index ai_operations_user_idx on public.ai_operations (user_id, created_at);

-- -----------------------------------------------------------------------------
-- Gatilhos de updated_at
-- -----------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'profiles', 'academic_years', 'subjects', 'exams', 'exam_topics', 'materials',
    'summaries', 'summary_versions', 'summary_sources', 'flashcards', 'flashcard_reviews',
    'questions', 'quizzes', 'quiz_attempts', 'study_sessions', 'calendar_events',
    'notebook_scans', 'notebook_scan_pages', 'ai_operations'
  ] loop
    execute format(
      'create trigger %I before update on public.%I for each row execute function public.set_updated_at()',
      t || '_set_updated_at', t
    );
  end loop;
end;
$$;

-- -----------------------------------------------------------------------------
-- Segurança: Row Level Security (cada usuário só enxerga os próprios dados)
-- -----------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'profiles', 'academic_years', 'subjects', 'exams', 'exam_topics', 'materials',
    'summaries', 'summary_versions', 'summary_sources', 'flashcards', 'flashcard_reviews',
    'questions', 'quizzes', 'quiz_attempts', 'study_sessions', 'calendar_events',
    'notebook_scans', 'notebook_scan_pages'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy %I on public.%I for all to authenticated
         using (user_id = (select auth.uid()))
         with check (user_id = (select auth.uid()))',
      t || '_owner_all', t
    );
  end loop;
end;
$$;

alter table public.ai_operations enable row level security;
create policy ai_operations_owner_read on public.ai_operations
  for select to authenticated
  using (user_id = (select auth.uid()));

-- Permissões explícitas (independe dos privilégios padrão do projeto).
revoke all on all tables in schema public from anon;
grant select, insert, update, delete on
  public.profiles, public.academic_years, public.subjects, public.exams, public.exam_topics,
  public.materials, public.summaries, public.summary_versions, public.summary_sources,
  public.flashcards, public.flashcard_reviews, public.questions, public.quizzes,
  public.quiz_attempts, public.study_sessions, public.calendar_events,
  public.notebook_scans, public.notebook_scan_pages
  to authenticated;
grant select on public.ai_operations to authenticated;
