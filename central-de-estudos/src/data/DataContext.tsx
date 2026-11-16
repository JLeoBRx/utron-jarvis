import { createContext, useContext } from 'react';
import type { DataBackend } from './backend/types';

export const DataContext = createContext<DataBackend | null>(null);

/** Backend de dados ativo (Supabase ou local). */
export function useBackend(): DataBackend {
  const db = useContext(DataContext);
  if (!db) throw new Error('useBackend precisa estar dentro de <DataContext.Provider>.');
  return db;
}
