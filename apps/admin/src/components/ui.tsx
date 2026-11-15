// Componentes básicos do painel. Todos os estados (carregando, vazio, erro) são explícitos.
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError, fieldProblems } from "../api";

export function Symbol({ size = 32 }: { size?: number }) {
  return (
    <svg className="simbolo" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect className="simbolo__fundo" x="5" y="7" width="54" height="54" rx="14" />
      <rect className="simbolo__placa" x="3" y="3" width="54" height="54" rx="14" />
      <g fill="none" strokeLinecap="round" strokeWidth="3.4">
        <path className="sulco" d="M13 17 C 23 11, 37 23, 47 16" />
        <path className="sulco sulco--2" d="M13 25 C 23 19, 37 31, 47 24" />
        <path className="sulco sulco--3" d="M13 33 C 23 27, 37 39, 47 32" />
        <path className="sulco sulco--4" d="M13 41 C 23 35, 37 47, 47 40" />
      </g>
    </svg>
  );
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return <p className="estado estado--carregando" role="status">{label}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="estado estado--vazio">{children}</p>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "Ocorreu um erro.";
  const problems = fieldProblems(error);
  const reference = error instanceof ApiError && error.correlationId ? error.correlationId : "";
  return (
    <div className="alerta alerta--erro" role="alert">
      <p>{message}</p>
      {problems.length > 0 && <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      {reference && <p className="alerta__ref">Referência: {reference}</p>}
      {onRetry && <button type="button" className="botao botao--secundario" onClick={onRetry}>Tentar de novo</button>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "sucesso" | "atencao"; children: ReactNode }) {
  return <div className={`alerta alerta--${tone}`} role="status">{children}</div>;
}

export function Badge({ status }: { status: string }) {
  const label: Record<string, string> = { draft: "rascunho", published: "publicado" };
  return <span className={`selo selo--${status}`}>{label[status] ?? status}</span>;
}

export function Field({ label, hint, children, id }: { label: string; hint?: string; children: ReactNode; id: string }) {
  return (
    <div className="campo">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <p className="campo__ajuda" id={`${id}-ajuda`}>{hint}</p>}
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>("input, button, textarea, select")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div className="modal" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal__caixa" role="dialog" aria-modal="true" aria-labelledby="modal-titulo" ref={box}>
        <h2 id="modal-titulo">{title}</h2>
        {children}
      </div>
    </div>
  );
}

/** Carrega dados de uma função assíncrona, com estados explícitos e recarga. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    load().then((value) => alive && setData(value)).catch((e) => alive && setError(e)).finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, setData, error, loading, reload: () => setTick((n) => n + 1) };
}

/** Executa uma ação, guardando "em andamento" e o erro para mostrar. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async <T,>(work: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await work();
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}
