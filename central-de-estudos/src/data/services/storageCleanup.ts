import type { DataBackend } from '../backend/types';
import type { UUID } from '../types';

/**
 * Caminhos de arquivos do Storage ligados a um conjunto de disciplinas.
 * O banco apaga os registros em cascata, mas os ARQUIVOS no Storage precisam
 * ser removidos explicitamente.
 */
export async function collectSubjectFilePaths(db: DataBackend, subjectIds: UUID[]): Promise<string[]> {
  if (!subjectIds.length) return [];
  const materials = await db.list('materials', { where: { subject_id: { in: subjectIds } } });
  const versions = materials.length
    ? await db.list('material_versions', { where: { material_id: { in: materials.map((m) => m.id) } } })
    : [];
  const scans = await db.list('notebook_scans', { where: { subject_id: { in: subjectIds } } });
  const pages = scans.length
    ? await db.list('notebook_scan_pages', { where: { scan_id: { in: scans.map((s) => s.id) } } })
    : [];
  return [
    ...materials.map((m) => m.storage_path),
    ...versions.map((v) => v.storage_path),
    ...pages.flatMap((p) => [p.original_path, p.processed_path]),
  ].filter((path): path is string => Boolean(path));
}

/** Remove arquivos sem interromper o fluxo (registros já foram apagados). */
export async function removeFilesBestEffort(db: DataBackend, paths: string[]): Promise<number> {
  if (!paths.length) return 0;
  try {
    for (let i = 0; i < paths.length; i += 100) {
      await db.storage.remove(paths.slice(i, i + 100));
    }
    return 0;
  } catch (error) {
    console.warn('[storage] arquivos não removidos — limpeza manual pode ser necessária', paths, error);
    return paths.length;
  }
}
