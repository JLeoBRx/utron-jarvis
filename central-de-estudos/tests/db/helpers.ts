import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { SupabaseBackend } from '@/data/backend/supabase';
import { newId } from '@/lib/ids';
// @ts-expect-error — módulo JS sem tipos (ambiente de teste)
import { ANON_KEY } from '../supabase-local/keys.mjs';

export const SUPABASE_URL = process.env.SUPABASE_TEST_URL ?? 'http://127.0.0.1:54321';

export async function stackAvailable(): Promise<boolean> {
  try {
    return (await fetch(`${SUPABASE_URL}/auth/v1/health`)).ok;
  } catch {
    return false;
  }
}

export function newClient(): SupabaseClient {
  return createClient(SUPABASE_URL, ANON_KEY as string, { auth: { persistSession: false, autoRefreshToken: false } });
}

export async function signUp(): Promise<{ client: SupabaseClient; db: SupabaseBackend; userId: string }> {
  const client = newClient();
  const email = `teste-${newId().slice(0, 8)}@central.local`;
  const { data, error } = await client.auth.signUp({ email, password: 'senha-de-teste-123' });
  if (error || !data.user || !data.session) throw error ?? new Error('cadastro sem sessão');
  return { client, db: new SupabaseBackend(client, data.user.id), userId: data.user.id };
}
