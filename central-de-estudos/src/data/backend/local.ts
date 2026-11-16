import Dexie, { type Table } from 'dexie';
import { AppError, toAppError } from '@/lib/errors';
import { newId } from '@/lib/ids';
import type { Insert, Patch, Row, TableName, UUID } from '../types';
import { applyQuery } from './query';
import { FRIENDLY_TABLE_NAMES, RELATIONS, STORAGE_PATH_COLUMNS, UNIQUE_RULES, type Relation } from './relations';
import type { DataBackend, ListQuery, StorageBackend, Where } from './types';

/** Usuário fixo do modo local (não há autenticação: os dados ficam neste navegador). */
export const LOCAL_USER_ID = '00000000-0000-4000-8000-000000000001';
export const LOCAL_DB_NAME = 'central-de-estudos';

type AnyRow = Record<string, unknown> & { id: string };

interface StoredFileRecord {
  path: string;
  data: ArrayBuffer;
  mime_type: string;
  size: number;
  created_at: string;
}

const TABLE_INDEXES: Record<TableName, string> = {
  profiles: 'id, user_id',
  academic_years: 'id',
  subjects: 'id, academic_year_id',
  exams: 'id, subject_id',
  exam_topics: 'id, exam_id',
  materials: 'id, subject_id, exam_id',
  summaries: 'id, subject_id, exam_id',
  summary_versions: 'id, summary_id',
  summary_sources: 'id, summary_id, material_id',
  flashcards: 'id, subject_id, exam_id',
  flashcard_reviews: 'id, flashcard_id',
  questions: 'id, subject_id, exam_id',
  quizzes: 'id, subject_id, exam_id',
  quiz_attempts: 'id, quiz_id',
  study_sessions: 'id, subject_id',
  calendar_events: 'id, subject_id',
  notebook_scans: 'id, subject_id',
  notebook_scan_pages: 'id, scan_id',
  ai_operations: 'id',
};

export class LocalDatabase extends Dexie {
  files!: Table<StoredFileRecord, string>;

  constructor(name = LOCAL_DB_NAME) {
    super(name);
    this.version(1).stores({ ...TABLE_INDEXES, files: 'path' });
  }
}

const MATCH_MESSAGES: Record<string, string> = {
  subject_id: 'pertence a outra disciplina',
  exam_id: 'pertence a outra prova',
};

function normalize(value: unknown, caseInsensitive: boolean): unknown {
  if (caseInsensitive && typeof value === 'string') return value.trim().toLocaleLowerCase('pt-BR');
  return value;
}

class LocalStorageBackend implements StorageBackend {
  private urls = new Map<string, string>();

  constructor(private readonly db: LocalDatabase) {}

  async upload(path: string, file: Blob, options?: { contentType?: string; upsert?: boolean }): Promise<void> {
    const existing = await this.db.files.get(path);
    if (existing && !options?.upsert) {
      throw new AppError('conflict', 'Já existe um arquivo neste caminho.');
    }
    const data = await file.arrayBuffer();
    await this.db.files.put({
      path,
      data,
      mime_type: options?.contentType ?? file.type ?? 'application/octet-stream',
      size: file.size,
      created_at: new Date().toISOString(),
    });
  }

  async download(path: string): Promise<Blob> {
    const record = await this.db.files.get(path);
    if (!record) throw new AppError('not_found', 'Arquivo não encontrado.');
    return new Blob([record.data], { type: record.mime_type });
  }

  async getUrl(path: string): Promise<string> {
    const cached = this.urls.get(path);
    if (cached) return cached;
    const blob = await this.download(path);
    const url = URL.createObjectURL(blob);
    this.urls.set(path, url);
    return url;
  }

  async remove(paths: string[]): Promise<void> {
    if (!paths.length) return;
    await this.db.files.bulkDelete(paths);
    for (const path of paths) {
      const url = this.urls.get(path);
      if (url) URL.revokeObjectURL(url);
      this.urls.delete(path);
    }
  }
}

