import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "./api";
import { useConnection } from "./connection";
import type { Preference, Preferences } from "./types";

type Context = { prefs: Preferences | null; save: (key: keyof Preferences, value: string | boolean) => Promise<Preference> };
const PreferencesContext = createContext<Context>({ prefs: null, save: async () => Promise.reject(new Error("sem provedor")) });

/** Preferências gravadas no banco do Assistant, aplicadas à interface (movimento, densidade, tamanho do texto). */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const { state } = useConnection();
  const [prefs, setPrefs] = useState<Preferences | null>(null);

  useEffect(() => {
    if (state !== "conectado" || prefs) return;
    api.get<Preferences>("/preferences").then(setPrefs, () => {});
  }, [state, prefs]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("movimento-reduzido", prefs?.movimento_reduzido.value === true);
    root.classList.toggle("densidade-compacta", prefs?.densidade.value === "compacta");
    root.classList.toggle("texto-grande", prefs?.tamanho_texto.value === "grande");
  }, [prefs]);

  const save = useCallback(async (key: keyof Preferences, value: string | boolean) => {
    const saved = await api.put<Preference>(`/preferences/${key}`, { value });
    setPrefs((current) => (current ? { ...current, [key]: saved } : current));
    return saved;
  }, []);

  return <PreferencesContext.Provider value={{ prefs, save }}>{children}</PreferencesContext.Provider>;
}

export const usePreferences = () => useContext(PreferencesContext);

export function useReducedMotion(): boolean {
  const { prefs } = usePreferences();
  const [system, setSystem] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystem(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return system || prefs?.movimento_reduzido.value === true;
}
