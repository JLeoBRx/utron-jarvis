/**
 * Configuração do frontend. Apenas variáveis PÚBLICAS (prefixo VITE_) chegam
 * aqui — elas são embutidas no JavaScript entregue ao navegador.
 */

function read(name: string): string | null {
  const value = (import.meta.env as Record<string, string | undefined>)[name];
  return value && value.trim() ? value.trim() : null;
}

/** Detecta se alguém colocou por engano uma chave SECRETA no frontend. */
export function looksLikeSecretKey(key: string): boolean {
  if (key.startsWith('sb_secret_')) return true;
  const parts = key.split('.');
  if (parts.length === 3) {
    try {
      const payload = JSON.parse(atob(parts[1]!.replace(/-/g, '+').replace(/_/g, '/'))) as { role?: string };
      return payload.role === 'service_role';
    } catch {
      return false;
    }
  }
  return false;
}

const supabaseUrl = read('VITE_SUPABASE_URL');
const supabaseKey = read('VITE_SUPABASE_PUBLISHABLE_KEY') ?? read('VITE_SUPABASE_ANON_KEY');

export const env = {
  supabaseUrl,
  supabaseKey,
  isSupabaseConfigured: Boolean(supabaseUrl && supabaseKey),
  /** Chave secreta exposta: o app se recusa a iniciar o modo nuvem. */
  hasSecretKeyExposed: Boolean(supabaseKey && looksLikeSecretKey(supabaseKey)),
  /** Configuração parcial (só uma das duas variáveis). */
  isPartiallyConfigured: Boolean(supabaseUrl) !== Boolean(supabaseKey),
} as const;
