import { describe, expect, it } from 'vitest';
import type { Exam, ExamTopic } from '@/data/types';
import { examUrgency, groupTopicsByExam, pendingExamsProgress, topicsProgress, upcomingExams } from './progress';
import { parseTopicLines } from '@/data/services/topics';
import { daysUntil, relativeDaysLabel } from './dates';

const topic = (exam_id: string, status: ExamTopic['status'], position = 1) =>
  ({ id: `${exam_id}-${position}`, exam_id, status, position }) as ExamTopic;
const exam = (id: string, exam_date: string | null, status: Exam['status'] = 'nao_iniciada') =>
  ({ id, exam_date, status }) as Exam;

describe('progresso', () => {
  it('é nulo sem conteúdos (não confunde ausência de dados com 0%)', () => {
    expect(topicsProgress([]).value).toBeNull();
  });

  it('pondera pelo status de estudo', () => {
    const p = topicsProgress([topic('a', 'dominado'), topic('a', 'nao_estudado', 2), topic('a', 'revisado', 3)]);
    expect(p.value).toBeCloseTo((1 + 0 + 2 / 3) / 3);
    expect(p.byStatus).toEqual({ nao_estudado: 1, estudando: 0, revisado: 1, dominado: 1 });
  });

  it('o progresso agregado ignora provas já realizadas', () => {
    const exams = [exam('a', null), exam('b', null, 'realizada')];
    const byExam = groupTopicsByExam([topic('a', 'estudando'), topic('b', 'dominado')]);
    expect(pendingExamsProgress(exams, byExam).value).toBeCloseTo(1 / 3);
  });
});

describe('datas e urgência', () => {
  const now = new Date(2026, 10, 16, 15, 0); // 16/11/2026 (mês 0-indexado)
  it('calcula dias de calendário no fuso local', () => {
    expect(daysUntil('2026-11-16', now)).toBe(0);
    expect(daysUntil('2026-11-17', now)).toBe(1);
    expect(daysUntil('2026-11-10', now)).toBe(-6);
    expect(relativeDaysLabel(5)).toBe('Em 5 dias');
  });

  it('classifica a urgência e ordena as próximas provas', () => {
    expect(examUrgency({ exam_date: '2026-11-18' }, now)).toBe('urgente');
    expect(examUrgency({ exam_date: '2026-11-22' }, now)).toBe('proxima');
    expect(examUrgency({ exam_date: null }, now)).toBe('sem_data');
    const list = upcomingExams(
      [exam('c', '2026-12-01'), exam('a', '2026-11-10'), exam('b', '2026-11-20'), exam('d', '2026-11-21', 'realizada')],
      now,
    );
    expect(list.map((e) => e.id)).toEqual(['b', 'c']);
  });
});

describe('cadastro de conteúdos em lote', () => {
  it('separa uma lista colada em conteúdos', () => {
    expect(parseTopicLines('- Cinemática\n\n• Velocidade média\n2) Aceleração\n  MRU  ')).toEqual([
      'Cinemática',
      'Velocidade média',
      'Aceleração',
      'MRU',
    ]);
  });
});