/**
 * Adaptador local (IndexedDB). Aplica as mesmas regras de integridade do
 * PostgreSQL: chaves estrangeiras (inclusive compostas), exclusão em cascata,
 * SET NULL e unicidade.
 */
export class LocalBackend implements DataBackend {
  readonly mode = 'local' as const;
  readonly userId = LOCAL_USER_ID;
  readonly storage: StorageBackend;

  constructor(readonly db: LocalDatabase = new LocalDatabase()) {
    this.storage = new LocalStorageBackend(db);
  }

  private t(table: TableName): Table<AnyRow, string> {
    return this.db.table(table);
  }

  private async run<R>(fn: () => Promise<R>): Promise<R> {
    try {
      return await fn();
    } catch (error) {
      if (error instanceof AppError) throw error;
      const name = (error as { name?: string; inner?: { name?: string } }).name;
      const innerName = (error as { inner?: { name?: string } }).inner?.name;
      if (name === 'QuotaExceededError' || innerName === 'QuotaExceededError') {
        throw new AppError('storage', 'O armazenamento do navegador está cheio.', error);
      }
      throw toAppError(error);
    }
  }

  async list<T extends TableName>(table: T, query?: ListQuery): Promise<Row<T>[]> {
    return this.run(async () => {
      const rows = await this.t(table).toArray();
      return applyQuery(rows, query) as unknown as Row<T>[];
    });
  }

  async get<T extends TableName>(table: T, id: UUID): Promise<Row<T> | null> {
    return this.run(async () => ((await this.t(table).get(id)) ?? null) as Row<T> | null);
  }

  async count<T extends TableName>(table: T, where?: Where): Promise<number> {
    const rows = await this.list(table, { where });
    return rows.length;
  }

  async insert<T extends TableName>(table: T, values: Insert<T>): Promise<Row<T>> {
    const [row] = await this.insertMany(table, [values]);
    return row!;
  }

  async insertMany<T extends TableName>(table: T, values: Insert<T>[]): Promise<Row<T>[]> {
    if (!values.length) return [];
    return this.run(() =>
      this.db.transaction('rw', this.db.tables, async () => {
        const inserted: AnyRow[] = [];
        for (const value of values) {
          const now = new Date().toISOString();
          const raw = value as Record<string, unknown>;
          const row: AnyRow = {
            ...raw,
            id: (raw.id as string | undefined) ?? newId(),
            user_id: this.userId,
            // Datas originais são preservadas na importação de backup.
            created_at: (raw.created_at as string | undefined) ?? now,
            updated_at: (raw.updated_at as string | undefined) ?? now,
          };
          if (await this.t(table).get(row.id)) {
            throw new AppError('conflict', `Já existe um registro (${FRIENDLY_TABLE_NAMES[table]}) com este identificador.`);
          }
          await this.checkForeignKeys(table, row);
          await this.checkUnique(table, row);
          await this.t(table).add(row);
          inserted.push(row);
        }
        return inserted as unknown as Row<T>[];
      }),
    );
  }

  async update<T extends TableName>(table: T, id: UUID, patch: Patch<T>): Promise<Row<T>> {
    return this.run(() =>
      this.db.transaction('rw', this.db.tables, async () => {
        const existing = await this.t(table).get(id);
        if (!existing) throw new AppError('not_found', `Registro não encontrado (${FRIENDLY_TABLE_NAMES[table]}).`);
        const clean = Object.fromEntries(
          Object.entries(patch as Record<string, unknown>).filter(
            ([key]) => !['id', 'user_id', 'created_at', 'updated_at'].includes(key),
          ),
        );
        const row: AnyRow = { ...existing, ...clean, updated_at: new Date().toISOString() };
        await this.checkForeignKeys(table, row);
        await this.checkUnique(table, row);
        await this.checkDependentsOnMatchChange(table, existing, row);
        await this.t(table).put(row);
        return row as unknown as Row<T>;
      }),
    );
  }

