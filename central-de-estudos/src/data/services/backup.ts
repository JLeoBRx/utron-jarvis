import { strFromU8, strToU8, unzipSync, zipSync, type Zippable } from 'fflate';
import { AppError, errorMessage } from '@/lib/errors';
import type { DataBackend, DataMode } from '../backend/types';
import { STORAGE_PATH_COLUMNS } from '../backend/relations';
import { TABLES_IN_DEPENDENCY_ORDER, type Insert, type TableName } from '../types';
import { reassignPathOwner } from './storagePaths';

export const BACKUP_APP_ID = 'central-de-estudos';
/** v1: só dados (JSON). v2: dados + arquivos (ZIP). Ambos são importáveis. */
export const BACKUP_FORMAT_VERSION = 2;

type AnyRecord = Record<string, unknown> & { id: string };

export interface BackupFile {
  app: typeof BACKUP_APP_ID;
  format_version: number;
  exported_at: string;
  source_mode: DataMode;
  files_included: boolean;
  counts: Partial<Record<TableName, number>>;
  tables: Partial<Record<TableName, AnyRecord[]>>;
  /** Arquivos que não puderam ser lidos no momento da exportação. */
  missing_files?: string[];
}

/** Backup completo carregado na memória (dados + bytes dos arquivos). */
export interface BackupBundle {
  backup: BackupFile;
  files: Map<string, Uint8Array>;
}

export interface ImportReport {
  inserted: Partial<Record<TableName, number>>;
  skipped: Partial<Record<TableName, number>>;
  failed: { table: TableName; id: string; message: string }[];
  filesUploaded: number;
  filesMissing: number;
}

const ARCHIVE_DATA = 'backup.json';
const ARCHIVE_FILES = 'arquivos/';

/** Exporta TODOS os registros do usuário (todas as tabelas). */
export async function exportBackup(db: DataBackend): Promise<BackupFile> {
  const tables: BackupFile['tables'] = {};
  const counts: BackupFile['counts'] = {};
  for (const table of TABLES_IN_DEPENDENCY_ORDER) {
    const rows = (await db.list(table)) as unknown as AnyRecord[];
    tables[table] = rows;
    counts[table] = rows.length;
  }
  return {
    app: BACKUP_APP_ID,
    format_version: 1,
    exported_at: new Date().toISOString(),
    source_mode: db.mode,
    files_included: false,
    counts,
    tables,
  };
}

/** Caminhos de arquivos referenciados pelos registros do backup. */
export function referencedFilePaths(backup: BackupFile): string[] {
  const paths = new Set<string>();
  for (const [table, columns] of Object.entries(STORAGE_PATH_COLUMNS) as [TableName, string[]][]) {
    for (const row of backup.tables[table] ?? []) {
      for (const column of columns) {
        const value = row[column];
        if (typeof value === 'string' && value) paths.add(value);
      }
    }
  }
  return [...paths];
}

/**
 * Exporta dados + arquivos em um único .zip:
 *   backup.json            → registros
 *   arquivos/<caminho>     → PDFs, imagens, fotos originais e tratadas
 */
export async function exportBackupArchive(
  db: DataBackend,
  onProgress?: (done: number, total: number) => void,
): Promise<{ blob: Blob; backup: BackupFile }> {
  const data = await exportBackup(db);
  const paths = referencedFilePaths(data);
  const entries: Zippable = {};
  const missing: string[] = [];
  for (const [index, path] of paths.entries()) {
    onProgress?.(index, paths.length);
    try {
      const blob = await db.storage.download(path);
      // Imagens e PDFs já são comprimidos: armazenar sem recompressão é mais rápido.
      entries[`${ARCHIVE_FILES}${path}`] = [new Uint8Array(await blob.arrayBuffer()), { level: 0 }];
    } catch {
      missing.push(path);
    }
  }
  onProgress?.(paths.length, paths.length);
  const backup: BackupFile = {
    ...data,
    format_version: BACKUP_FORMAT_VERSION,
    files_included: true,
    missing_files: missing.length ? missing : undefined,
  };
  entries[ARCHIVE_DATA] = [strToU8(JSON.stringify(backup, null, 2)), { level: 6 }];
  const zipped = zipSync(entries);
  return { blob: new Blob([zipped as Uint8Array<ArrayBuffer>], { type: 'application/zip' }), backup };
}

export function backupFileName(date = new Date(), extension: 'zip' | 'json' = 'zip'): string {
  const stamp = date.toISOString().slice(0, 16).replace(/[:T]/g, '-');
  return `central-de-estudos-backup-${stamp}.${extension}`;
}

export function parseBackupFile(text: string): BackupFile {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new AppError('validation', 'O arquivo não é um JSON válido.');
  }
  const backup = data as Partial<BackupFile>;
  if (!backup || backup.app !== BACKUP_APP_ID || typeof backup.tables !== 'object' || backup.tables === null) {
    throw new AppError('validation', 'Este arquivo não é um backup da Central de Estudos.');
  }
  if (typeof backup.format_version !== 'number' || backup.format_version > BACKUP_FORMAT_VERSION) {
    throw new AppError('validation', 'Versão de backup não suportada. Atualize a aplicação.');
  }
  for (const [table, rows] of Object.entries(backup.tables)) {
    if (!TABLES_IN_DEPENDENCY_ORDER.includes(table as TableName)) {
      throw new AppError('validation', `Tabela desconhecida no backup: ${table}.`);
    }
    if (!Array.isArray(rows) || rows.some((r) => !r || typeof (r as AnyRecord).id !== 'string')) {
      throw new AppError('validation', `Registros inválidos na tabela ${table}.`);
    }
  }
  return { files_included: false, ...backup } as BackupFile;
}

