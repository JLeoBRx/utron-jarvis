import type { PostgrestError, SupabaseClient } from '@supabase/supabase-js';
import { AppError, isNetworkError, toAppError } from '@/lib/errors';
import type { Insert, Patch, Row, TableName, UUID } from '../types';
import { FRIENDLY_TABLE_NAMES, UNIQUE_RULES } from './relations';
import type { DataBackend, ListQuery, StorageBackend, Where } from './types';

export const STORAGE_BUCKET = 'materiais';
const PAGE_SIZE = 1000;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyClient = SupabaseClient<any, any, any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFilterBuilder = any;

/** Traduz erros do PostgREST/PostgreSQL para mensagens claras em português. */
export function mapPostgrestError(error: PostgrestError | { message: string; code?: string }, table?: TableName): AppError {
  const code = error.code ?? '';
  const message = error.message ?? '';
  const friendly = table ? FRIENDLY_TABLE_NAMES[table] : 'registro';

  if (!code && (message.toLowerCase().includes('fetch') || message.toLowerCase().includes('network'))) {
    return new AppError('offline', 'Sem conexão com o servidor. Verifique sua internet e tente novamente.', error);
  }

  switch (code) {
    case '23505': {
      const rule = UNIQUE_RULES.find((r) => message.includes(r.constraint));
      return new AppError('conflict', rule?.message ?? `Já existe um registro igual (${friendly}).`, error);
    }
    case '23503': {
      if (message.startsWith('update or delete')) {
        return new AppError('integrity', 'Não é possível alterar: existem registros vinculados a este item.', error);
      }
      if (message.includes('exam_id_subject_id')) {
        return new AppError('integrity', 'A prova selecionada pertence a outra disciplina.', error);
      }
      if (message.includes('topic_id_exam_id')) {
        return new AppError('integrity', 'O conteúdo selecionado pertence a outra prova.', error);
      }
      return new AppError('integrity', 'O registro relacionado não existe ou não pertence a você.', error);
    }
    case '23514':
    case '23502':
    case '22001':
    case '22007':
    case '22008':
      return new AppError('validation', 'Os dados informados são inválidos. Revise os campos e tente novamente.', error);
    case '22P02':
      return new AppError('not_found', `Registro não encontrado (${friendly}).`, error);
    case '42501':
      return new AppError('permission', 'Você não tem permissão para realizar esta operação.', error);
    case 'PGRST116':
      return new AppError('not_found', `Registro não encontrado (${friendly}).`, error);
    case 'PGRST301':
    case 'PGRST302':
    case 'PGRST303':
      return new AppError('auth', 'Sua sessão expirou. Entre novamente.', error);
    case 'PGRST205':
    case '42P01':
      return new AppError(
        'config',
        'A tabela não foi encontrada no banco. Verifique se as migrações do Supabase foram aplicadas.',
        error,
      );
    default:
      return new AppError('unknown', `Erro no banco de dados: ${message}`, error);
  }
}

function applyWhere(builder: AnyFilterBuilder, where: Where | undefined): AnyFilterBuilder {
  if (!where) return builder;
  let b = builder;
  for (const [column, condition] of Object.entries(where)) {
    if (condition === null) b = b.is(column, null);
    else if (typeof condition !== 'object') b = b.eq(column, condition);
    else if ('in' in condition) b = b.in(column, condition.in);
    else if ('neq' in condition) b = b.neq(column, condition.neq);
    else if ('gte' in condition) b = b.gte(column, condition.gte);
    else if ('lte' in condition) b = b.lte(column, condition.lte);
    else if ('notNull' in condition) b = b.not(column, 'is', null);
  }
  return b;
}

class SupabaseStorageBackend implements StorageBackend {
  private readonly client: AnyClient;

  constructor(client: AnyClient) {
    this.client = client;
  }

  private bucket() {
    return this.client.storage.from(STORAGE_BUCKET);
  }

  private fail(error: { message: string }, fallback: string): never {
    if (isNetworkError(error) || error.message?.toLowerCase().includes('fetch')) {
      throw new AppError('offline', 'Sem conexão com o servidor de arquivos.', error);
    }
    throw new AppError('storage', `${fallback}: ${error.message}`, error);
  }

  async upload(path: string, file: Blob, options?: { contentType?: string; upsert?: boolean }): Promise<void> {
    const { error } = await this.bucket().upload(path, file, {
      contentType: options?.contentType ?? (file.type || undefined),
      upsert: options?.upsert ?? false,
    });
    if (error) this.fail(error, 'Não foi possível enviar o arquivo');
  }

