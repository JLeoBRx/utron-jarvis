-- =============================================================================
-- CENTRAL DE ESTUDOS — Fase 3: Biblioteca e scanner de cadernos
-- =============================================================================
-- Migração ADITIVA: não apaga nem altera dados existentes.
--   1. material_versions  → substituir um arquivo preserva o original
--   2. materiais do tipo "digitalizacao" (caderno fotografado = 1 material)
--   3. metadados das páginas digitalizadas (base para a leitura por IA)
--   4. bucket: aceita HEIC/HEIF (fotos originais de iPhone)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Versões anteriores dos arquivos
-- -----------------------------------------------------------------------------
create table public.material_versions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
  material_id     uuid not null,
  version_number  integer not null check (version_number >= 1),
  storage_path    text not null unique,
  file_name       text not null check (char_length(file_name) between 1 and 255),
  mime_type       text,
  size_bytes      bigint check (size_bytes is null or size_bytes >= 0),
  replaced_at     timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (material_id, version_number),
  foreign key (material_id, user_id)
    references public.materials (id, user_id) on delete cascade
);
create index material_versions_material_idx on public.material_versions (material_id);
create index material_versions_user_idx on public.material_versions (user_id);

create trigger material_versions_set_updated_at
  before update on public.material_versions
  for each row execute function public.set_updated_at();

alter table public.material_versions enable row level security;
create policy material_versions_owner_all on public.material_versions
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
grant select, insert, update, delete on public.material_versions to authenticated;

-- -----------------------------------------------------------------------------
-- 2. Caderno digitalizado como material da biblioteca
-- -----------------------------------------------------------------------------
alter table public.notebook_scans
  add constraint notebook_scans_id_subject_id_key unique (id, subject_id);

alter table public.materials add column scan_id uuid;
alter table public.materials add constraint materials_scan_id_key unique (scan_id);
-- O material e a digitalização pertencem obrigatoriamente à MESMA disciplina.
alter table public.materials
  add constraint materials_scan_id_subject_id_fkey foreign key (scan_id, subject_id)
  references public.notebook_scans (id, subject_id) on delete cascade;

alter table public.materials drop constraint materials_kind_check;
alter table public.materials
  add constraint materials_kind_check check (kind in ('arquivo', 'link', 'digitalizacao'));

alter table public.materials drop constraint materials_check;
alter table public.materials add constraint materials_conteudo_check check (
  (kind = 'arquivo'       and storage_path is not null and url is null     and scan_id is null) or
  (kind = 'link'          and url is not null     and storage_path is null and scan_id is null) or
  (kind = 'digitalizacao' and scan_id is not null and storage_path is null and url is null)
);

-- -----------------------------------------------------------------------------
-- 3. Páginas digitalizadas — tudo o que o processamento posterior precisa:
--    original intocado, versão tratada, ordem, dimensões e edições aplicadas.
-- -----------------------------------------------------------------------------
alter table public.notebook_scan_pages
  add column source                text not null default 'galeria' check (source in ('camera', 'galeria')),
  add column original_file_name    text check (original_file_name is null or char_length(original_file_name) <= 255),
  add column original_mime_type    text,
  add column original_size_bytes   bigint check (original_size_bytes is null or original_size_bytes >= 0),
  add column processed_mime_type   text,
  add column processed_size_bytes  bigint check (processed_size_bytes is null or processed_size_bytes >= 0),
  add column width                 integer check (width is null or width > 0),
  add column height                integer check (height is null or height > 0),
  -- rotação, recorte/perspectiva (quadrilátero normalizado), realce de iluminação
  add column edits                 jsonb not null default '{}'::jsonb;

-- -----------------------------------------------------------------------------
-- 4. Storage: fotos HEIC/HEIF (originais de iPhone) além dos tipos anteriores
-- -----------------------------------------------------------------------------
update storage.buckets
set allowed_mime_types = array[
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/plain',
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/heic',
  'image/heif'
]
where id = 'materiais';
