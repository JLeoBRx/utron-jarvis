import Dexie from 'dexie';
import { beforeEach, describe, expect, it } from 'vitest';
import { LocalBackend, LocalDatabase } from '@/data/backend/local';
import { createTestBackend } from '@/test/helpers';
import { newId } from '@/lib/ids';
import { checkUpload, storageSafeName, titleFromFileName, youtubeEmbedUrl } from '@/lib/files';
import type { DataBackend } from '../backend/types';
import { createAcademicYear } from './workspace';
import { listSubjects } from './subjects';
import { createExam, deleteExam } from './exams';
import {
  createLinkMaterial,
  deleteMaterial,
  listMaterialVersions,
  replaceMaterialFile,
  updateMaterialMeta,
  uploadMaterialFile,
  type UploadSource,
} from './materials';
import { DEFAULT_EDITS, discardPartialScan, listScanPages, saveScan, type SaveScanInput } from './scans';
import { exportBackupArchive, importBackup, readBackupBundle } from './backup';
import { buildScanReadingRequest, manualReadingPrompt, parseScanReadingResult, scanReadingJsonSchema } from '../ai/scanReading';
import { deleteSubject } from './subjects';

function file(name: string, content: string, type = ''): UploadSource {
  const blob = new Blob([content], { type });
  return { name, type, size: blob.size, blob };
}

let db: LocalBackend;
let fisica: { id: string; name: string };
let quimica: { id: string };

