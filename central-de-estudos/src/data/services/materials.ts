import { AppError } from '@/lib/errors';
import { checkUpload, LIBRARY_FILE_TYPES } from '@/lib/files';
import { newId } from '@/lib/ids';
import type { DataBackend } from '../backend/types';
import { linkSchema, materialMetaSchema, parseOrThrow, type LinkInput, type MaterialMetaInput } from '../schemas';
import type { Material, MaterialVersion, UUID } from '../types';
import { removeFilesBestEffort } from './storageCleanup';
import { materialFilePath } from './storagePaths';

/** Arquivo a enviar (File do navegador ou Blob com nome). */
export interface UploadSource {
  name: string;
  type: string;
  size: number;
  blob: Blob;
}

export function toUploadSource(file: File): UploadSource {
  return { name: file.name, type: file.type, size: file.size, blob: file };
}

export async function listMaterials(db: DataBackend, subjectIds?: UUID[]): Promise<Material[]> {
  if (subjectIds && !subjectIds.length) return [];
  return db.list('materials', {
    where: subjectIds ? { subject_id: { in: subjectIds } } : undefined,
    orderBy: [{ column: 'created_at', ascending: false }],
  });
}

function validateFile(file: UploadSource) {
  const check = checkUpload(file, LIBRARY_FILE_TYPES);
  if (!check.ok) throw new AppError('validation', `${file.name}: ${check.reason}`);
  return check.type;
}

/**
 * Envia um arquivo para a biblioteca. Ordem segura: primeiro o arquivo vai para
 * o Storage; só então o registro é criado. Se o registro falhar, o arquivo
 * enviado é removido (nada fica órfão).
 */
export async function uploadMaterialFile(db: DataBackend, meta: MaterialMetaInput, file: UploadSource): Promise<Material> {
  const values = parseOrThrow(materialMetaSchema, meta);
  const type = validateFile(file);
  const id = newId();
  const path = materialFilePath(db.userId, values.subject_id, id, 1, file.name);
  await db.storage.upload(path, file.blob, { contentType: type.mime });
  try {
    return await db.insert('materials', {
      id,
      ...values,
      kind: 'arquivo',
      file_name: file.name.slice(0, 255),
      mime_type: type.mime,
      size_bytes: file.size,
      storage_path: path,
      url: null,
      version: 1,
      replaced_at: null,
      scan_id: null,
    });
  } catch (error) {
    await db.storage.remove([path]).catch(() => undefined);
    throw error;
  }
}

export async function createLinkMaterial(db: DataBackend, input: LinkInput): Promise<Material> {
  const { url, ...meta } = parseOrThrow(linkSchema, input);
  return db.insert('materials', {
    ...meta,
    kind: 'link',
    url,
    file_name: null,
    mime_type: null,
    size_bytes: null,
    storage_path: null,
    version: 1,
    replaced_at: null,
    scan_id: null,
  });
}

/** Atualiza título, descrição, origem, categoria, prova e (para arquivos/links) disciplina. */
export async function updateMaterialMeta(db: DataBackend, material: Material, meta: MaterialMetaInput): Promise<Material> {
  const values = parseOrThrow(materialMetaSchema, meta);
  if (material.kind === 'digitalizacao' && values.subject_id !== material.subject_id) {
    throw new AppError('validation', 'Um caderno digitalizado não pode mudar de disciplina.');
  }
  const updated = await db.update('materials', material.id, values);
  if (material.scan_id && values.exam_id !== material.exam_id) {
    await db.update('notebook_scans', material.scan_id, { exam_id: values.exam_id });
  }
  return updated;
}

export async function listMaterialVersions(db: DataBackend, materialId: UUID): Promise<MaterialVersion[]> {
  return db.list('material_versions', {
    where: { material_id: materialId },
    orderBy: [{ column: 'version_number', ascending: false }],
  });
}

/**
 * Substitui o arquivo SEM apagar o anterior: o arquivo atual é registrado em
 * `material_versions` e continua disponível para download.
 */
export async function replaceMaterialFile(db: DataBackend, material: Material, file: UploadSource): Promise<Material> {
  if (material.kind !== 'arquivo' || !material.storage_path) {
    throw new AppError('validation', 'Apenas materiais do tipo arquivo podem ter o arquivo substituído.');
  }
  const type = validateFile(file);
  const nextVersion = material.version + 1;
  const path = materialFilePath(db.userId, material.subject_id, material.id, nextVersion, file.name);
  await db.storage.upload(path, file.blob, { contentType: type.mime });

  let version: MaterialVersion | null = null;
  try {
    version = await db.insert('material_versions', {
      material_id: material.id,
      version_number: material.version,
      storage_path: material.storage_path,
      file_name: material.file_name ?? 'arquivo',
      mime_type: material.mime_type,
      size_bytes: material.size_bytes,
      replaced_at: new Date().toISOString(),
    });
    return await db.update('materials', material.id, {
      storage_path: path,
      file_name: file.name.slice(0, 255),
      mime_type: type.mime,
      size_bytes: file.size,
      version: nextVersion,
      replaced_at: new Date().toISOString(),
    });
  } catch (error) {
    // Desfaz: o material continua apontando para o arquivo anterior, intacto.
    if (version) await db.remove('material_versions', version.id).catch(() => undefined);
    await db.storage.remove([path]).catch(() => undefined);
    throw error;
  }
}

/** Todos os arquivos que pertencem a um material (atual, versões e páginas digitalizadas). */
export async function collectMaterialFilePaths(db: DataBackend, material: Material): Promise<string[]> {
  const versions = await db.list('material_versions', { where: { material_id: material.id } });
  const pages = material.scan_id ? await db.list('notebook_scan_pages', { where: { scan_id: material.scan_id } }) : [];
  return [
    material.storage_path,
    ...versions.map((v) => v.storage_path),
    ...pages.flatMap((p) => [p.original_path, p.processed_path]),
  ].filter((p): p is string => Boolean(p));
}

/** Exclui definitivamente o material, suas versões e (se for caderno) as páginas e fotos. */
export async function deleteMaterial(db: DataBackend, material: Material): Promise<void> {
  const paths = await collectMaterialFilePaths(db, material);
  if (material.scan_id) await db.remove('notebook_scans', material.scan_id); // cascata: páginas + material
  else await db.remove('materials', material.id);
  await removeFilesBestEffort(db, paths);
}
