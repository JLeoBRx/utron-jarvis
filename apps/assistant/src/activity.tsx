import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { SymbolState } from "@safra/ui";

import { useConnection } from "./connection";

/** O que a interface está fazendo agora com o Assistant (só estados reais: um pedido em andamento). */
type Busy = { busy: boolean; setBusy: (value: boolean) => void };
const BusyContext = createContext<Busy>({ busy: false, setBusy: () => {} });

export function BusyProvider({ children }: { children: ReactNode }) {
  const [busy, setBusy] = useState(false);
  const value = useMemo(() => ({ busy, setBusy }), [busy]);
  return <BusyContext.Provider value={value}>{children}</BusyContext.Provider>;
}

export const useBusy = () => useContext(BusyContext);

/**
 * Estado do símbolo a partir de fatos: a conexão, a saúde informada pelo Assistant e um pedido em andamento.
 * "Ouvindo" e "respondendo" dependem da voz e do gateway de IA, que ainda não existem — por isso nunca aparecem aqui.
 */
export function useSymbolState(): SymbolState {
  const { state, health } = useConnection();
  const { busy } = useBusy();
  if (state === "conectando") return "inicializando";
  if (state === "reconectando" || state === "desconectado") return "desconectado";
  if (health && health.status !== "ok") return "erro";
  if (busy) return "processando";
  return "inativo";
}
