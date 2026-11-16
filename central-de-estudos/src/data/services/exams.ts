import type { DataBackend } from '../backend/types';
import { examSchema, parseOrThrow, type ExamInput } from '../schemas';
import type { Exam, ExamStatus, UUID } from '../types';

export async function listExams(db: DataBackend, subjectIds?: UUID[]): Promise<Exam[]> {
  if (subjectIds && !subjectIds.length) return [];
  return db.list('exams', {
    where: subjectIds ? { subject_id: { in: subjectIds } } : undefined,
    orderBy: [{ column: 'exam_date', ascending: true }, { column: 'created_at', ascending: true }],
  });
}

export async function createExam(db: DataBackend, input: ExamInput): Promise<Exam> {
  const values = parseOrThrow(examSchema, input);
  return db.insert('exams', values);
}

export async function updateExam(db: DataBackend, id: UUID, input: ExamInput): Promise<Exam> {
  const values = parseOrThrow(examSchema, input);
  return db.update('exams', id, values);
}

export async function setExamStatus(db: DataBackend, id: UUID, status: ExamStatus): Promise<Exam> {
  return db.update('exams', id, { status });
}

export interface ExamDeletionImpact {
  /** Apagados junto com a prova. */
  topics: number;
  flashcards: number;
  questions: number;
  quizzes: number;
  events: number;
  /** Preservados na disciplina (apenas desvinculados da prova). */
  materials: number;
  summaries: number;
}

export async function getExamDeletionImpact(db: DataBackend, id: UUID): Promise<ExamDeletionImpact> {
  const where = { exam_id: id };
  const [topics, flashcards, questions, quizzes, events, materials, summaries] = await Promise.all([
    db.count('exam_topics', where),
    db.count('flashcards', where),
    db.count('questions', where),
    db.count('quizzes', where),
    db.count('calendar_events', where),
    db.count('materials', where),
    db.count('summaries', where),
  ]);
  return { topics, flashcards, questions, quizzes, events, materials, summaries };
}

/**
 * Exclui a prova. Conteúdos, flashcards, questões, simulados e eventos da
 * prova são apagados; MATERIAIS e RESUMOS são preservados na disciplina.
 */
export async function deleteExam(db: DataBackend, id: UUID): Promise<void> {
  await db.remove('exams', id);
}
