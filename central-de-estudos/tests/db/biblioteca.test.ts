/**
 * Fase 3 contra Supabase REAL: biblioteca (Storage privado + versões) e
 * scanner de cadernos (fotos originais/tratadas, páginas, material).
 */
import { beforeAll, describe, expect, it } from 'vitest';
import { createAcademicYear } from '@/data/services/workspace';
import { listSubjects } from '@/data/services/subjects';
import { createExam } from '@/data/services/exams';
import {
  createLinkMaterial,
  deleteMaterial,
  listMaterialVersions,
  replaceMaterialFile,
  uploadMaterialFile,
  type UploadSource,
} from '@/data/services/materials';
import { DEFAULT_EDITS, listScanPages, saveScan, type SaveScanInput } from '@/data/services/scans';
import { exportBackupArchive, importBackup, readBackupBundle } from '@/data/services/backup';
import { buildScanReadingRequest } from '@/data/ai/scanReading';
import { newId } from '@/lib/ids';
import { createTestBackend } from '@/test/helpers';
import { signUp, stackAvailable } from './helpers';

const available = await stackAvailable();

function file(name: string, content: string, type: string): UploadSource {
  const blob = new Blob([content], { type });
  return { name, type, size: blob.size, blob };
}

const meta = (subject_id: string, exam_id: string | null = null) => ({
  subject_id,
  exam_id,
  category: 'slides' as const,
  title: 'Slides',
  description: null,
  origin: 'Professor',
});

function scanInput(subjectId: string, examId: string | null): SaveScanInput {
  return {
    scanId: newId(),
    materialId: newId(),
    subject_id: subjectId,
    exam_id: examId,
    topic: 'Cinemática',
    description: null,
    pages: [0, 1].map((i) => ({
      id: newId(),
      source: 'camera' as const,
      original: new Blob([`foto-original-${i}`], { type: 'image/jpeg' }),
      originalName: `IMG_${i}.jpg`,
      originalMime: 'image/jpeg',
      processed: new Blob([`foto-tratada-${i}`], { type: 'image/jpeg' }),
      width: 1000,
      height: 1400,
      edits: DEFAULT_EDITS,
    })),
  };
}

