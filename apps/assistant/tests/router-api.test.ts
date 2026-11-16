import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../src/api";
import { parseRoute } from "../src/router";
import { installFakeApi, json } from "./fake-api";

afterEach(() => vi.unstubAllGlobals());

describe("rotas", () => {
  it("reconhece as onze áreas e os detalhes com número", () => {
    expect(parseRoute("")).toEqual({ name: "inicio" });
    expect(parseRoute("#/")).toEqual({ name: "inicio" });
    for (const name of ["historico", "memoria", "ferramentas", "ia", "configuracoes", "monitoramento", "perfil", "console"]) {
      expect(parseRoute(`#/${name}`)).toEqual({ name });
    }
    expect(parseRoute("#/conversas")).toEqual({ name: "conversas", id: undefined });
    expect(parseRoute("#/conversas/12")).toEqual({ name: "conversas", id: 12 });
    expect(parseRoute("#/projetos/3/")).toEqual({ name: "projetos", id: 3 });
  });

  it("endereços desconhecidos não caem em área nenhuma", () => {
    expect(parseRoute("#/conversas/abc").name).toBe("nao-encontrada");
    expect(parseRoute("#/admin").name).toBe("nao-encontrada");
    expect(parseRoute("#/memoria/1").name).toBe("nao-encontrada");
  });
});

describe("cliente da API", () => {
  it("envia JSON e lê o formato único de erro do SAFRA", async () => {
    const { calls } = installFakeApi((method, path) =>
      method === "POST" && path === "/projects" ? json(409, { error: { code: "conflito", message: "Já existe um projeto com esse nome." } }) : undefined);
    await expect(api.post("/projects", { name: "TCC" })).rejects.toMatchObject({ status: 409, code: "conflito", message: "Já existe um projeto com esse nome." });
    expect(calls[0]).toEqual({ method: "POST", path: "/projects", body: { name: "TCC" } });
  });

  it("diferencia falta de conexão de cancelamento", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(api.get("/health")).rejects.toMatchObject({ code: "sem_conexao" });
    vi.stubGlobal("fetch", vi.fn((_input: unknown, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("abortado", "AbortError")));
    })));
    const controller = new AbortController();
    const pending = api.post("/conversations/1/messages", { content: "oi" }, controller.signal);
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("cancelado");
  });
});
