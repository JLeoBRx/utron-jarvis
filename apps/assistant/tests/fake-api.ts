import { vi } from "vitest";

/** API falsa só para os testes de componente: responde como o Assistant responderia (formatos reais). */
export const STATUS = {
  service: "assistant", version: "4.0.0.dev0", environment: "test", started_at: Date.now() / 1000 - 120,
  health: { status: "ok", checks: [{ name: "storage", ok: true, critical: true, detail: "", elapsed_ms: 0.4 }, { name: "schema", ok: true, critical: true, detail: "", elapsed_ms: 1.2 }] },
  database: { file: "safra.sqlite3", revision: "0002", head: "0002", size_bytes: 4096, counts: { conversations: 1, messages: 1, memories: 0, projects: 0 } },
  modules: [
    { name: "core", situacao: "implementado", fase: 2, resumo: "configuração" },
    { name: "ai_gateway", situacao: "planejado", fase: 5, resumo: "não há gateway" },
    { name: "memory", situacao: "parcial", fase: 3, resumo: "conversas e memórias" },
  ],
  ai: { situacao: "nao_implementado", fase: 5, mensagem: "O gateway de IA ainda não foi implementado." },
  voice: { situacao: "nao_implementado", fase: 6 },
};
const AI = { gateway: STATUS.ai, providers: [], selection_allowed: false };
const PREFS = Object.fromEntries(["nome", "tratamento", "movimento_reduzido", "densidade", "tamanho_texto"].map((k) => [k, { label: k, value: k === "movimento_reduzido" ? false : k === "densidade" ? "confortavel" : k === "tamanho_texto" ? "normal" : "", default: "", choices: k === "densidade" ? ["confortavel", "compacta"] : k === "tamanho_texto" ? ["normal", "grande"] : null, source: "padrao", updated_at: null }]));
const MESSAGE = { id: 1, role: "user", content: "Olá", provenance: {}, provider_id: null, created_at: "2026-11-16T10:00:00+00:00" };
const CONVERSATION = { id: 1, title: "Olá", project_id: null, started_at: MESSAGE.created_at, updated_at: MESSAGE.created_at, archived: false, message_count: 1, preview: "Olá" };

type Handler = (method: string, path: string, body: unknown, init?: RequestInit) => unknown | Promise<unknown>;

export function json(status: number, data: unknown): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

export function installFakeApi(overrides: Handler = () => undefined) {
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://127.0.0.1:47800");
    const method = init?.method ?? "GET";
    const path = url.pathname.replace("/api/v1", "") + url.search;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const custom = await overrides(method, path, body, init);
    if (custom instanceof Response) return custom;
    if (custom !== undefined) return json(200, custom);
    const route = url.pathname.replace("/api/v1", "");
    if (route === "/health") return json(200, { status: "ok", service: "assistant", version: "4.0.0.dev0" });
    if (route === "/system/status") return json(200, STATUS);
    if (route === "/system/resources") return json(200, { process: { rss_mb: 72.4, cpu_percent: 0.5, threads: 7, uptime_s: 120 }, system: { cpu_count: 4, cpu_percent: 3, memory_total_mb: 16000, memory_used_percent: 40 }, storage: { database_bytes: 4096, disk_free_mb: 20000 }, measured_at: Date.now() / 1000 });
    if (route === "/system/settings") return json(200, { environment: "test", data_dir: "/tmp/safra", api_host: "127.0.0.1", api_port: 47800, log_level: "INFO", log_to_file: false, migrate_on_start: true, editable: false, note: "só leitura" });
    if (route === "/activity") return json(200, []);
    if (route === "/ai/status") return json(200, AI);
    if (route === "/tools") return json(200, { executor: { situacao: "nao_implementado", fase: 7, mensagem: "Sem executor." }, tools: [], executions: [] });
    if (route === "/preferences") return json(200, PREFS);
    if (route === "/projects") return json(200, []);
    if (route === "/memories") return json(200, []);
    if (route === "/conversations" && method === "GET") return json(200, [CONVERSATION]);
    if (route === "/conversations/1") return json(200, { ...CONVERSATION, messages: [MESSAGE] });
    if (route === "/conversations/1/messages")
      return json(201, { message: { ...MESSAGE, id: 2, content: (body as { content: string }).content }, reply: { status: "indisponivel", code: "gateway_ia_nao_implementado", message: "sem gateway" } });
    return json(404, { error: { code: "nao_encontrado", message: "não existe" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
