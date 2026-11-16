import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { env } from '@/config/env';

let client: SupabaseClient | null = null;

/** Cliente Supabase único da aplicação (ou `null` em modo local). */
export function getSupabase(): SupabaseClient | null {
  if (!env.isSupabaseConfigured || env.hasSecretKeyExposed) return null;
  if (!client) {
    client = createClient(env.supabaseUrl!, env.supabaseKey!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return client;
}
