import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, del, fieldProblems, get, post, setCsrfToken, upload } from "../src/api";

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn().mockImplementation(async () => new Response(body === undefined ? "" : JSON.stringify(body), { status, headers }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken("");
});

describe("cliente da API do painel", () => {
  it("envia o código anti-CSRF só nos pedidos que alteram", async () => {
    const fetchMock = respond(200, { ok: true });
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("codigo-da-sessao");
    await get("/pages", { status: "draft" });
    await post("/pages", { title: "x" });
    await del("/pages/1", { confirm_slug: "x" });
    const [getCall, postCall, delCall] = fetchMock.mock.calls;
    expect(getCall[0]).toBe("/admin/api/pages?status=draft");
    expect(getCall[1].headers["X-CSRF-Token"]).toBeUndefined();
    expect(postCall[1].headers["X-CSRF-Token"]).toBe("codigo-da-sessao");
    expect(postCall[1].headers["Content-Type"]).toBe("application/json");
    expect(postCall[1].credentials).toBe("same-origin");
    expect(JSON.parse(postCall[1].body)).toEqual({ title: "x" });
    expect(delCall[1].method).toBe("DELETE");
  });

  it("envia arquivos como bytes, com os metadados na consulta", async () => {
    const fetchMock = respond(201, { id: 1 });
    vi.stubGlobal("fetch", fetchMock);
    await upload("/media", new Blob(["abc"]), { filename: "a.png", alt_text: "texto" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/admin/api/media?filename=a.png&alt_text=texto");
    expect(init.headers["Content-Type"]).toBe("application/octet-stream");
    expect(init.body).toBeInstanceOf(Blob);
  });

  it("traduz o formato único de erro do servidor", async () => {
    vi.stubGlobal("fetch", respond(422, { error: { code: "validacao", message: "Os dados enviados são inválidos.", correlation_id: "c-1",
      details: { fields: [{ field: "slug", problem: "inválido" }] } } }));
    const error = await post("/pages", {}).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.code).toBe("validacao");
    expect(error.correlationId).toBe("c-1");
    expect(fieldProblems(error)).toEqual(["slug: inválido"]);
  });

  it("não quebra quando o servidor responde sem JSON", async () => {
    vi.stubGlobal("fetch", respond(502, undefined, { "X-SAFRA-Correlacao": "c-9" }));
    const error = await get("/dashboard").catch((e) => e);
    expect(error.status).toBe(502);
    expect(error.code).toBe("erro_http");
  });

  it("informa a falta de conexão sem detalhes técnicos", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await get("/dashboard").catch((e) => e);
    expect(error.code).toBe("sem_conexao");
    expect(error.message).not.toContain("Failed");
  });
});
