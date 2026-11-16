-- =============================================================================
-- CENTRAL DE ESTUDOS — Armazenamento de arquivos (Supabase Storage)
-- =============================================================================
-- Bucket PRIVADO "materiais". Os arquivos ficam em:
--     <user_id>/<subject_id>/<material_id>/<nome-do-arquivo>
-- Cada usuário só lê/escreve dentro da própria pasta (<user_id>/...).
-- Visualização/download usam URLs assinadas e temporárias.
-- =============================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'materiais',
  'materiais',
  false,
  52428800, -- 50 MB por arquivo
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'image/png',
    'image/jpeg',
    'image/webp'
  ]
)
on conflict (id) do nothing;

create policy "materiais_dono_select" on storage.objects
  for select to authenticated
  using (bucket_id = 'materiais' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "materiais_dono_insert" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'materiais' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "materiais_dono_update" on storage.objects
  for update to authenticated
  using (bucket_id = 'materiais' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'materiais' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "materiais_dono_delete" on storage.objects
  for delete to authenticated
  using (bucket_id = 'materiais' and (storage.foldername(name))[1] = (select auth.uid())::text);
