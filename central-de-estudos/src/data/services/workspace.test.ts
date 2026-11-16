import { describe, expect, it } from 'vitest';
import { createTestBackend } from '@/test/helpers';
import { OFFICIAL_SUBJECTS } from '../seed/officialSubjects';
import { createAcademicYear, listAcademicYears, pickActiveYear, seedOfficialSubjects, setActiveAcademicYear } from './workspace';
import { listSubjects } from './subjects';

describe('disciplinas oficiais', () => {
  it('lista exatamente as 20 disciplinas oficiais, sem inventar códigos', () => {
    expect(OFFICIAL_SUBJECTS).toHaveLength(20);
    expect(OFFICIAL_SUBJECTS.filter((s) => s.category === 'formacao_geral')).toHaveLength(13);
    expect(OFFICIAL_SUBJECTS.filter((s) => s.category === 'formacao_tecnica')).toHaveLength(7);
    const mci = OFFICIAL_SUBJECTS.find((s) => s.name === 'Máquinas e Comandos Industriais');
    expect(mci?.code).toBeNull();
    const codes = OFFICIAL_SUBJECTS.map((s) => s.code).filter(Boolean);
    expect(new Set(codes).size).toBe(19);
    expect(OFFICIAL_SUBJECTS.find((s) => s.name === 'Matemática 2')?.code).toBe('INT.12845');
    expect(OFFICIAL_SUBJECTS.find((s) => s.name === 'Língua Portuguesa e Redação 2')?.code).toBe('INT.12840');
  });

  it('cadastra as 20 disciplinas vazias no ano letivo e não duplica ao repetir', async () => {
    const db = createTestBackend();
    const { year, seeded } = await createAcademicYear(db, { name: '2026' }, { activate: true, seedOfficialSubjects: true });
    expect(seeded).toHaveLength(20);
    const subjects = await listSubjects(db, year.id);
    expect(subjects.map((s) => s.name)).toEqual(OFFICIAL_SUBJECTS.map((s) => s.name));
    expect(subjects.every((s) => s.teacher === null && s.description === null)).toBe(true);
    expect(await db.count('exams')).toBe(0);
    expect(await db.count('exam_topics')).toBe(0);

    const again = await seedOfficialSubjects(db, year.id);
    expect(again).toHaveLength(0);
    expect(await db.count('subjects')).toBe(20);
  });
});

describe('anos letivos', () => {
  it('mantém apenas um ano ativo ao alternar', async () => {
    const db = createTestBackend();
    const { year: a } = await createAcademicYear(db, { name: '2026' }, { activate: true });
    const { year: b } = await createAcademicYear(db, { name: '2027' }, { activate: true });
    let years = await listAcademicYears(db);
    expect(years.filter((y) => y.is_active).map((y) => y.id)).toEqual([b.id]);
    await setActiveAcademicYear(db, a.id);
    years = await listAcademicYears(db);
    expect(pickActiveYear(years)?.id).toBe(a.id);
    expect(years.filter((y) => y.is_active)).toHaveLength(1);
  });

  it('valida o término depois do início', async () => {
    const db = createTestBackend();
    await expect(
      createAcademicYear(db, { name: 'X', start_date: '2026-12-01', end_date: '2026-02-01' }),
    ).rejects.toMatchObject({ code: 'validation' });
  });
});
