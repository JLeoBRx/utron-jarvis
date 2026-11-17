import { AppError } from '@/lib/errors';
import { extensionForMime } from '@/lib/files';
import type { DataBackend } from '../backend/types';
import { materialMetaSchema, parseOrThrow } from '../schemas';
import type { Material, NotebookScan, NotebookScanPage, UUID } from '../types';
import { removeFilesBestEffort } from './storageCleanup';
import { scanPagePath } from './storagePaths';

/** Edições aplicadas a uma página (guardadas para reprodutibilidade e auditoria). */
export interface PageEdits {
  rotation: 0 | 90 | 180 | 270;
  /** Quadrilátero do recorte em coordenadas normalizadas (0–1) da imagem já girada. */
  quad: [Point, Point, Point, Point] | null;
  enhance: 'original' | 'realce' | 'documento' | 'pb';
  brightness: number;
  contrast: number;
}

export interface Point {
  x: number;
  y: number;
}

export const DEFAULT_EDITS: PageEdits = { rotation: 0, quad: null, enhance: 'documento', brightness: 0, contrast: 0 };

/** Página pronta para salvar: a foto ORIGINAL intocada + a versão tratada. */
export interface ScanPageUpload {
  id: UUID;
  source: 'camera' | 'galeria';
  original: Blob;
  originalName: string;
  originalMime: string;
  processed: Blob;
  width: number;
  height: number;
  edits: PageEdits;
}

export interface SaveScanInput {
  /** Ids fixos permitem tentar de novo sem duplicar nada. */
  scanId: UUID;
  materialId: UUID;
  subject_id: UUID;
  exam_id: UUID | null;
  /** Nome do assunto (ex.: "Cinemática e velocidade média"). */
  topic: string | null;
  description: string | null;
  pages: ScanPageUpload[];
}

export interface SaveScanProgress {
  step: 'arquivos' | 'registros' | 'concluido';
  done: number;
  total: number;
}

export function defaultScanTitle(topic: string | null, subjectName: string | undefined, date = new Date()): string {
  if (topic?.trim()) return topic.trim().slice(0, 200);
  const day = date.toLocaleDateString('pt-BR');
  return `Caderno${subjectName ? ` — ${subjectName}` : ''} (${day})`.slice(0, 200);
}

function pagePaths(db: DataBackend, input: SaveScanInput, page: ScanPageUpload) {
  return {
    original: scanPagePath(db.userId, input.subject_id, input.scanId, page.id, 'original', extensionForMime(page.originalMime)),
    processed: scanPagePath(db.userId, input.subject_id, input.scanId, page.id, 'tratada', 'jpg'),
  };
}

/** Todos os caminhos que um salvamento grava (para limpar se o usuário cancelar). */
export function scanUploadPaths(db: DataBackend, input: SaveScanInput): string[] {
  return input.pages.flatMap((page) => {
    const p = pagePaths(db, input, page);
    return [p.original, p.processed];
  });
}

/**
 * Salva a digitalização:
 *   1. envia as fotos (original + tratada) de cada página;
 *   2. cria a digitalização (status "capturado" = pronta para leitura por IA);
 *   3. cria os registros das páginas, na ordem escolhida;
 *   4. cria o material do tipo "digitalizacao" na biblioteca.
 * Cada etapa verifica o que já existe — repetir após uma falha é seguro.
 */
export async function saveScan(
  db: DataBackend,
  input: SaveScanInput,
  meta: { title: string },
  onProgress?: (progress: SaveScanProgress) => void,
): Promise<{ scan: NotebookScan; material: Material }> {
  if (!input.pages.length) throw new AppError('validation', 'Fotografe ou selecione pelo menos uma página.');
  const values = parseOrThrow(materialMetaSchema, {
    subject_id: input.subject_id,
    exam_id: input.exam_id,
    category: 'caderno',
    title: meta.title,
    description: input.description,
    origin: 'Caderno (fotografado)',
  });

  const total = input.pages.length * 2;
  let done = 0;
  onProgress?.({ step: 'arquivos', done, total });
  for (const page of input.pages) {
    const paths = pagePaths(db, input, page);
    // upsert: reenviar após uma falha substitui o mesmo arquivo, sem duplicar.
    await db.storage.upload(paths.original, page.original, { contentType: page.originalMime, upsert: true });
    onProgress?.({ step: 'arquivos', done: ++done, total });
    await db.storage.upload(paths.processed, page.processed, { contentType: 'image/jpeg', upsert: true });
    onProgress?.({ step: 'arquivos', done: ++done, total });
  }

  onProgress?.({ step: 'registros', done, total });
  const scan =
    (await db.get('notebook_scans', input.scanId)) ??
    (await db.insert('notebook_scans', {
      id: input.scanId,
      subject_id: values.subject_id,
      exam_id: values.exam_id,
      summary_id: null,
      topic_label: input.topic?.trim() ? input.topic.trim().slice(0, 200) : null,
      status: 'capturado',
      page_count: input.pages.length,
      recognized: null,
      error: null,
    }));

  const existingPages = new Set((await db.list('notebook_scan_pages', { where: { scan_id: scan.id } })).map((p) => p.id));
  const newPages = input.pages
    .map((page, index) => ({ page, index }))
    .filter(({ page }) => !existingPages.has(page.id))
    .map(({ page, index }) => {
      const paths = pagePaths(db, input, page);
      return {
        id: page.id,
        scan_id: scan.id,
        position: index,
        original_path: paths.original,
        processed_path: paths.processed,
        material_id: null,
        recognized_text: null,
        confidence: null,
        needs_review: false,
        review_notes: null,
        source: page.source,
        original_file_name: page.originalName.slice(0, 255),
        original_mime_type: page.originalMime,
        original_size_bytes: page.original.size,
        processed_mime_type: 'image/jpeg',
        processed_size_bytes: page.processed.size,
        width: page.width,
        height: page.height,
        edits: page.edits as unknown as Record<string, unknown>,
      };
    });
  if (newPages.length) await db.insertMany('notebook_scan_pages', newPages);

  const totalBytes = input.pages.reduce((sum, p) => sum + p.original.size + p.processed.size, 0);
  const material =
    (await db.get('materials', input.materialId)) ??
    (await db.insert('materials', {
      id: input.materialId,
      ...values,
      kind: 'digitalizacao',
      scan_id: scan.id,
      file_name: null,
      mime_type: null,
      size_bytes: totalBytes,
      storage_path: null,
      url: null,
      version: 1,
      replaced_at: null,
    }));

  onProgress?.({ step: 'concluido', done: total, total });
  return { scan, material };
}

/** Cancela um salvamento incompleto: apaga registros e fotos já enviadas. */
export async function discardPartialScan(db: DataBackend, input: SaveScanInput): Promise<void> {
  if (await db.get('notebook_scans', input.scanId)) await db.remove('notebook_scans', input.scanId);
  await removeFilesBestEffort(db, scanUploadPaths(db, input));
}

export async function listScanPages(db: DataBackend, scanId: UUID): Promise<NotebookScanPage[]> {
  return db.list('notebook_scan_pages', { where: { scan_id: scanId }, orderBy: [{ column: 'position', ascending: true }] });
}