  async download(path: string): Promise<Blob> {
    const { data, error } = await this.bucket().download(path);
    if (error || !data) this.fail(error ?? { message: 'arquivo vazio' }, 'Não foi possível baixar o arquivo');
    return data;
  }

  async getUrl(path: string, expiresInSeconds = 3600): Promise<string> {
    const { data, error } = await this.bucket().createSignedUrl(path, expiresInSeconds);
    if (error || !data) this.fail(error ?? { message: 'URL indisponível' }, 'Não foi possível abrir o arquivo');
    return data.signedUrl;
  }

  async remove(paths: string[]): Promise<void> {
    if (!paths.length) return;
    const { error } = await this.bucket().remove(paths);
    if (error) this.fail(error, 'Não foi possível remover o arquivo');
  }
}

/**
 * Adaptador Supabase (modo principal). O `user_id` é preenchido pelo banco
 * (`default auth.uid()`) e protegido por Row Level Security.
 */
export class SupabaseBackend implements DataBackend {
  readonly mode = 'supabase' as const;
  readonly storage: StorageBackend;
  readonly userId: UUID;
  private readonly client: AnyClient;

  constructor(client: AnyClient, userId: UUID) {
    this.client = client;
    this.userId = userId;
    this.storage = new SupabaseStorageBackend(client);
  }

  private async exec<R>(table: TableName, fn: () => PromiseLike<{ data: R; error: PostgrestError | null }>): Promise<R> {
    let result: { data: R; error: PostgrestError | null };
    try {
      result = await fn();
    } catch (error) {
      throw toAppError(error);
    }
    if (result.error) throw mapPostgrestError(result.error, table);
    return result.data;
  }

  async list<T extends TableName>(table: T, query?: ListQuery): Promise<Row<T>[]> {
    const build = (from: number, to: number) => {
      let builder = applyWhere(this.client.from(table).select('*'), query?.where);
      for (const { column, ascending = true } of query?.orderBy ?? []) {
        builder = builder.order(column, { ascending, nullsFirst: !ascending });
      }
      // Desempate estável para paginação.
      builder = builder.order('id', { ascending: true });
      return builder.range(from, to);
    };

    if (query?.limit !== undefined) {
      return this.exec(table, () => build(0, Math.max(0, query.limit! - 1))) as Promise<Row<T>[]>;
    }

    const rows: Row<T>[] = [];
    for (let from = 0; ; from += PAGE_SIZE) {
      const page = (await this.exec(table, () => build(from, from + PAGE_SIZE - 1))) as Row<T>[];
      rows.push(...page);
      if (page.length < PAGE_SIZE) break;
    }
    return rows;
  }

  async get<T extends TableName>(table: T, id: UUID): Promise<Row<T> | null> {
    const data = await this.exec(table, () => this.client.from(table).select('*').eq('id', id).maybeSingle());
    return (data as Row<T> | null) ?? null;
  }

  async count<T extends TableName>(table: T, where?: Where): Promise<number> {
    let result: { count: number | null; error: PostgrestError | null };
    try {
      result = await applyWhere(this.client.from(table).select('id', { count: 'exact', head: true }), where);
    } catch (error) {
      throw toAppError(error);
    }
    if (result.error) throw mapPostgrestError(result.error, table);
    return result.count ?? 0;
  }

  async insert<T extends TableName>(table: T, values: Insert<T>): Promise<Row<T>> {
    const data = await this.exec(table, () => this.client.from(table).insert(values).select('*').single());
    return data as Row<T>;
  }

  async insertMany<T extends TableName>(table: T, values: Insert<T>[]): Promise<Row<T>[]> {
    const rows: Row<T>[] = [];
    for (let i = 0; i < values.length; i += 500) {
      const chunk = values.slice(i, i + 500);
      const data = await this.exec(table, () => this.client.from(table).insert(chunk).select('*'));
      rows.push(...(data as Row<T>[]));
    }
    return rows;
  }

  async update<T extends TableName>(table: T, id: UUID, patch: Patch<T>): Promise<Row<T>> {
    const data = await this.exec(table, () =>
      this.client.from(table).update(patch as never).eq('id', id).select('*').maybeSingle(),
    );
    if (!data) throw new AppError('not_found', `Registro não encontrado (${FRIENDLY_TABLE_NAMES[table]}).`);
    return data as Row<T>;
  }

  async remove<T extends TableName>(table: T, id: UUID): Promise<void> {
    await this.exec(table, () => this.client.from(table).delete().eq('id', id));
  }
}
