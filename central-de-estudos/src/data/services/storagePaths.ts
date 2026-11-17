import { storageSafeName } from '@/lib/files';
import type { UUID } from '../types';

/**
 * Caminhos no Storage. O PRIMEIRO segmento é sempre o id do usuário — é isso
 * que as políticas do bucket privado verificam.
 *
 *   <user>/<disciplina>/materiais/<material>/v<versão>-<arquivo>
 *   <user>/<disciplina>/cadernos/<digitalização>/<página>-original.<ext>
 *   <user>/<disciplina>/cadernos/<digitalização>/<página>-tratada.jpg
 */
export function materialFilePath(userId: UUID, subjectId: UUID, materialId: UUID, version: number, fileName: string): string {
  return `${userId}/${subjectId}/materiais/${materialId}/v${version}-${storageSafeName(fileName)}`;
}

export function scanPagePath(
  userId: UUID,
  subjectId: UUID,
  scanId: UUID,
  pageId: UUID,
  variant: 'original' | 'tratada',
  extension: string,
): string {
  return `${userId}/${subjectId}/cadernos/${scanId}/${pageId}-${variant}.${extension}`;
}

/** Troca o dono do caminho (usado ao importar backup em outra conta/modo). */
export function reassignPathOwner(path: string, userId: UUID): string {
  const slash = path.indexOf('/');
  return slash === -1 ? `${userId}/${path}` : `${userId}${path.slice(slash)}`;
}
