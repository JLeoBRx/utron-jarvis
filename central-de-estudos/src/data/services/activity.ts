import type { DataBackend } from '../backend/types';
import type { UUID } from '../types';

export type ActivityKind = 'material' | 'resumo' | 'simulado' | 'sessao' | 'prova';

export interface ActivityItem {
  id: string;
  kind: ActivityKind;
  title: string;
  subjectId: UUID | null;
  examId: UUID | null;
  at: string;
  detail?: string;
}

/**
 * Atividades recentes do ano letivo, derivadas dos próprios registros
 * (nada é inventado): materiais enviados, resumos atualizados, simulados
 * finalizados, sessões de estudo e provas cadastradas/alteradas.
 */
export async function listRecentActivity(db: DataBackend, subjectIds: UUID[], limit = 8): Promise<ActivityItem[]> {
  if (!subjectIds.length) return [];
  const inSubjects = { subject_id: { in: subjectIds } };
  const [materials, summaries, sessions, exams, quizzes] = await Promise.all([
    db.list('materials', { where: inSubjects, orderBy: [{ column: 'created_at', ascending: false }], limit }),
    db.list('summaries', { where: inSubjects, orderBy: [{ column: 'updated_at', ascending: false }], limit }),
    db.list('study_sessions', { where: inSubjects, orderBy: [{ column: 'started_at', ascending: false }], limit }),
    db.list('exams', { where: inSubjects, orderBy: [{ column: 'updated_at', ascending: false }], limit }),
    db.list('quizzes', { where: inSubjects }),
  ]);
  const quizById = new Map(quizzes.map((q) => [q.id, q]));
  const attempts = quizzes.length
    ? await db.list('quiz_attempts', {
        where: { quiz_id: { in: quizzes.map((q) => q.id) }, status: 'finalizada' },
        orderBy: [{ column: 'finished_at', ascending: false }],
        limit,
      })
    : [];

  const items: ActivityItem[] = [
    ...materials.map((m) => ({
      id: `material:${m.id}`,
      kind: 'material' as const,
      title: m.title,
      subjectId: m.subject_id,
      examId: m.exam_id,
      at: m.created_at,
    })),
    ...summaries.map((s) => ({
      id: `resumo:${s.id}`,
      kind: 'resumo' as const,
      title: s.title,
      subjectId: s.subject_id,
      examId: s.exam_id,
      at: s.updated_at,
    })),
    ...attempts.map((a) => {
      const quiz = quizById.get(a.quiz_id);
      return {
        id: `simulado:${a.id}`,
        kind: 'simulado' as const,
        title: quiz?.title ?? 'Simulado',
        subjectId: quiz?.subject_id ?? null,
        examId: quiz?.exam_id ?? null,
        at: a.finished_at ?? a.updated_at,
        detail: a.score !== null ? `${Math.round(a.score)}% de aproveitamento` : undefined,
      };
    }),
    ...sessions.map((s) => ({
      id: `sessao:${s.id}`,
      kind: 'sessao' as const,
      title: `Sessão de estudo · ${s.duration_minutes} min`,
      subjectId: s.subject_id,
      examId: s.exam_id,
      at: s.started_at,
    })),
    ...exams.map((e) => ({
      id: `prova:${e.id}`,
      kind: 'prova' as const,
      title: e.title,
      subjectId: e.subject_id,
      examId: e.id,
      at: e.updated_at,
      detail: e.created_at === e.updated_at ? 'Prova cadastrada' : 'Prova atualizada',
    })),
  ];

  return items.sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, limit);
}
