import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "./api";

/** Estado da ligação com o Assistant, conferido de verdade pela rota de saúde. */
export type ConnectionState = "conectando" | "conectado" | "reconectando" | "desconectado";
type Health = { status: "ok" | "degraded" | "failed"; service: string; version: string };
type Connection = { state: ConnectionState; health: Health | null; lastOk: Date | null; retry: () => void };

const Context = createContext<Connection>({ state: "conectando", health: null, lastOk: null, retry: () => {} });
export const POLL_MS = 5_000;
const ATTEMPTS_BEFORE_OFFLINE = 3;

export function ConnectionProvider({ children, pollMs = POLL_MS }: { children: ReactNode; pollMs?: number | undefined }) {
  const [state, setState] = useState<ConnectionState>("conectando");
  const [health, setHealth] = useState<Health | null>(null);
  const [lastOk, setLastOk] = useState<Date | null>(null);
  const failures = useRef(0);
  const everConnected = useRef(false);

  const check = useCallback(async () => {
    try {
      const result = await api.get<Health>("/health");
      failures.current = 0;
      everConnected.current = true;
      setHealth(result);
      setLastOk(new Date());
      setState("conectado");
    } catch {
      failures.current += 1;
      setState(failures.current >= ATTEMPTS_BEFORE_OFFLINE ? "desconectado" : everConnected.current ? "reconectando" : "conectando");
    }
  }, []);

  useEffect(() => {
    void check();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void check();
    }, pollMs);
    const onVisible = () => document.visibilityState === "visible" && void check();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [check, pollMs]);

  const retry = useCallback(() => {
    failures.current = 0;
    setState(everConnected.current ? "reconectando" : "conectando");
    void check();
  }, [check]);

  return <Context.Provider value={{ state, health, lastOk, retry }}>{children}</Context.Provider>;
}

export const useConnection = () => useContext(Context);
