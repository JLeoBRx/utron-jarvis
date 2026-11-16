import type { Insert, Patch, Row, TableName, UUID } from '../types';

export type Scalar = string | number | boolean;

/**
 * Condição de filtro por coluna:
 *  - valor simples → igualdade
 *  - `null`        → IS NULL
 *  - objeto        → operadores
 */
export type FilterCondition =
  | Scalar
  | null
  | { in: Scalar[] }
  | { neq: Scalar }
  | { gte: Scalar }
  | { lte: Scalar }
  | { notNull: true };

export type Where = Record<string, FilterCondition>;

export interface OrderBy {
  column: string;
  ascending?: boolean;
}

export interface ListQuery {
  where?: Where;
  orderBy?: OrderBy[];
  limit?: number;
}

export interface StoredFile {
  blob: Blob;
  mimeType: string;
  size: number;
}

export interface StorageBackend {
  upload(path: string, file: Blob, options?: { contentType?: string; upsert?: boolean }): Promise<void>;
  download(path: string): Promise<Blob>;
  /** URL temporária para visualização/download. */
  getUrl(path: string, expiresInSeconds?: number): Promise<string>;
  remove(paths: string[]): Promise<void>;
}

export type DataMode = 'supabase' | 'local';

/**
 * Interface única de acesso a dados. Implementada por:
 *  - `SupabaseBackend` (PostgreSQL + Storage, modo principal);
 *  - `LocalBackend` (IndexedDB, modo local enquanto o Supabase não é configurado).
 * Os serviços de domínio dependem apenas desta interface.
 */
export interface DataBackend {
  readonly mode: DataMode;
  readonly userId: UUID;
  list<T extends TableName>(table: T, query?: ListQuery): Promise<Row<T>[]>;
  get<T extends TableName>(table: T, id: UUID): Promise<Row<T> | null>;
  count<T extends TableName>(table: T, where?: Where): Promise<number>;
  insert<T extends TableName>(table: T, values: Insert<T>): Promise<Row<T>>;
  insertMany<T extends TableName>(table: T, values: Insert<T>[]): Promise<Row<T>[]>;
  update<T extends TableName>(table: T, id: UUID, patch: Patch<T>): Promise<Row<T>>;
  remove<T extends TableName>(table: T, id: UUID): Promise<void>;
  readonly storage: StorageBackend;
}
