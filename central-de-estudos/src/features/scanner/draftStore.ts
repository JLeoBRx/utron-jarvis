/**
 * Rascunho da digitalização, salvo no próprio aparelho (IndexedDB) a cada
 * alteração. Se a aba fechar, o celular recarregar a página ou a bateria
 * acabar, as fotos já tiradas são recuperadas ao abrir o scanner de novo.
 * É um estado TEMPORÁRIO: ao salvar o caderno, o rascunho é apagado.
 */
import Dexie, { type Table } from 'dexie';
import type { PageEdits } from '@/data/services/scans';

export interface DraftPageRecord {
  id: string;
  owner: string;
  position: number;
  original: ArrayBuffer;
  originalMime: string;
  originalName: string;
  source: 'camera' | 'galeria';
  edits: PageEdits;
  createdAt: string;
}

export interface DraftMeta {
  owner: string;
  subjectId: string;
  examId: string;
  topic: string;
  description: string;
  updatedAt: string;
}

class DraftDatabase extends Dexie {
  pages!: Table<DraftPageRecord, string>;
  meta!: Table<DraftMeta, string>;

  constructor() {
    super('central-de-estudos-rascunhos');
    this.version(1).stores({ pages: 'id, owner', meta: 'owner' });
  }
}

let database: DraftDatabase | null = null;
function db(): DraftDatabase {
  database ??= new DraftDatabase();
  return database;
}

export interface DraftPage {
  id: string;
  original: Blob;
  originalMime: string;
  originalName: string;
  source: 'camera' | 'galeria';
  edits: PageEdits;
}

export async function loadDraft(owner: string): Promise<{ pages: DraftPage[]; meta: DraftMeta | null }> {
  try {
    const [records, meta] = await Promise.all([db().pages.where('owner').equals(owner).toArray(), db().meta.get(owner)]);
    records.sort((a, b) => a.position - b.position);
    return {
      pages: records.map((r) => ({
        id: r.id,
        original: new Blob([r.original], { type: r.originalMime }),
        originalMime: r.originalMime,
        originalName: r.originalName,
        source: r.source,
        edits: r.edits,
      })),
      meta: meta ?? null,
    };
  } catch {
    return { pages: [], meta: null };
  }
}

export async function saveDraftPage(owner: string, page: DraftPage, position: number): Promise<void> {
  await db().pages.put({
    id: page.id,
    owner,
    position,
    original: await page.original.arrayBuffer(),
    originalMime: page.originalMime,
    originalName: page.originalName,
    source: page.source,
    edits: page.edits,
    createdAt: new Date().toISOString(),
  });
}

export async function updateDraftPage(id: string, changes: Partial<Pick<DraftPageRecord, 'edits' | 'position'>>): Promise<void> {
  await db().pages.update(id, changes);
}

export async function removeDraftPage(id: string): Promise<void> {
  await db().pages.delete(id);
}

export async function saveDraftOrder(ids: string[]): Promise<void> {
  await db().transaction('rw', db().pages, async () => {
    for (const [position, id] of ids.entries()) await db().pages.update(id, { position });
  });
}

export async function saveDraftMeta(meta: DraftMeta): Promise<void> {
  await db().meta.put(meta);
}

export async function clearDraft(owner: string): Promise<void> {
  await db().transaction('rw', db().pages, db().meta, async () => {
    await db().pages.where('owner').equals(owner).delete();
    await db().meta.delete(owner);
  });
}
