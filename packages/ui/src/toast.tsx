import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { IconButton } from "./Button";
import { Icon, type IconName } from "./Icon";

export type ToastTone = "sucesso" | "erro" | "informacao" | "atencao";
type Toast = { id: number; tone: ToastTone; message: string };

type ToastApi = { notify: (message: string, tone?: ToastTone) => void };

const ToastContext = createContext<ToastApi | null>(null);
const ICON: Record<ToastTone, IconName> = { sucesso: "sucesso", erro: "erro", informacao: "informacao", atencao: "alerta" };
const DURATION: Record<ToastTone, number> = { sucesso: 4000, informacao: 5000, atencao: 7000, erro: 9000 };

/**
 * Avisos temporários. As regiões ao vivo ficam montadas desde o início (leitores de tela só anunciam mudanças em
 * regiões que já existem): sucesso e informação são "polite"; erro e atenção são "assertive".
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);
  const notify = useCallback((message: string, tone: ToastTone = "sucesso") => {
    const id = next.current++;
    setToasts((list) => [...list.slice(-3), { id, tone, message }]);
  }, []);
  const api = useMemo(() => ({ notify }), [notify]);
  const polite = toasts.filter((t) => t.tone === "sucesso" || t.tone === "informacao");
  const urgent = toasts.filter((t) => t.tone === "erro" || t.tone === "atencao");
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="ui-avisos">
        <div aria-live="polite" className="ui-avisos__grupo">
          {polite.map((t) => (
            <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
          ))}
        </div>
        <div aria-live="assertive" className="ui-avisos__grupo">
          {urgent.map((t) => (
            <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), DURATION[toast.tone]);
    return () => window.clearTimeout(timer);
  }, [paused, toast, onDismiss]);
  return (
    <div
      className={`ui-aviso ui-aviso--${toast.tone}`}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <Icon name={ICON[toast.tone]} size={20} />
      <p className="ui-aviso__texto">{toast.message}</p>
      <IconButton icon="fechar" label="Dispensar aviso" size="pequeno" onClick={() => onDismiss(toast.id)} />
    </div>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast precisa de <ToastProvider> acima na árvore");
  return api;
}
