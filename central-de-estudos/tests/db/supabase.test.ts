/**
 * Testes de integração com um Supabase REAL (local, via Docker):
 * PostgreSQL + GoTrue (Auth) + PostgREST + Storage.
 *
 * Verificam: migrações, RLS (isolamento entre usuários), chaves compostas
 * (não misturar provas/disciplinas), cascata/SET NULL, tradução de erros e
 * políticas do bucket privado. Pré-requisito: `npm run supabase:local:up`.
 */
import { beforeAll, describe, expect, it } from 'vitest';
import { createAcademicYear } from '@/data/services/workspace';
import { listSubjects } from '@/data/services/subjects';
import { createExam, deleteExam, updateExam } from '@/data/services/exams';
import { createTopics, moveTopic, listTopics } from '@/data/services/topics';
import { exportBackup, importBackup } from '@/data/services/backup';
import type { ExamInput } from '@/data/schemas';
import { newId } from '@/lib/ids';
import { newClient, signUp, stackAvailable, SUPABASE_URL } from './helpers';

const URL = SUPABASE_URL;
const available = await stackAvailable();
if (!available) {
  console.warn(`[db] Supabase local indisponível em ${URL} — rode "npm run supabase:local:up". Testes ignorados.`);
}

const examInput = (subject_id: string, title = 'Avaliação 1'): ExamInput => ({
  subject_id,
  title,
  exam_date: '2026-12-01',
  exam_time: '08:30',
  teacher: null,
  description: null,
  priority: 'alta',
  status: 'nao_iniciada',
  score: null,
  max_score: null,
});

const linkMaterial = (subject_id: string, exam_id: string | null) => ({
  subject_id,
  exam_id,
  kind: 'link' as const,
  category: 'complementares' as const,
  title: 'Vídeo-aula',
  description: null,
  origin: 'YouTube',
  file_name: null,
  mime_type: null,
  size_bytes: null,
  storage_path: null,
  url: 'https://exemplo.org/aula',
  version: 1,
  replaced_at: null,
  scan_id: null,
});