describe.skipIf(!available)('Supabase real — biblioteca e scanner', () => {
  let alice: Awaited<ReturnType<typeof signUp>>;
  let bob: Awaited<ReturnType<typeof signUp>>;
  let fisicaId: string;
  let quimicaId: string;

  beforeAll(async () => {
    alice = await signUp();
    bob = await signUp();
    const { year } = await createAcademicYear(alice.db, { name: '2026' }, { activate: true, seedOfficialSubjects: true });
    const subjects = await listSubjects(alice.db, year.id);
    fisicaId = subjects.find((s) => s.name === 'Física 2')!.id;
    quimicaId = subjects.find((s) => s.name === 'Química 2')!.id;
  });

  it('upload de PDF, DOCX, PPTX e imagem no bucket privado', async () => {
    const cases: [string, string][] = [
      ['aula.pdf', 'application/pdf'],
      ['texto.docx', ''],
      ['slides.pptx', 'application/octet-stream'],
      ['quadro.png', 'image/png'],
      ['notas.txt', 'text/plain'],
    ];
    for (const [name, type] of cases) {
      const m = await uploadMaterialFile(alice.db, meta(fisicaId), file(name, `conteúdo de ${name}`, type));
      expect(m.storage_path!.startsWith(`${alice.userId}/`)).toBe(true);
      expect(await (await alice.db.storage.download(m.storage_path!)).text()).toBe(`conteúdo de ${name}`);
    }
  });

  it('substituição preserva o original e as versões ficam protegidas por RLS', async () => {
    const v1 = await uploadMaterialFile(alice.db, meta(fisicaId), file('lista.pdf', 'versão 1', 'application/pdf'));
    const v2 = await replaceMaterialFile(alice.db, v1, file('lista.pdf', 'versão 2', 'application/pdf'));
    expect(v2.version).toBe(2);
    const [old] = await listMaterialVersions(alice.db, v1.id);
    expect(await (await alice.db.storage.download(old!.storage_path)).text()).toBe('versão 1');
    expect(await (await alice.db.storage.download(v2.storage_path!)).text()).toBe('versão 2');

    expect(await listMaterialVersions(bob.db, v1.id)).toEqual([]);
    await expect(bob.db.storage.download(old!.storage_path)).rejects.toBeTruthy();
  });

  it('exclusão remove registro, versões e arquivos do Storage', async () => {
    const v1 = await uploadMaterialFile(alice.db, meta(fisicaId), file('apagar.pdf', 'a', 'application/pdf'));
    const v2 = await replaceMaterialFile(alice.db, v1, file('apagar.pdf', 'b', 'application/pdf'));
    const [old] = await listMaterialVersions(alice.db, v1.id);
    await deleteMaterial(alice.db, v2);
    expect(await alice.db.get('materials', v1.id)).toBeNull();
    await expect(alice.db.storage.download(v2.storage_path!)).rejects.toBeTruthy();
    await expect(alice.db.storage.download(old!.storage_path)).rejects.toBeTruthy();
  });

  it('scanner: salva fotos originais e tratadas, páginas e material; outro usuário não acessa', async () => {
    const prova = await createExam(alice.db, {
      subject_id: fisicaId,
      title: 'Avaliação 2',
      exam_date: null,
      exam_time: null,
      teacher: null,
      description: null,
      priority: 'alta',
      status: 'nao_iniciada',
      score: null,
      max_score: null,
    });
    const input = scanInput(fisicaId, prova.id);
    const { scan, material } = await saveScan(alice.db, input, { title: 'Cinemática' });
    expect(material).toMatchObject({ kind: 'digitalizacao', scan_id: scan.id, exam_id: prova.id });
    const pages = await listScanPages(alice.db, scan.id);
    expect(pages).toHaveLength(2);
    expect(await (await alice.db.storage.download(pages[1]!.original_path)).text()).toBe('foto-original-1');
    expect(await (await alice.db.storage.download(pages[1]!.processed_path!)).text()).toBe('foto-tratada-1');

    // pedido para a IA (Fase 7) aponta para arquivos que existem no Storage
    const request = buildScanReadingRequest(scan, pages, { subjectName: 'Física 2', examTitle: 'Avaliação 2' });
    for (const page of request.paginas) {
      expect((await alice.db.storage.download(page.imagem.storage_path)).size).toBeGreaterThan(0);
    }

    expect(await listScanPages(bob.db, scan.id)).toEqual([]);
    await expect(bob.db.storage.download(pages[0]!.original_path)).rejects.toBeTruthy();

    // repetir não duplica
    await saveScan(alice.db, input, { title: 'Cinemática' });
    expect(await alice.db.count('notebook_scan_pages', { scan_id: scan.id })).toBe(2);

    await deleteMaterial(alice.db, material);
    expect(await alice.db.get('notebook_scans', scan.id)).toBeNull();
    await expect(alice.db.storage.download(pages[0]!.original_path)).rejects.toBeTruthy();
  });

  it('fotos HEIC de iPhone são aceitas como original', async () => {
    const path = `${alice.userId}/${fisicaId}/cadernos/${newId()}/p-original.heic`;
    await alice.db.storage.upload(path, new Blob(['heic'], { type: 'image/heic' }), { contentType: 'image/heic' });
    expect((await alice.db.storage.download(path)).size).toBe(4);
  });

  it('banco recusa caderno sem digitalização e digitalização de outra disciplina', async () => {
    const { error } = await alice.client.from('materials').insert({
      subject_id: fisicaId,
      kind: 'digitalizacao',
      category: 'caderno',
      title: 'sem scan',
    });
    expect(error?.code).toBe('23514');

    const { scan, material } = await saveScan(alice.db, scanInput(fisicaId, null), { title: 'X' });
    // remove só o material, mantendo a digitalização "solta" para o teste da chave
    await alice.client.from('materials').delete().eq('id', material.id);
    const { error: fkError } = await alice.client.from('materials').insert({
      subject_id: quimicaId,
      kind: 'digitalizacao',
      category: 'caderno',
      title: 'outra disciplina',
      scan_id: scan.id,
    });
    expect(fkError?.code).toBe('23503');
  });

  it('links continuam funcionando com o novo esquema', async () => {
    const link = await createLinkMaterial(alice.db, { ...meta(fisicaId), url: 'https://exemplo.org/video' });
    expect(link).toMatchObject({ kind: 'link', scan_id: null });
  });

  it('backup .zip do modo local é restaurado na nuvem com os arquivos (caminhos na pasta da conta)', async () => {
    const local = createTestBackend();
    const { year } = await createAcademicYear(local, { name: 'Local' }, { activate: true, seedOfficialSubjects: true });
    const [subject] = await listSubjects(local, year.id);
    const m = await uploadMaterialFile(local, meta(subject!.id), file('local.pdf', 'pdf local', 'application/pdf'));
    await replaceMaterialFile(local, m, file('local.pdf', 'pdf local v2', 'application/pdf'));
    await saveScan(local, scanInput(subject!.id, null), { title: 'Caderno local' });

    const { blob } = await exportBackupArchive(local);
    const carol = await signUp();
    const report = await importBackup(carol.db, await readBackupBundle(blob));
    expect(report.failed).toEqual([]);
    expect(report.filesUploaded).toBe(6);

    const [cloudMaterial] = await carol.db.list('materials', { where: { kind: 'arquivo' } });
    expect(cloudMaterial!.storage_path!.startsWith(`${carol.userId}/`)).toBe(true);
    expect(await (await carol.db.storage.download(cloudMaterial!.storage_path!)).text()).toBe('pdf local v2');
    const pages = await carol.db.list('notebook_scan_pages');
    expect(await (await carol.db.storage.download(pages[0]!.original_path)).text()).toMatch(/^foto-original-/);
  });
});
