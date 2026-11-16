/** Cliente da API local do Assistant (mesma origem). Erros chegam no formato único do SAFRA. */

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

const TIMEOUT_MS = 15_000;

export async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: combined,
      credentials: "same-origin",
    });
  } catch (error) {
    if (signal?.aborted) throw new ApiError(0, "cancelado", "Pedido cancelado.");
    if (timeout.aborted) throw new ApiError(0, "tempo_esgotado", "O Assistant demorou demais para responder.");
    throw new ApiError(0, "sem_conexao", "Sem conexão com o Assistant neste computador.", error);
  }
  const text = await response.text();
  const data = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    throw new ApiError(response.status, error?.code ?? "erro_http", error?.message ?? `Erro ${response.status}.`, error?.details);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body: unknown = {}, signal?: AbortSignal) => request<T>("POST", path, body, signal),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Algo deu errado.";
}
