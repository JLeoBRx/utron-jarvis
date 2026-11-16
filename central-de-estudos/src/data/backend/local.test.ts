import { beforeEach, describe, expect, it } from 'vitest';
import { createTestBackend } from '@/test/helpers';
import { AppError } from '@/lib/errors';
import type { LocalBackend } from './local';
import { createAcademicYear } from '../services/workspace';
import { createSubject } from '../services/subjects';
import { createExam, getExamDeletionImpact, deleteExam, updateExam } from '../services/exams';
import { createTopics } from '../services/topics';
import type { ExamInput } from '../schemas';

let db: LocalBackend;
let yearId: string;

const subjectInput = (name: string) => ({
  name,
  code: null,
  category: 'formacao_geral' as const,
  description: null,
  teacher: null,
  color: 'indigo',
});

const examInput = (subject_id: string, title = 'Avaliação 1'): ExamInput => ({
  subject_id,
  title,
  exam_date: null,
  exam_time: null,
  teacher: null,
  description: null,
  priority: 'media',
  status: 'nao_iniciada',
  score: null,
  max_score: null,
});

function materialFor(subject_id: string, exam_id: string | null) {
  return {
    subject_id,
    exam_id,
    kind: 'link' as const,
    category: 'complementares' as const,
    title: 'Vídeo-aula',
    description: null,
    origin: null,
    file_name: null,
    mime_type: null,
    size_bytes: null,
    storage_path: null,
    url: 'https://exemplo.org/aula',
    version: 1,
    replaced_at: null,
  };
}

beforeEach(async () => {
  db = createTestBackend();
  const { year } = await createAcademicYear(db, { name: 'Ano de teste' }, { activate: true });
  yearId = year.id;
});

describe('LocalBackend — integridade', () => {
  it('preenche id, user_id e datas na inserção', async () => {
    const subject = await createSubject(db, yearId, subjectInput('Física 2'));
    expect(subject.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(subject.user_id).toBe(db.userId);
    expect(subject.created_at).toBeTruthy();
    expect(subject.position).toBe(1);
  });

  it('rejeita referência a registro inexistente', async () => {
    await expect(createExam(db, examInput('00000000-0000-4000-8000-00000000dead'))).rejects.toMatchObject({
      code: 'integrity',
    });
  });

  it('não permite vincular material a prova de OUTRA disciplina', async () => {
    const fisica = await createSubject(db, yearId, subjectInput('Física 2'));
    const quimica = await createSubject(db, yearId, subjectInput('Química 2'));
    const provaFisica = await createExam(db, examInput(fisica.id));
    await expect(db.insert('materials', materialFor(quimica.id, provaFisica.id))).rejects.toThrow(
      /pertence a outra disciplina/,
    );
    const ok = await db.insert('materials', materialFor(fisica.id, provaFisica.id));
    expect(ok.exam_id).toBe(provaFisica.id);
  });

  it('impede nomes de disciplina duplicados no mesmo ano (sem diferenciar maiúsculas)', async () => {
    await createSubject(db, yearId, subjectInput('Física 2'));
    await expect(createSubject(db, yearId, subjectInput('  física 2 '))).rejects.toMatchObject({ code: 'conflict' });
  });

  it('impede dois anos letivos ativos', async () => {
    await expect(db.insert('academic_years', { name: 'Outro', start_date: null, end_date: null, is_active: true })).rejects.toBeInstanceOf(
      AppError,
    );
  });

  it('excluir a prova apaga conteúdos e PRESERVA materiais (desvinculados)', async () => {
    const fisica = await createSubject(db, yearId, subjectInput('Física 2'));
    const prova = await createExam(db, examInput(fisica.id));
    await createTopics(db, prova.id, ['Cinemática', 'Dinâmica']);
    const material = await db.insert('materials', materialFor(fisica.id, prova.id));

    const impact = await getExamDeletionImpact(db, prova.id);
    expect(impact).toMatchObject({ topics: 2, materials: 1 });

    await deleteExam(db, prova.id);
    expect(await db.count('exam_topics', { exam_id: prova.id })).toBe(0);
    const preserved = await db.get('materials', material.id);
    expect(preserved).not.toBeNull();
    expect(preserved!.exam_id).toBeNull();
    expect(preserved!.subject_id).toBe(fisica.id);
  });

  it('excluir a disciplina apaga em cascata provas, conteúdos, materiais e arquivos', async () => {
    const fisica = await createSubject(db, yearId, subjectInput('Física 2'));
    const prova = await createExam(db, examInput(fisica.id));
    await createTopics(db, prova.id, ['Cinemática']);
    const path = `${db.userId}/${fisica.id}/m1/slides.txt`;
    await db.storage.upload(path, new Blob(['conteúdo'], { type: 'text/plain' }));
    await db.insert('materials', {
      ...materialFor(fisica.id, prova.id),
      kind: 'arquivo',
      url: null,
      storage_path: path,
      file_name: 'slides.txt',
      mime_type: 'text/plain',
      size_bytes: 8,
    });

    await db.remove('subjects', fisica.id);
    expect(await db.count('exams')).toBe(0);
    expect(await db.count('exam_topics')).toBe(0);
    expect(await db.count('materials')).toBe(0);
    await expect(db.storage.download(path)).rejects.toMatchObject({ code: 'not_found' });
  });

  it('não permite mover para outra disciplina uma prova com materiais vinculados', async () => {
    const fisica = await createSubject(db, yearId, subjectInput('Física 2'));
    const quimica = await createSubject(db, yearId, subjectInput('Química 2'));
    const prova = await createExam(db, examInput(fisica.id));
    await createTopics(db, prova.id, ['Cinemática']);
    // Sem materiais: pode mover (conteúdos acompanham a prova).
    const movida = await updateExam(db, prova.id, examInput(quimica.id));
    expect(movida.subject_id).toBe(quimica.id);
    // Com material vinculado: bloqueia para não misturar disciplinas.
    await db.insert('materials', materialFor(quimica.id, prova.id));
    await expect(updateExam(db, prova.id, examInput(fisica.id))).rejects.toMatchObject({ code: 'integrity' });
  });

  it('armazena e recupera arquivos', async () => {
    const path = `${db.userId}/x/y/nota.txt`;
    await db.storage.upload(path, new Blob(['olá'], { type: 'text/plain' }));
    const blob = await db.storage.download(path);
    expect(await blob.text()).toBe('olá');
    await expect(db.storage.upload(path, new Blob(['b']))).rejects.toMatchObject({ code: 'conflict' });
  });
});

describe('LocalBackend — consultas', () => {
  it('filtra com in / null e ordena com NULLs por último', async () => {
    const fisica = await createSubject(db, yearId, subjectInput('Física 2'));
    await createExam(db, { ...examInput(fisica.id, 'Sem data'), exam_date: null });
    await createExam(db, { ...examInput(fisica.id, 'Dezembro'), exam_date: '2026-12-10' });
    await createExam(db, { ...examInput(fisica.id, 'Novembro'), exam_date: '2026-11-20' });
    const ordered = await db.list('exams', { orderBy: [{ column: 'exam_date', ascending: true }] });
    expect(ordered.map((e) => e.title)).toEqual(['Novembro', 'Dezembro', 'Sem data']);
    expect(await db.count('exams', { exam_date: null })).toBe(1);
    expect(await db.count('exams', { title: { in: ['Novembro', 'Dezembro'] } })).toBe(2);
    expect(await db.count('exams', { exam_date: { gte: '2026-12-01' } })).toBe(1);
  });
});