async function exam(subjectId: string, title = 'Avaliação 2') {
  return createExam(db, {
    subject_id: subjectId,
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
}

const meta = (subject_id: string, exam_id: string | null = null) => ({
  subject_id,
  exam_id,
  category: 'slides' as const,
  title: 'Slides da aula 3',
  description: null,
  origin: 'Professor',
});

beforeEach(async () => {
  db = createTestBackend();
  const { year } = await createAcademicYear(db, { name: '2026' }, { activate: true, seedOfficialSubjects: true });
  const subjects = await listSubjects(db, year.id);
  fisica = subjects.find((s) => s.name === 'Física 2')!;
  quimica = subjects.find((s) => s.name === 'Química 2')!;
});

describe('validação de arquivos', () => {
  it('aceita os formatos da biblioteca pela extensão, mesmo sem MIME', () => {
    for (const name of ['a.pdf', 'b.docx', 'c.pptx', 'd.txt', 'e.png', 'f.jpg', 'g.JPEG', 'h.webp']) {
      expect(checkUpload({ name, type: '', size: 10 }).ok, name).toBe(true);
    }
    expect(checkUpload({ name: 'virus.exe', type: 'application/x-msdownload', size: 10 })).toMatchObject({ ok: false });
    expect(checkUpload({ name: 'vazio.pdf', type: 'application/pdf', size: 0 })).toMatchObject({ ok: false, reason: 'O arquivo está vazio.' });
    expect(checkUpload({ name: 'grande.pdf', type: 'application/pdf', size: 51 * 1024 * 1024 })).toMatchObject({ ok: false });
  });

  it('gera nomes seguros para o storage e títulos legíveis', () => {
    expect(storageSafeName('Aula 3 — Cinemática (v2).PDF')).toBe('Aula-3-Cinematica-v2.pdf');
    expect(titleFromFileName('lista_de_exercicios_2.pdf')).toBe('lista de exercicios 2');
    expect(youtubeEmbedUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ');
    expect(youtubeEmbedUrl('https://youtu.be/dQw4w9WgXcQ?t=10')).toBe('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ');
    expect(youtubeEmbedUrl('https://exemplo.org/video')).toBeNull();
  });
});

describe('materiais', () => {
  it('envia arquivo para a pasta do usuário e registra o material', async () => {
    const m = await uploadMaterialFile(db, meta(fisica.id), file('Aula 3.pdf', '%PDF-1.4 conteúdo'));
    expect(m).toMatchObject({ kind: 'arquivo', mime_type: 'application/pdf', version: 1, file_name: 'Aula 3.pdf' });
    expect(m.storage_path).toMatch(new RegExp(`^${db.userId}/${fisica.id}/materiais/${m.id}/v1-Aula-3\\.pdf$`));
    expect(await (await db.storage.download(m.storage_path!)).text()).toBe('%PDF-1.4 conteúdo');
  });

  it('recusa formato inválido sem criar registro nem arquivo', async () => {
    await expect(uploadMaterialFile(db, meta(fisica.id), file('script.exe', 'MZ'))).rejects.toMatchObject({ code: 'validation' });
    expect(await db.count('materials')).toBe(0);
    expect(await db.db.files.count()).toBe(0);
  });

  it('se o registro falhar, remove o arquivo enviado (sem órfãos)', async () => {
    const provaQuimica = await exam(quimica.id);
    // prova de outra disciplina → o banco recusa o registro
    await expect(uploadMaterialFile(db, meta(fisica.id, provaQuimica.id), file('a.pdf', 'x'))).rejects.toMatchObject({
      code: 'integrity',
    });
    expect(await db.db.files.count()).toBe(0);
  });

  it('substituir PRESERVA o arquivo original como versão anterior', async () => {
    const v1 = await uploadMaterialFile(db, meta(fisica.id), file('lista.pdf', 'versão 1'));
    const v2 = await replaceMaterialFile(db, v1, file('lista-corrigida.pdf', 'versão 2'));
    expect(v2).toMatchObject({ version: 2, file_name: 'lista-corrigida.pdf' });
    expect(await (await db.storage.download(v2.storage_path!)).text()).toBe('versão 2');
    const versions = await listMaterialVersions(db, v1.id);
    expect(versions).toHaveLength(1);
    expect(versions[0]).toMatchObject({ version_number: 1, file_name: 'lista.pdf', storage_path: v1.storage_path });
    expect(await (await db.storage.download(versions[0]!.storage_path)).text()).toBe('versão 1');

    const v3 = await replaceMaterialFile(db, v2, file('lista-final.pdf', 'versão 3'));
    expect(v3.version).toBe(3);
    expect((await listMaterialVersions(db, v1.id)).map((v) => v.version_number)).toEqual([2, 1]);
  });

  it('excluir apaga o material, as versões e TODOS os arquivos', async () => {
    const v1 = await uploadMaterialFile(db, meta(fisica.id), file('lista.pdf', 'v1'));
    const v2 = await replaceMaterialFile(db, v1, file('lista.pdf', 'v2'));
    expect(await db.db.files.count()).toBe(2);
    await deleteMaterial(db, v2);
    expect(await db.count('materials')).toBe(0);
    expect(await db.count('material_versions')).toBe(0);
    expect(await db.db.files.count()).toBe(0);
  });

  it('links: valida o endereço', async () => {
    await expect(createLinkMaterial(db, { ...meta(fisica.id), url: 'exemplo.org' })).rejects.toThrow(/https:\/\//);
    const link = await createLinkMaterial(db, { ...meta(fisica.id), category: 'complementares', url: 'https://youtu.be/dQw4w9WgXcQ' });
    expect(link).toMatchObject({ kind: 'link', storage_path: null });
  });

  it('organização: move material para uma prova da mesma disciplina; excluir a prova preserva o material', async () => {
    const prova = await exam(fisica.id);
    const m = await uploadMaterialFile(db, meta(fisica.id), file('a.pdf', 'x'));
    const moved = await updateMaterialMeta(db, m, { ...meta(fisica.id, prova.id), title: 'Novo nome' });
    expect(moved).toMatchObject({ exam_id: prova.id, title: 'Novo nome' });
    await deleteExam(db, prova.id);
    expect(await db.get('materials', m.id)).toMatchObject({ exam_id: null });
    expect(await db.db.files.count()).toBe(1);
  });
});

function scanInput(subjectId: string, examId: string | null, pages = 3): SaveScanInput {
  return {
    scanId: newId(),
    materialId: newId(),
    subject_id: subjectId,
    exam_id: examId,
    topic: 'Cinemática e velocidade média',
    description: null,
    pages: Array.from({ length: pages }, (_, i) => ({
      id: newId(),
      source: i === 0 ? 'camera' : 'galeria',
      original: new Blob([`original-${i}`], { type: 'image/jpeg' }),
      originalName: `IMG_00${i}.jpg`,
      originalMime: 'image/jpeg',
      processed: new Blob([`tratada-${i}`], { type: 'image/jpeg' }),
      width: 1200,
      height: 1600,
      edits: { ...DEFAULT_EDITS, rotation: i === 1 ? 90 : 0 },
    })),
  };
}

describe('scanner — salvamento', () => {
  it('salva originais intocados, versões tratadas, páginas em ordem e o material', async () => {
    const prova = await exam(fisica.id);
    const input = scanInput(fisica.id, prova.id);
    const progress: number[] = [];
    const { scan, material } = await saveScan(db, input, { title: 'Cinemática' }, (p) => progress.push(p.done));
    expect(scan).toMatchObject({ status: 'capturado', page_count: 3, exam_id: prova.id, topic_label: 'Cinemática e velocidade média' });
    expect(material).toMatchObject({ kind: 'digitalizacao', category: 'caderno', scan_id: scan.id, exam_id: prova.id });
    expect(progress.at(-1)).toBe(6);

    const pages = await listScanPages(db, scan.id);
    expect(pages.map((p) => p.position)).toEqual([0, 1, 2]);
    expect(pages.map((p) => p.id)).toEqual(input.pages.map((p) => p.id));
    expect(pages[1]).toMatchObject({ source: 'galeria', width: 1200, height: 1600, original_file_name: 'IMG_001.jpg' });
    expect((pages[1]!.edits as { rotation: number }).rotation).toBe(90);
    expect(await (await db.storage.download(pages[0]!.original_path)).text()).toBe('original-0');
    expect(await (await db.storage.download(pages[0]!.processed_path!)).text()).toBe('tratada-0');
    expect(pages[0]!.original_path).toMatch(new RegExp(`^${db.userId}/${fisica.id}/cadernos/${scan.id}/`));
  });

  it('repetir o salvamento após falha não duplica nada', async () => {
    const input = scanInput(fisica.id, null, 2);
    await saveScan(db, input, { title: 'X' });
    await saveScan(db, input, { title: 'X' });
    expect(await db.count('notebook_scans')).toBe(1);
    expect(await db.count('notebook_scan_pages')).toBe(2);
    expect(await db.count('materials')).toBe(1);
    expect(await db.db.files.count()).toBe(4);
  });

  it('cancelar um salvamento parcial apaga registros e fotos', async () => {
    const input = scanInput(fisica.id, null, 2);
    await saveScan(db, input, { title: 'X' });
    await discardPartialScan(db, input);
    expect(await db.count('notebook_scans')).toBe(0);
    expect(await db.count('materials')).toBe(0);
    expect(await db.db.files.count()).toBe(0);
  });

  it('excluir o material do caderno apaga a digitalização, as páginas e as fotos', async () => {
    const { material } = await saveScan(db, scanInput(fisica.id, null, 2), { title: 'X' });
    await deleteMaterial(db, material);
    expect(await db.count('notebook_scans')).toBe(0);
    expect(await db.count('notebook_scan_pages')).toBe(0);
    expect(await db.count('materials')).toBe(0);
    expect(await db.db.files.count()).toBe(0);
  });

  it('excluir a disciplina apaga também cadernos e versões de arquivos', async () => {
    await saveScan(db, scanInput(fisica.id, null, 1), { title: 'X' });
    const m = await uploadMaterialFile(db, meta(fisica.id), file('a.pdf', 'v1'));
    await replaceMaterialFile(db, m, file('a.pdf', 'v2'));
    await deleteSubject(db, fisica.id);
    expect(await db.db.files.count()).toBe(0);
    expect(await db.count('material_versions')).toBe(0);
  });

  it('caderno digitalizado não pode mudar de disciplina', async () => {
    const { material } = await saveScan(db, scanInput(fisica.id, null, 1), { title: 'X' });
    await expect(updateMaterialMeta(db, material, { ...meta(quimica.id), category: 'caderno' })).rejects.toMatchObject({
      code: 'validation',
    });
  });
});

describe('preparação para IA (contrato, sem chamada a modelo)', () => {
  it('monta o pedido de leitura com imagens tratadas, originais e ordem', async () => {
    const input = scanInput(fisica.id, null, 2);
    const { scan } = await saveScan(db, input, { title: 'X' });
    const pages = await listScanPages(db, scan.id);
    const request = buildScanReadingRequest(scan, [...pages].reverse(), { subjectName: 'Física 2', examTitle: null });
    expect(request.paginas.map((p) => p.page_id)).toEqual(input.pages.map((p) => p.id));
    expect(request.paginas[0]!.imagem.storage_path).toBe(pages[0]!.processed_path);
    expect(request.paginas[0]!.original.storage_path).toBe(pages[0]!.original_path);
    expect(request.instrucoes).toMatch(/Não invente anotações/);
    expect(request.contexto.assunto).toBe('Cinemática e velocidade média');
  });

  it('valida a resposta do modelo e rejeita páginas desconhecidas', () => {
    const pages = [{ id: 'p1' }];
    const ok = {
      versao: 1,
      paginas: [{ page_id: 'p1', posicao: 0, blocos: [{ tipo: 'formula', conteudo: 'v_m = \\frac{\\Delta s}{\\Delta t}', confianca: 0.9, incerto: false }], trechos_ilegiveis: [] }],
      assuntos: [{ titulo: 'Velocidade média', paginas: [0] }],
      formulas: [{ latex: 'v_m = \\frac{\\Delta s}{\\Delta t}', pagina: 0, confianca: 0.9, verificar: false }],
      pontos_para_revisao: [],
    };
    expect(parseScanReadingResult(ok, pages).assuntos[0]!.titulo).toBe('Velocidade média');
    expect(() => parseScanReadingResult({ ...ok, paginas: [{ ...ok.paginas[0], page_id: 'x' }] }, pages)).toThrow(/desconhecidas/);
    expect(() => parseScanReadingResult({ versao: 1 }, pages)).toThrow();
    expect(scanReadingJsonSchema()).toMatchObject({ type: 'object' });
    expect(manualReadingPrompt({ subjectName: 'Física 2', examTitle: 'Avaliação 2', topic: null, pageCount: 3 })).toMatch(/3 páginas/);
  });
});

describe('backup com arquivos (.zip)', () => {
  async function populate(source: DataBackend) {
    const m = await uploadMaterialFile(source, meta(fisica.id), file('lista.pdf', 'v1'));
    await replaceMaterialFile(source, m, file('lista.pdf', 'v2'));
    await saveScan(source, scanInput(fisica.id, null, 2), { title: 'Caderno' });
  }

  it('exporta dados + arquivos e restaura em outro dono, reescrevendo os caminhos', async () => {
    await populate(db);
    const { blob, backup } = await exportBackupArchive(db);
    expect(backup).toMatchObject({ format_version: 2, files_included: true });
    expect(backup.missing_files).toBeUndefined();

    // destino com OUTRO usuário (como migrar do modo local para uma conta)
    const otherUser = '11111111-2222-4333-8444-555555555555';
    const target = createTestBackend() as LocalBackend & { userId: string };
    Object.defineProperty(target, 'userId', { value: otherUser });
    const report = await importBackup(target, await readBackupBundle(blob));
    expect(report.failed).toEqual([]);
    expect(report.filesUploaded).toBe(6); // 1 atual + 1 versão + 2×2 fotos
    expect(report.filesMissing).toBe(0);

    const [material] = await target.list('materials', { where: { kind: 'arquivo' } });
    expect(material!.storage_path!.startsWith(`${otherUser}/`)).toBe(true);
    expect(await (await target.storage.download(material!.storage_path!)).text()).toBe('v2');
    const [version] = await target.list('material_versions');
    expect(await (await target.storage.download(version!.storage_path)).text()).toBe('v1');
    const pages = await target.list('notebook_scan_pages', { orderBy: [{ column: 'position' }] });
    expect(await (await target.storage.download(pages[0]!.original_path)).text()).toBe('original-0');

    const again = await importBackup(target, await readBackupBundle(blob));
    expect(again.inserted).toMatchObject({ materials: 0, notebook_scan_pages: 0 });
  });
});

describe('atualização do banco local (v1 → v2)', () => {
  it('preserva os dados existentes ao abrir a nova versão do banco', async () => {
    const name = `upgrade-${newId()}`;
    const v1 = new Dexie(name);
    v1.version(1).stores({ subjects: 'id, academic_year_id', materials: 'id, subject_id, exam_id', files: 'path' });
    await v1.table('subjects').add({ id: 's1', name: 'Física 2', academic_year_id: 'y1' });
    await v1.table('materials').add({ id: 'm1', subject_id: 's1', kind: 'link', url: 'https://x.org', title: 'Link' });
    v1.close();

    const upgraded = new LocalBackend(new LocalDatabase(name));
    expect(await upgraded.get('subjects', 's1')).toMatchObject({ name: 'Física 2' });
    expect(await upgraded.get('materials', 'm1')).toMatchObject({ title: 'Link' });
    expect(await upgraded.count('material_versions')).toBe(0);
  });
});
