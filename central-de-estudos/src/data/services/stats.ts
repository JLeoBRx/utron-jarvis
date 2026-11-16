import type { DataBackend } from '../backend/types';
import type { UUID } from '../types';

export interface ContentCounts {
  materials: number;
  summaries: number;
  summariesDone: number;
  flashcards: number;
}

/** Contagens reais (consultas ao banco) para o ano letivo. */
export async function getContentCounts(db: DataBackend, subjectIds: UUID[]): Promise<ContentCounts> {
  if (!subjectIds.length) return { materials: 0, summaries: 0, summariesDone: 0, flashcards: 0 };
  const inSubjects = { subject_id: { in: subjectIds } };
  const [materials, summaries, summariesDone, flashcards] = await Promise.all([
    db.count('materials', inSubjects),
    db.count('summaries', inSubjects),
    db.count('summaries', { ...inSubjects, status: 'concluido' }),
    db.count('flashcards', inSubjects),
  ]);
  return { materials, summaries, summariesDone, flashcards };
}

/** Quantidade de materiais por disciplina (para os cards). */
export async function getMaterialCountsBySubject(db: DataBackend, subjectIds: UUID[]): Promise<Record<UUID, number>> {
  if (!subjectIds.length) return {};
  const rows = await db.list('materials', { where: { subject_id: { in: subjectIds } } });
  const counts: Record<UUID, number> = {};
  for (const row of rows) counts[row.subject_id] = (counts[row.subject_id] ?? 0) + 1;
  return counts;
}
