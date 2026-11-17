import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

/**
 * Filtros guardados na URL (o botão "voltar" preserva a seleção).
 * As alterações partem da URL ATUAL do navegador — e não dos parâmetros do
 * último render — para que mudanças rápidas seguidas não se sobrescrevam.
 */
export function useUrlFilters() {
  const [params, setParams] = useSearchParams();
  const update = useCallback(
    (changes: Record<string, string>) => {
      const next = new URLSearchParams(window.location.search);
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      setParams(next, { replace: true });
    },
    [setParams],
  );
  const clear = useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams]);
  return { params, update, clear };
}