/** Lê um backup .zip (v2, com arquivos) ou .json (v1, só dados). */
export async function readBackupBundle(file: Blob): Promise<BackupBundle> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const isZip = bytes[0] === 0x50 && bytes[1] === 0x4b; // "PK"
  if (!isZip) return { backup: parseBackupFile(strFromU8(bytes)), files: new Map() };

  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(bytes);
  } catch {
    throw new AppError('validation', 'O arquivo .zip está corrompido.');
  }
  const data = entries[ARCHIVE_DATA];
  if (!data) throw new AppError('validation', 'Este .zip não é um backup da Central de Estudos.');
  const files = new Map<string, Uint8Array>();
  for (const [name, content] of Object.entries(entries)) {
    if (name.startsWith(ARCHIVE_FILES) && !name.endsWith('/')) files.set(name.slice(ARCHIVE_FILES.length), content);
  }
  return { backup: parseBackupFile(strFromU8(data)), files };
}

function guessMime(path: string): string | undefined {
  const ext = path.split('.').pop()?.toLowerCase();
  const map: Record<string, string> = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    txt: 'text/plain',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    heic: 'image/heic',
    heif: 'image/heif',
  };
  return ext ? map[ext] : undefined;
}

/**
 * Importa um backup SEM SOBRESCREVER nada: registros cujo identificador já
 * existe são ignorados. Os caminhos dos arquivos são transferidos para a pasta
 * do usuário atual (exigência das políticas do Storage) e cada arquivo é
 * enviado ANTES do registro que aponta para ele.
 */
export async function importBackup(
  db: DataBackend,
  input: BackupFile | BackupBundle,
  onProgress?: (table: TableName, index: number, total: number) => void,
): Promise<ImportReport> {
  const { backup, files } = 'backup' in input ? input : { backup: input, files: new Map<string, Uint8Array>() };
  const report: ImportReport = { inserted: {}, skipped: {}, failed: [], filesUploaded: 0, filesMissing: 0 };
  const order = TABLES_IN_DEPENDENCY_ORDER.filter((t) => backup.tables[t]?.length);
  const uploaded = new Set<string>();

  for (const [index, table] of order.entries()) {
    onProgress?.(table, index, order.length);
    const incoming = backup.tables[table] ?? [];
    const existing = await db.list(table);
    const existingIds = new Set(existing.map((r) => r.id));

    let rows = incoming.filter((r) => !existingIds.has(r.id));
    let skipped = incoming.length - rows.length;

    if (table === 'profiles') {
      if (existing.length) {
        skipped += rows.length;
        rows = [];
      } else {
        skipped += Math.max(0, rows.length - 1);
        rows = rows.slice(0, 1);
      }
    }
    if (table === 'academic_years' && existing.some((y) => (y as { is_active: boolean }).is_active)) {
      rows = rows.map((r) => ({ ...r, is_active: false }));
    }

    // Arquivos: novo dono no caminho + envio antes do registro.
    const pathColumns = STORAGE_PATH_COLUMNS[table] ?? [];
    if (pathColumns.length) {
      rows = rows.map((row) => {
        const copy: AnyRecord = { ...row };
        for (const column of pathColumns) {
          const value = copy[column];
          if (typeof value === 'string' && value) copy[column] = reassignPathOwner(value, db.userId);
        }
        return copy;
      });
      for (const [i, row] of rows.entries()) {
        for (const column of pathColumns) {
          const target = row[column];
          const original = incoming.find((r) => r.id === row.id)?.[column];
          if (typeof target !== 'string' || typeof original !== 'string' || uploaded.has(target)) continue;
          const bytes = files.get(original);
          if (!bytes) {
            report.filesMissing += 1;
            continue;
          }
          try {
            await db.storage.upload(target, new Blob([bytes as Uint8Array<ArrayBuffer>]), { contentType: guessMime(target), upsert: true });
            uploaded.add(target);
            report.filesUploaded += 1;
          } catch (error) {
            report.failed.push({ table, id: row.id, message: `Arquivo não enviado: ${errorMessage(error)}` });
            rows[i] = { ...row, __skip: true };
          }
        }
      }
      rows = rows.filter((r) => !r.__skip);
    }

    const prepared = rows.map((r) => {
      const { user_id: _ignored, ...rest } = r;
      return rest as unknown as Insert<typeof table>;
    });

    let inserted = 0;
    for (let i = 0; i < prepared.length; i += 200) {
      const chunk = prepared.slice(i, i + 200);
      try {
        await db.insertMany(table, chunk);
        inserted += chunk.length;
      } catch {
        for (const row of chunk) {
          try {
            await db.insert(table, row);
            inserted += 1;
          } catch (error) {
            report.failed.push({ table, id: (row as { id?: string }).id ?? '?', message: errorMessage(error) });
          }
        }
      }
    }
    report.inserted[table] = inserted;
    report.skipped[table] = skipped;
  }
  return report;
}
