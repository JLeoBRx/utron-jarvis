import { describe, expect, it } from 'vitest';
import { createTestBackend } from '@/test/helpers';
import { createAcademicYear } from './workspace';
import { listSubjects } from './subjects';
import { createExam } from './exams';
import { createTopics } from './topics';
import { exportBackup, importBackup, parseBackupFile } from './backup';

describe('backup', () => {
  it('exporta e importa sem perder dados e sem sobrescrever na segunda importação', async () => {
    const source = createTestBackend();
    const { year } = await createAcademicYear(source, { name: '2026' }, { activate: true, seedOfficialSubjects: true });
    const [fisica] = await listSubjects(source, year.id);
    const prova = await createExam(source, {
      subject_id: fisica!.id,
      title: 'Avaliação 2',
      exam_date: '2026-12-03',
      exam_time: '10:00',
      teacher: null,
      description: null,
      priority: 'alta',
      status: 'em_preparacao',
      score: null,
      max_score: null,
    });
    await createTopics(source, prova.id, ['Cinemática', 'Velocidade média']);

    const backup = parseBackupFile(JSON.stringify(await exportBackup(source)));
    expect(backup.counts).toMatchObject({ academic_years: 1, subjects: 20, exams: 1, exam_topics: 2 });

    const target = createTestBackend();
    const report = await importBackup(target, backup);
    expect(report.failed).toEqual([]);
    expect(report.inserted).toMatchObject({ academic_years: 1, subjects: 20, exams: 1, exam_topics: 2 });
    const imported = await target.get('exams', prova.id);
    expect(imported).toMatchObject({ title: 'Avaliação 2', exam_time: '10:00:00', created_at: prova.created_at });

    const second = await importBackup(target, backup);
    expect(second.inserted).toMatchObject({ subjects: 0, exams: 0 });
    expect(second.skipped).toMatchObject({ subjects: 20, exams: 1 });
    expect(await target.count('subjects')).toBe(20);
  });

  it('recusa arquivos que não são backups da Central de Estudos', () => {
    expect(() => parseBackupFile('{"foo":1}')).toThrow(/não é um backup/);
    expect(() => parseBackupFile('não é json')).toThrow(/JSON válido/);
  });
});
