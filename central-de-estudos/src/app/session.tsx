import type { Session } from '@supabase/supabase-js';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { env } from '@/config/env';
import { LocalBackend } from '@/data/backend/local';
import { SupabaseBackend } from '@/data/backend/supabase';
import type { DataBackend } from '@/data/backend/types';
import { getSupabase } from '@/lib/supabase';
import { queryClient } from './queryClient';

export type SessionState =
  | { status: 'config_error'; reason: string }
  | { status: 'loading' }
  | { status: 'signed_out' }
  | { status: 'ready'; backend: DataBackend; email: string | null };

interface SessionContextValue {
  state: SessionState;
  /** O usuário chegou por um link de redefinição de senha. */
  passwordRecovery: boolean;
  clearPasswordRecovery: () => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

let localBackend: LocalBackend | null = null;
function getLocalBackend(): LocalBackend {
  localBackend ??= new LocalBackend();
  return localBackend;
}

function initialState(): SessionState {
  if (env.hasSecretKeyExposed) {
    return {
      status: 'config_error',
      reason:
        'A variável VITE_SUPABASE_PUBLISHABLE_KEY contém uma chave SECRETA (service_role). Ela nunca pode ir para o navegador. Troque pela chave pública (publishable/anon) e gere uma nova chave secreta no Supabase.',
    };
  }
  if (env.isPartiallyConfigured) {
    return {
      status: 'config_error',
      reason: 'Configuração do Supabase incompleta: informe VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY (ou nenhuma das duas para usar o modo local).',
    };
  }
  if (!env.isSupabaseConfigured) return { status: 'ready', backend: getLocalBackend(), email: null };
  return { status: 'loading' };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(initialState);
  const [passwordRecovery, setPasswordRecovery] = useState(false);

  useEffect(() => {
    const supabase = getSupabase();
    if (!supabase) return;

    const apply = (session: Session | null) => {
      setState((current) => {
        if (!session) return { status: 'signed_out' };
        // Mantém o mesmo backend enquanto o usuário não muda (evita refazer consultas).
        if (current.status === 'ready' && current.backend.userId === session.user.id) {
          return current.email === (session.user.email ?? null) ? current : { ...current, email: session.user.email ?? null };
        }
        return { status: 'ready', backend: new SupabaseBackend(supabase, session.user.id), email: session.user.email ?? null };
      });
    };

    supabase.auth
      .getSession()
      .then(({ data }) => apply(data.session))
      .catch(() => setState({ status: 'signed_out' }));

    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') setPasswordRecovery(true);
      apply(session);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  /**
   * Sair: primeiro desmonta a área de dados (nenhuma consulta nova é disparada
   * sem sessão), cancela as pendentes e limpa o cache; depois encerra a sessão.
   */
  const signOut = useCallback(async () => {
    setState({ status: 'signed_out' });
    await queryClient.cancelQueries();
    queryClient.clear();
    await getSupabase()?.auth.signOut();
  }, []);

  const value = useMemo(
    () => ({ state, passwordRecovery, clearPasswordRecovery: () => setPasswordRecovery(false), signOut }),
    [state, passwordRecovery, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession precisa estar dentro de <SessionProvider>.');
  return ctx;
}