describe.skipIf(!available)('Supabase real — banco, RLS e storage', () => {
  let alice: Awaited<ReturnType<typeof signUp>>;
  let bob: Awaited<ReturnType<typeof signUp>>;
  let aliceYearId: string;

  beforeAll(async () => {
    alice = await signUp();
    bob = await signUp();
    const { year, seeded } = await createAcademicYear(alice.db, { name: '2026' }, { activate: true, seedOfficialSubjects: true });
    aliceYearId = year.id;
    expect(seeded).toHaveLength(20);
  });

  it('cadastra as 20 disciplinas oficiais com user_id preenchido pelo banco', async () => {
    const subjects = await listSubjects(alice.db, aliceYearId);
    expect(subjects).toHaveLength(20);
    expect(subjects.every((s) => s.user_id === alice.userId)).toBe(true);
    expect(subjects.find((s) => s.name === 'Máquinas e Comandos Industriais')?.code).toBeNull();
    expect(subjects.find((s) => s.name === 'Sistemas Digitais')?.code).toBe('INT.12853');
  });

  it('RLS: um usuário não enxerga nem altera dados de outro', async () => {
    expect(await bob.db.count('subjects')).toBe(0);
    const [aliceSubject] = await listSubjects(alice.db, aliceYearId);
    expect(await bob.db.get('subjects', aliceSubject!.id)).toBeNull();
    await expect(bob.db.update('subjects', aliceSubject!.id, { name: 'invadido' })).rejects.toMatchObject({
      code: 'not_found',
    });
    await bob.db.remove('subjects', aliceSubject!.id); // não apaga nada (RLS)
    expect(await alice.db.get('subjects', aliceSubject!.id)).not.toBeNull();
  });

  it('RLS: não permite criar registro apontando para disciplina de outro usuário', async () => {
    const [aliceSubject] = await listSubjects(alice.db, aliceYearId);
    await expect(createExam(bob.db, examInput(aliceSubject!.id))).rejects.toMatchObject({ code: 'integrity' });
  });

  it('RLS: não permite forjar user_id de outro usuário', async () => {
    const { error } = await bob.client
      .from('academic_years')
      .insert({ name: 'forjado', user_id: alice.userId, is_active: false });
    expect(error?.code).toBe('42501');
  });

  it('usuário anônimo (sem login) não lê nada', async () => {
    const anon = newClient();
    const { data, error } = await anon.from('subjects').select('*');
    expect(error?.code ?? (data?.length === 0 ? 'vazio' : 'vazou')).not.toBe('vazou');
  });

  it('chave composta: material só pode ser vinculado a prova da mesma disciplina', async () => {
    const subjects = await listSubjects(alice.db, aliceYearId);
    const fisica = subjects.find((s) => s.name === 'Física 2')!;
    const quimica = subjects.find((s) => s.name === 'Química 2')!;
    const prova = await createExam(alice.db, examInput(fisica.id));
    await expect(alice.db.insert('materials', linkMaterial(quimica.id, prova.id))).rejects.toThrow(
      'A prova selecionada pertence a outra disciplina.',
    );
    const ok = await alice.db.insert('materials', linkMaterial(fisica.id, prova.id));
    expect(ok.exam_id).toBe(prova.id);
  });

  it('excluir prova apaga conteúdos e preserva materiais desvinculados (SET NULL)', async () => {
    const subjects = await listSubjects(alice.db, aliceYearId);
    const mat = subjects.find((s) => s.name === 'Matemática 2')!;
    const prova = await createExam(alice.db, examInput(mat.id, 'Avaliação 2'));
    expect(prova.exam_time).toBe('08:30:00');
    await createTopics(alice.db, prova.id, ['Funções', 'Logaritmos', 'Progressões']);
    const material = await alice.db.insert('materials', linkMaterial(mat.id, prova.id));

    await deleteExam(alice.db, prova.id);
    expect(await alice.db.count('exam_topics', { exam_id: prova.id })).toBe(0);
    const preserved = await alice.db.get('materials', material.id);
    expect(preserved).toMatchObject({ exam_id: null, subject_id: mat.id });
  });

  it('não permite mover prova com materiais para outra disciplina', async () => {
    const subjects = await listSubjects(alice.db, aliceYearId);
    const bio = subjects.find((s) => s.name === 'Biologia 2')!;
    const geo = subjects.find((s) => s.name === 'Geografia 2')!;
    const prova = await createExam(alice.db, examInput(bio.id, 'Avaliação 3'));
    await alice.db.insert('materials', linkMaterial(bio.id, prova.id));
    await expect(updateExam(alice.db, prova.id, examInput(geo.id, 'Avaliação 3'))).rejects.toMatchObject({
      code: 'integrity',
    });
  });

  it('traduz violações de unicidade e de validação', async () => {
    await expect(
      alice.db.insert('subjects', {
        academic_year_id: aliceYearId,
        name: '  física 2 ',
        code: null,
        category: 'formacao_geral',
        description: null,
        teacher: null,
        color: 'blue',
        position: 99,
        archived_at: null,
      }),
    ).rejects.toThrow('Já existe uma disciplina com este nome neste ano letivo.');

    await expect(
      alice.db.insert('academic_years', { name: 'Outro ativo', start_date: null, end_date: null, is_active: true }),
    ).rejects.toThrow('Já existe um ano letivo ativo.');

    const { error } = await alice.client.from('exams').insert({ subject_id: newId(), title: 'x', priority: 'urgentíssima' });
    expect(error?.code).toBe('23514');
  });

  it('reordena conteúdos', async () => {
    const subjects = await listSubjects(alice.db, aliceYearId);
    const hist = subjects.find((s) => s.name === 'História 2')!;
    const prova = await createExam(alice.db, examInput(hist.id, 'Avaliação 4'));
    const [a, b, c] = await createTopics(alice.db, prova.id, ['A', 'B', 'C']);
    await moveTopic(alice.db, prova.id, c!.id, -1);
    expect((await listTopics(alice.db, [prova.id])).map((t) => t.title)).toEqual(['A', 'C', 'B']);
    await moveTopic(alice.db, prova.id, a!.id, -1); // já é o primeiro: sem efeito
    expect((await listTopics(alice.db, [prova.id])).map((t) => t.id)).toEqual([a!.id, c!.id, b!.id]);
  });

  it('backup: exporta da conta e importa em outra conta sem conflitos', async () => {
    const backup = await exportBackup(alice.db);
    const carol = await signUp();
    const report = await importBackup(carol.db, JSON.parse(JSON.stringify(backup)));
    // Os ids são globais: importar os MESMOS registros em outra conta conflita
    // com os da Alice (chave primária) — eles aparecem como falhas, não como
    // sobrescrita. Já o caminho principal (modo local → nuvem) é coberto abaixo.
    expect(await alice.db.count('subjects')).toBe(20);
    expect(report.inserted.subjects ?? 0).toBe(0);
  });

  it('backup: migra dados do modo local para a nuvem', async () => {
    const { createTestBackend } = await import('@/test/helpers');
    const local = createTestBackend();
    const { year } = await createAcademicYear(local, { name: 'Ano local' }, { activate: true, seedOfficialSubjects: true });
    const [first] = await listSubjects(local, year.id);
    const prova = await createExam(local, examInput(first!.id, 'Prova local'));
    await createTopics(local, prova.id, ['Tópico 1', 'Tópico 2']);

    const dave = await signUp();
    const report = await importBackup(dave.db, await exportBackup(local));
    expect(report.failed).toEqual([]);
    expect(report.inserted).toMatchObject({ academic_years: 1, subjects: 20, exams: 1, exam_topics: 2 });
    const cloudExam = await dave.db.get('exams', prova.id);
    expect(cloudExam).toMatchObject({ title: 'Prova local', user_id: dave.userId });
  });

  describe('storage (bucket privado "materiais")', () => {
    it('envia, baixa e gera URL assinada na própria pasta', async () => {
      const path = `${alice.userId}/teste/${newId()}/anotacoes.txt`;
      await alice.db.storage.upload(path, new Blob(['Velocidade média = Δs/Δt'], { type: 'text/plain' }));
      const blob = await alice.db.storage.download(path);
      expect(await blob.text()).toBe('Velocidade média = Δs/Δt');
      const url = await alice.db.storage.getUrl(path, 60);
      expect(url).toContain('/storage/v1/object/sign/materiais/');
      const res = await fetch(url.replace(/^https?:\/\/[^/]+/, URL));
      expect(await res.text()).toBe('Velocidade média = Δs/Δt');
    });

    it('bloqueia envio na pasta de outro usuário e leitura de arquivos alheios', async () => {
      await expect(
        bob.db.storage.upload(`${alice.userId}/invasao.txt`, new Blob(['x'], { type: 'text/plain' })),
      ).rejects.toMatchObject({ code: 'storage' });

      const path = `${alice.userId}/privado/${newId()}.txt`;
      await alice.db.storage.upload(path, new Blob(['segredo'], { type: 'text/plain' }));
      await expect(bob.db.storage.download(path)).rejects.toBeTruthy();
    });

    it('recusa tipos de arquivo não permitidos', async () => {
      await expect(
        alice.db.storage.upload(`${alice.userId}/x/${newId()}.exe`, new Blob(['MZ'], { type: 'application/x-msdownload' })),
      ).rejects.toMatchObject({ code: 'storage' });
    });
  });
});