  async remove<T extends TableName>(table: T, id: UUID): Promise<void> {
    await this.run(() =>
      this.db.transaction('rw', this.db.tables, async () => {
        const paths: string[] = [];
        await this.cascadeDelete(table, id, paths);
        if (paths.length) await this.db.files.bulkDelete(paths);
      }),
    );
  }

  // -------------------------------------------------------------------------
  // Integridade
  // -------------------------------------------------------------------------
  private async checkForeignKeys(table: TableName, row: AnyRow): Promise<void> {
    for (const rel of RELATIONS) {
      if (rel.table !== table) continue;
      const value = row[rel.column];
      if (value === null || value === undefined) continue;
      const parent = await this.t(rel.parent).get(value as string);
      if (!parent) {
        throw new AppError('integrity', `O registro relacionado (${FRIENDLY_TABLE_NAMES[rel.parent]}) não existe.`);
      }
      for (const column of rel.match ?? []) {
        if (parent[column] !== row[column]) {
          const reason = MATCH_MESSAGES[column] ?? `não corresponde em "${column}"`;
          throw new AppError('integrity', `O registro selecionado (${FRIENDLY_TABLE_NAMES[rel.parent]}) ${reason}.`);
        }
      }
    }
  }

  private async checkUnique(table: TableName, row: AnyRow): Promise<void> {
    for (const rule of UNIQUE_RULES) {
      if (rule.table !== table) continue;
      if (rule.whereTrue && !row[rule.whereTrue]) continue;
      const others = await this.t(table).toArray();
      const conflict = others.find(
        (other) =>
          other.id !== row.id &&
          (!rule.whereTrue || Boolean(other[rule.whereTrue])) &&
          rule.columns.every((column) => {
            const ci = rule.caseInsensitive?.includes(column) ?? false;
            return normalize(other[column], ci) === normalize(row[column], ci);
          }),
      );
      if (conflict) throw new AppError('conflict', rule.message);
    }
  }

  /** Equivale a ON UPDATE NO ACTION das chaves compostas. */
  private async checkDependentsOnMatchChange(table: TableName, before: AnyRow, after: AnyRow): Promise<void> {
    const dependents: Relation[] = RELATIONS.filter(
      (rel) => rel.parent === table && rel.match?.some((column) => before[column] !== after[column]),
    );
    for (const rel of dependents) {
      const children = await this.t(rel.table).filter((child) => child[rel.column] === before.id).count();
      if (children > 0) {
        throw new AppError(
          'integrity',
          `Não é possível alterar: existem registros vinculados (${FRIENDLY_TABLE_NAMES[rel.table]}).`,
        );
      }
    }
  }

  private async cascadeDelete(table: TableName, id: string, paths: string[]): Promise<void> {
    const row = await this.t(table).get(id);
    if (!row) return;
    for (const rel of RELATIONS) {
      if (rel.parent !== table) continue;
      const children = await this.t(rel.table).filter((child) => child[rel.column] === id).toArray();
      for (const child of children) {
        if (rel.onDelete === 'cascade') {
          await this.cascadeDelete(rel.table, child.id, paths);
        } else {
          await this.t(rel.table).update(child.id, { [rel.column]: null, updated_at: new Date().toISOString() });
        }
      }
    }
    for (const column of STORAGE_PATH_COLUMNS[table] ?? []) {
      const path = row[column];
      if (typeof path === 'string' && path) paths.push(path);
    }
    await this.t(table).delete(id);
  }

  /** Apaga TODOS os dados locais (usado apenas por ação explícita do usuário). */
  async wipe(): Promise<void> {
    await this.db.transaction('rw', this.db.tables, async () => {
      await Promise.all(this.db.tables.map((table) => table.clear()));
    });
  }
}
