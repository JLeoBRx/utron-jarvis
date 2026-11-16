import { useCallback, useEffect, useRef, useState } from "react";

import { api, messageOf } from "./api";

export type Resource<T> = { data: T | null; error: string | null; loading: boolean; reload: () => Promise<void>; setData: (value: T) => void };

/** Lê uma rota da API, com estado de carregando e de erro, e recarrega quando o caminho muda. */
export function useResource<T>(path: string | null, refreshMs?: number): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const current = useRef(path);
  current.current = path;

  const reload = useCallback(async () => {
    if (path === null) return;
    setLoading(true);
    try {
      const result = await api.get<T>(path);
      if (current.current === path) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (current.current === path) setError(messageOf(err));
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setData(null);
    void reload();
    if (!refreshMs) return;
    const timer = window.setInterval(() => document.visibilityState === "visible" && void reload(), refreshMs);
    return () => window.clearInterval(timer);
  }, [reload, refreshMs]);

  return { data, error, loading, reload, setData };
}

/** Título da aba do navegador por área. */
export function useTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} — SAFRA`;
  }, [title]);
}
