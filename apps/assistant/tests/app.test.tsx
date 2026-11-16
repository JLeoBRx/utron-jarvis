import axe from "axe-core";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App, NAV } from "../src/App";
import { Composer } from "../src/pages/Conversations";
import { installFakeApi, json } from "./fake-api";

async function violations(node: Element) {
  const result = await axe.run(node, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

beforeEach(() => {
  window.location.hash = "";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("estrutura", () => {
  it("a navegação tem as dez áreas pedidas e o console", () => {
    const ids = NAV.flatMap((g) => g.items.map((i) => i.id));
    expect(ids).toEqual(["inicio", "conversas", "historico", "projetos", "memoria", "ferramentas", "ia", "monitoramento", "console", "configuracoes", "perfil"]);
  });

  it("o início mostra o estado real e avisa que não há respostas de IA", async () => {
    installFakeApi();
    const { container } = render(<App />);
    await screen.findByText("O SAFRA ainda não gera respostas");
    await screen.findByText("conectado");
    expect(within(screen.getByRole("region", { name: "Estado do SAFRA" })).getByRole("img", { name: "SAFRA — em repouso" })).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText("Olá").length).toBeGreaterThan(0));
    expect(await violations(container)).toEqual([]);
  });

  it("cada área abre pelo menu e marca a atual", async () => {
    installFakeApi();
    render(<App />);
    for (const item of NAV.flatMap((g) => g.items)) {
      act(() => {
        window.location.hash = item.href.slice(1);
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      });
      const link = screen.getByRole("link", { name: new RegExp(item.label) });
      expect(link.getAttribute("aria-current")).toBe("page");
      expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
    }
  });
});

describe("console", () => {
  it("mostra módulos, saúde e o que não existe como não implementado", async () => {
    installFakeApi();
    window.location.hash = "#/console";
    const { container } = render(<App />);
    const table = await screen.findByRole("table", { name: "Módulos do Assistant" });
    expect(within(table).getByText("Gateway de IA")).toBeTruthy();
    expect(within(table).getByText("planejado")).toBeTruthy();
    expect(within(table).getByText("implementado")).toBeTruthy();
    expect(await screen.findByText("Voz ainda não implementada")).toBeTruthy();
    expect(await screen.findByText("72.4")).toBeTruthy();
    expect(await violations(container)).toEqual([]);
  });
});

describe("conexão", () => {
  it("sem o Assistant, avisa, mostra o símbolo desconectado e desabilita as ações", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    window.location.hash = "#/conversas";
    render(<App pollMs={20} />);
    expect(await screen.findByText("Conectando ao Assistant…")).toBeTruthy();
    expect(await screen.findByText("Sem conexão com o Assistant", {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByLabelText("Mensagem")).toHaveProperty("disabled", true);
  });
});

describe("conversa", () => {
  it("envia, mostra a mensagem e diz que não há resposta (nada inventado)", async () => {
    const { calls } = installFakeApi();
    window.location.hash = "#/conversas/1";
    render(<App />);
    const box = await screen.findByLabelText("Mensagem");
    await waitFor(() => expect(box).toHaveProperty("disabled", false));
    fireEvent.change(box, { target: { value: "Resuma meu dia" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Resuma meu dia")).toBeTruthy();
    expect(calls.some((c) => c.method === "POST" && c.path === "/conversations/1/messages")).toBe(true);
    expect(screen.getAllByText(/Sem resposta: o gateway de IA ainda não foi implementado/).length).toBe(2);
    expect(screen.queryByText(/^SAFRA$/, { selector: ".mensagem__autor" })).toBeNull();
  });

  it("o envio em andamento mostra o indicador e pode ser cancelado", async () => {
    let aborted = false;
    const onSend = (_text: string, signal: AbortSignal) => new Promise<void>((_resolve, reject) => {
      signal.addEventListener("abort", () => { aborted = true; reject(Object.assign(new Error("cancelado"), { code: "cancelado" })); });
    });
    render(<Composer disabled={false} archived={false} onSend={onSend} ai={null} />);
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "texto longo" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Enviando…")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(aborted).toBe(true));
    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("texto longo");
  });

  it("a escolha de provedor fica desabilitada enquanto o gateway não existe", () => {
    render(<Composer disabled={false} archived={false} onSend={async () => {}} ai={{ gateway: { situacao: "nao_implementado", fase: 5 }, providers: [], selection_allowed: false }} />);
    expect(screen.getByLabelText("Provedor de IA")).toHaveProperty("disabled", true);
    expect(screen.getByText(/A escolha de provedor chega com o gateway de IA/)).toBeTruthy();
  });

  it("um erro do Assistant aparece junto do campo e o texto é mantido", async () => {
    render(<Composer disabled={false} archived={false} ai={null} onSend={async () => { throw new Error("A conversa está arquivada."); }} />);
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "oi" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/A conversa está arquivada/)).toBeTruthy();
    expect((screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("oi");
  });
});

describe("memória", () => {
  it("lixeira vazia e registro com confirmação passam no axe", async () => {
    installFakeApi((method, path) => (method === "POST" && path === "/memories" ? json(201, { id: 9 }) : undefined));
    window.location.hash = "#/memoria";
    const { container } = render(<App />);
    expect(await screen.findByText("Nada registrado ainda")).toBeTruthy();
    expect(await violations(container)).toEqual([]);
  });
});
