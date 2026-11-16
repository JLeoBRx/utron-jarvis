import { LocalBackend, LocalDatabase } from '@/data/backend/local';
import { newId } from '@/lib/ids';

/** Banco local isolado (IndexedDB em memória) para cada teste. */
export function createTestBackend(): LocalBackend {
  return new LocalBackend(new LocalDatabase(`test-${newId()}`));
}
