import { useEffect, useState } from "react";

export type Route =
  | { name: "inicio" }
  | { name: "conversas"; id?: number }
  | { name: "historico" }
  | { name: "projetos"; id?: number }
  | { name: "memoria" }
  | { name: "ferramentas" }
  | { name: "ia" }
  | { name: "configuracoes" }
  | { name: "monitoramento" }
  | { name: "perfil" }
  | { name: "console" }
  | { name: "nao-encontrada"; path: string };

const SIMPLE = ["historico", "memoria", "ferramentas", "ia", "configuracoes", "monitoramento", "perfil", "console"] as const;

/** Rotas por hash (#/…): a interface é um único arquivo servido pelo Assistant, sem reescrita de endereço. */
export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  if (path === "/") return { name: "inicio" };
  const [, first = "", second] = path.split("/");
  const id = second !== undefined && /^\d+$/.test(second) ? Number(second) : undefined;
  if (first === "conversas" && (second === undefined || id !== undefined)) return { name: "conversas", id };
  if (first === "projetos" && (second === undefined || id !== undefined)) return { name: "projetos", id };
  if (second === undefined && (SIMPLE as readonly string[]).includes(first)) return { name: first as (typeof SIMPLE)[number] };
  return { name: "nao-encontrada", path };
}

export const href = (path: string) => `#${path}`;

export function navigate(path: string): void {
  window.location.hash = path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
