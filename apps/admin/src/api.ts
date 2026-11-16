// Cliente da API do painel. A segurança é do servidor: aqui só se envia o que ele exige (cookie de sessão,
// código anti-CSRF nos pedidos que alteram) e se traduz o formato único de erro.

const BASE = "/admin/api";
const SAFE = new Set(["GET", "HEAD"]);
let csrfToken = "";

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly correlationId: string;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}, correlationId = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
  }
}

export function fieldProblems(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];
  const fields = error.details["fields"];
  if (!Array.isArray(fields)) return [];
  return fields.map((f: { field?: string; problem?: string }) => `${f.field ?? ""}: ${f.problem ?? ""}`);
}

type Body = unknown;

export async function api<T>(method: string, path: string, body?: Body, init: { raw?: Blob; query?: Record<string, string> } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (!SAFE.has(method)) headers["X-CSRF-Token"] = csrfToken;
  let payload: BodyInit | undefined;
  if (init.raw) {
    headers["Content-Type"] = "application/octet-stream";
    payload = init.raw;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const query = init.query ? "?" + new URLSearchParams(init.query).toString() : "";
  let response: Response;
  try {
    response = await fetch(BASE + path + query, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "sem_conexao", "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.");
  }
  const text = await response.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown>; correlation_id?: string } })?.error;
    throw new ApiError(response.status, error?.code ?? "erro_http", error?.message ?? `O servidor respondeu ${response.status}.`,
      error?.details ?? {}, error?.correlation_id ?? response.headers.get("X-SAFRA-Correlacao") ?? "");
  }
  return data as T;
}

export const get = <T>(path: string, query?: Record<string, string>) => api<T>("GET", path, undefined, { query });
export const post = <T>(path: string, body?: Body) => api<T>("POST", path, body ?? {});
export const put = <T>(path: string, body: Body) => api<T>("PUT", path, body);
export const patch = <T>(path: string, body: Body) => api<T>("PATCH", path, body);
export const del = <T>(path: string, body?: Body) => api<T>("DELETE", path, body);
export const upload = <T>(path: string, file: Blob, query: Record<string, string>) => api<T>("POST", path, undefined, { raw: file, query });
