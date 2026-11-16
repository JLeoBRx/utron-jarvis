import type { Exam, ExamTopic, TopicStatus } from '@/data/types';
import { daysUntil } from './dates';

/**
 * PROGRESSO DE PREPARAÇÃO
 * -----------------------
 * Calculado a partir do status de estudo de cada CONTEÚDO cadastrado — ou
 * seja, de atividades efetivamente registradas pelo estudante, e nunca da
 * quantidade de resumos ou materiais existentes.
 *
 *   Não estudado = 0 · Estudando = 1/3 · Revisado = 2/3 · Dominado = 1
 *
 * (Nas próximas fases, flashcards e simulados também entrarão no cálculo.)
 */
export const TOPIC_WEIGHTS: Record<TopicStatus, number> = {
  nao_estudado: 0,
  estudando: 1 / 3,
  revisado: 2 / 3,
  dominado: 1,
};

export interface ProgressInfo {
  /** 0–1, ou `null` quando não há conteúdos cadastrados. */
  value: number | null;
  total: number;
  byStatus: Record<TopicStatus, number>;
}

export function emptyByStatus(): Record<TopicStatus, number> {
  return { nao_estudado: 0, estudando: 0, revisado: 0, dominado: 0 };
}

export function topicsProgress(topics: Pick<ExamTopic, 'status'>[]): ProgressInfo {
  const byStatus = emptyByStatus();
  let sum = 0;
  for (const topic of topics) {
    byStatus[topic.status] += 1;
    sum += TOPIC_WEIGHTS[topic.status];
  }
  return { value: topics.length ? sum / topics.length : null, total: topics.length, byStatus };
}

export function groupTopicsByExam(topics: ExamTopic[]): Map<string, ExamTopic[]> {
  const map = new Map<string, ExamTopic[]>();
  for (const topic of topics) {
    const list = map.get(topic.exam_id);
    if (list) list.push(topic);
    else map.set(topic.exam_id, [topic]);
  }
  for (const list of map.values()) list.sort((a, b) => a.position - b.position);
  return map;
}

/**
 * Progresso agregado (disciplina ou geral): considera os conteúdos das provas
 * PENDENTES (status diferente de "Realizada").
 */
export function pendingExamsProgress(exams: Exam[], topicsByExam: Map<string, ExamTopic[]>): ProgressInfo {
  const topics = exams
    .filter((exam) => exam.status !== 'realizada')
    .flatMap((exam) => topicsByExam.get(exam.id) ?? []);
  return topicsProgress(topics);
}

export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`;
}

export type Urgency = 'passada' | 'hoje' | 'urgente' | 'proxima' | 'futura' | 'sem_data';

export function examUrgency(exam: Pick<Exam, 'exam_date'>, now: Date = new Date()): Urgency {
  if (!exam.exam_date) return 'sem_data';
  const days = daysUntil(exam.exam_date, now);
  if (days < 0) return 'passada';
  if (days === 0) return 'hoje';
  if (days <= 3) return 'urgente';
  if (days <= 7) return 'proxima';
  return 'futura';
}

/** Provas futuras (ou de hoje) ainda não realizadas, da mais próxima à mais distante. */
export function upcomingExams(exams: Exam[], now: Date = new Date()): Exam[] {
  return exams
    .filter((exam) => exam.status !== 'realizada' && exam.exam_date && daysUntil(exam.exam_date, now) >= 0)
    .sort((a, b) => (a.exam_date! < b.exam_date! ? -1 : a.exam_date! > b.exam_date! ? 1 : 0));
}
