import { AppError } from '@/lib/errors';
import type { DataBackend } from '../backend/types';
import { parseOrThrow, topicSchema } from '../schemas';
import type { ExamTopic, TopicStatus, UUID } from '../types';

export async function listTopics(db: DataBackend, examIds?: UUID[]): Promise<ExamTopic[]> {
  if (examIds && !examIds.length) return [];
  return db.list('exam_topics', {
    where: examIds ? { exam_id: { in: examIds } } : undefined,
    orderBy: [{ column: 'position', ascending: true }],
  });
}

/**
 * Cadastra conteúdos. Aceita vários de uma vez (ex.: lista colada, um por
 * linha). Linhas vazias e marcadores ("-", "•", "1.") são ignorados.
 */
export function parseTopicLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:[-–•*]|\d+[.)])\s*/, '').trim())
    .filter(Boolean);
}

export async function createTopics(db: DataBackend, examId: UUID, titles: string[]): Promise<ExamTopic[]> {
  const clean = titles.map((t) => parseOrThrow(topicSchema, { title: t, status: 'nao_estudado' }).title);
  if (!clean.length) throw new AppError('validation', 'Informe pelo menos um conteúdo.');
  const existing = await db.list('exam_topics', { where: { exam_id: examId } });
  let position = existing.reduce((max, t) => Math.max(max, t.position), 0);
  return db.insertMany(
    'exam_topics',
    clean.map((title) => ({ exam_id: examId, title, notes: null, status: 'nao_estudado' as TopicStatus, position: ++position })),
  );
}

export async function updateTopic(
  db: DataBackend,
  id: UUID,
  input: { title: string; notes?: string | null; status: TopicStatus },
): Promise<ExamTopic> {
  const values = parseOrThrow(topicSchema, input);
  return db.update('exam_topics', id, values);
}

export async function setTopicStatus(db: DataBackend, id: UUID, status: TopicStatus): Promise<ExamTopic> {
  return db.update('exam_topics', id, { status });
}

export async function deleteTopic(db: DataBackend, id: UUID): Promise<void> {
  await db.remove('exam_topics', id);
}

/** Move o conteúdo uma posição para cima/baixo e renumera a lista (1, 2, 3…). */
export async function moveTopic(db: DataBackend, examId: UUID, id: UUID, direction: -1 | 1): Promise<void> {
  const ordered = await listTopics(db, [examId]);
  const index = ordered.findIndex((t) => t.id === id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= ordered.length) return;
  [ordered[index], ordered[target]] = [ordered[target]!, ordered[index]!];
  for (let i = 0; i < ordered.length; i++) {
    const topic = ordered[i]!;
    if (topic.position !== i + 1) await db.update('exam_topics', topic.id, { position: i + 1 });
  }
}
