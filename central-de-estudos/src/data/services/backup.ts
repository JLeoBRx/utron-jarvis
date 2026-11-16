import { AppError, errorMessage } from '@/lib/errors';
import type { DataBackend, DataMode } from '../backend/types';
import { TABLES_IN_DEPENDENCY_ORDER, type Insert, type TableName } from '../types';

export const BACKUP_APP_ID = 'central-de-estudos';
export const BACKUP_FORMAT_VERSION = 1;

type AnyRecord = Record<string, unknown> & { id: string };

export interface BackupFile {
  app: typeof BACKUP_APP_ID;
  format_version: number;
  exported_at: string;
  source_mode: DataMode;
  /** Arquivos (PDFs, imagens) ainda não entram no backup JSON. */
  files_included: false;
  counts: Partial<Record<TableName, number>>;
  tables: Partial<Record<TableName, AnyRecord[]>>;
}

export interface ImportReport {
  inserted: Partial<Record<TableName, number>>;
  skipped: Partial<Record<TableName, number>>;
  failed: { table: TableName; id: string; message: string }[];
}

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
    format_version: BACKUP_FORMAT_VERSION,
    exported_at: new Date().toISOString(),
    source_mode: db.mode,
    files_included: false,
    counts,
    tables,
  };
}

export function backupFileName(date = new Date()): string {
  const stamp = date.toISOString().slice(0, 16).replace(/[:T]/g, '-');
  return `central-de-estudos-backup-${stamp}.json`;
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
  return backup as BackupFile;
}

/**
 * Importa um backup SEM SOBRESCREVER nada: registros cujo identificador já
 * existe são ignorados (e contabilizados). Útil para migrar do modo local
 * para o Supabase ou restaurar dados apagados.
 */
export async function importBackup(
  db: DataBackend,
  backup: BackupFile,
  onProgress?: (table: TableName, index: number, total: number) => void,
): Promise<ImportReport> {
  const report: ImportReport = { inserted: {}, skipped: {}, failed: [] };
  const order = TABLES_IN_DEPENDENCY_ORDER.filter((t) => backup.tables[t]?.length);

  for (const [index, table] of order.entries()) {
    onProgress?.(table, index, order.length);
    const incoming = backup.tables[table] ?? [];
    const existing = await db.list(table);
    const existingIds = new Set(existing.map((r) => r.id));

    let rows = incoming.filter((r) => !existingIds.has(r.id));
    let skipped = incoming.length - rows.length;

    if (table === 'profiles') {
      // Um perfil por usuário: mantém o atual, se houver.
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
        // Tenta um a um para isolar apenas os registros problemáticos.
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
