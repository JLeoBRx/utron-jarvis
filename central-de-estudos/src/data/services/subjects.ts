import type { DataBackend } from '../backend/types';
import { parseOrThrow, subjectSchema, type SubjectInput } from '../schemas';
import type { Subject, UUID } from '../types';
import { collectSubjectFilePaths, removeFilesBestEffort } from './storageCleanup';

export function sortSubjects(subjects: Subject[]): Subject[] {
  return [...subjects].sort((a, b) => a.position - b.position || a.name.localeCompare(b.name, 'pt-BR'));
}

export async function listSubjects(db: DataBackend, academicYearId: UUID): Promise<Subject[]> {
  const rows = await db.list('subjects', { where: { academic_year_id: academicYearId } });
  return sortSubjects(rows);
}

export async function createSubject(db: DataBackend, academicYearId: UUID, input: SubjectInput): Promise<Subject> {
  const values = parseOrThrow(subjectSchema, input);
  const siblings = await db.list('subjects', { where: { academic_year_id: academicYearId } });
  const position = siblings.reduce((max, s) => Math.max(max, s.position), 0) + 1;
  return db.insert('subjects', { ...values, academic_year_id: academicYearId, position, archived_at: null });
}

export async function updateSubject(db: DataBackend, id: UUID, input: SubjectInput): Promise<Subject> {
  const values = parseOrThrow(subjectSchema, input);
  return db.update('subjects', id, values);
}

export async function setSubjectArchived(db: DataBackend, id: UUID, archived: boolean): Promise<Subject> {
  return db.update('subjects', id, { archived_at: archived ? new Date().toISOString() : null });
}

/** Exclui a disciplina e TUDO que pertence a ela (inclusive arquivos). */
export async function deleteSubject(db: DataBackend, id: UUID): Promise<void> {
  const paths = await collectSubjectFilePaths(db, [id]);
  await db.remove('subjects', id);
  await removeFilesBestEffort(db, paths);
}

export interface SubjectDeletionImpact {
  exams: number;
  materials: number;
  summaries: number;
  flashcards: number;
  questions: number;
}

export async function getSubjectDeletionImpact(db: DataBackend, id: UUID): Promise<SubjectDeletionImpact> {
  const where = { subject_id: id };
  const [exams, materials, summaries, flashcards, questions] = await Promise.all([
    db.count('exams', where),
    db.count('materials', where),
    db.count('summaries', where),
    db.count('flashcards', where),
    db.count('questions', where),
  ]);
  return { exams, materials, summaries, flashcards, questions };
}
