import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Banner, DataTable, EmptyState, ErrorState, MetricCard, SideNav, Spinner, StatusBadge, Tabs, ToastProvider, useToast, type Column } from "../src";
import { axeViolations } from "./axe";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

type Row = { id: number; nome: string; tamanho: number };
const columns: Column<Row>[] = [
  { key: "nome", header: "Nome", render: (r) => r.nome, sortValue: (r) => r.nome },
  { key: "tamanho", header: "Tamanho", render: (r) => `${r.tamanho} kB`, sortValue: (r) => r.tamanho, align: "fim" },
];
const rows: Row[] = [{ id: 1, nome: "banner", tamanho: 30 }, { id: 2, nome: "avatar", tamanho: 12 }];

describe("DataTable", () => {
  it("ordena pelas colunas e informa a ordem com aria-sort", async () => {
    const { container } = render(<DataTable caption="Arquivos" columns={columns} rows={rows} rowKey={(r) => r.id} />);
    const body = () => within(container.querySelector("tbody") as HTMLElement).getAllByRole("row").map((r) => r.textContent);
    expect(body()[0]).toContain("banner");
    fireEvent.click(screen.getByRole("button", { name: /Nome/ }));
    expect(screen.getByRole("columnheader", { name: /Nome/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(body()[0]).toContain("avatar");
    fireEvent.click(screen.getByRole("button", { name: /Tamanho/ }));
    fireEvent.click(screen.getByRole("button", { name: /Tamanho/ }));
    expect(screen.getByRole("columnheader", { name: /Tamanho/ }).getAttribute("aria-sort")).toBe("descending");
    expect(body()[0]).toContain("banner");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("mostra carregando, vazio e erro com nova tentativa", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<DataTable caption="Arquivos" columns={columns} rows={null} loading rowKey={(r) => r.id} />);
    expect(screen.getByRole("status", { name: /carregando/ })).toBeTruthy();
    rerender(<DataTable caption="Arquivos" columns={columns} rows={[]} rowKey={(r) => r.id} empty={{ title: "Nenhum arquivo enviado" }} />);
    expect(screen.getByText("Nenhum arquivo enviado")).toBeTruthy();
    rerender(<DataTable caption="Arquivos" columns={columns} rows={null} error="O servidor não respondeu." onRetry={onRetry} rowKey={(r) => r.id} />);
    expect(screen.getByRole("alert").textContent).toContain("O servidor não respondeu.");
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("Tabs", () => {
  it("troca de aba com as setas", async () => {
    const { container } = render(<Tabs label="Configurações" tabs={[
      { id: "geral", label: "Geral", content: <p>painel geral</p> },
      { id: "voz", label: "Voz", content: <p>painel de voz</p> },
    ]} />);
    const first = screen.getByRole("tab", { name: "Geral" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Voz" }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Voz" }));
    expect(screen.getByRole("tabpanel").textContent).toBe("painel de voz");
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("estados e indicadores", () => {
  it("carregando, vazio, erro, faixa e selo têm texto, não só cor", async () => {
    const { container } = render(
      <main>
        <Spinner label="Carregando conversas" />
        <EmptyState title="Nenhuma conversa" description="Escreva a primeira mensagem." />
        <ErrorState message="Sem conexão com o Assistant." />
        <Banner tone="atencao" title="Gateway de IA não implementado">As respostas chegam na Fase 5.</Banner>
        <StatusBadge tone="sucesso">no ar</StatusBadge>
        <MetricCard label="Memória do processo" value="72" unit="MB" />
      </main>,
    );
    expect(screen.getAllByRole("status").some((el) => el.textContent?.includes("Carregando conversas"))).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("Sem conexão");
    expect(screen.getByText("Gateway de IA não implementado")).toBeTruthy();
    expect(screen.getByText("no ar")).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("navegação marca a página atual e lê as pendências", async () => {
    const { container } = render(<SideNav label="Principal" current="memoria" groups={[{ items: [
      { id: "inicio", label: "Início", href: "#/", icon: "inicio" },
      { id: "memoria", label: "Memória", href: "#/memoria", icon: "memoria", badge: 3 },
    ] }]} />);
    const current = screen.getByRole("link", { name: /Memória/ });
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.textContent).toContain("3 pendentes");
    expect(screen.getByRole("link", { name: "Início" }).getAttribute("aria-current")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("avisos temporários", () => {
  function Emit() {
    const { notify } = useToast();
    return (
      <>
        <button type="button" onClick={() => notify("Página publicada")}>ok</button>
        <button type="button" onClick={() => notify("Falha ao salvar", "erro")}>erro</button>
      </>
    );
  }

  it("anunciam em regiões ao vivo, somem sozinhos e podem ser dispensados", () => {
    vi.useFakeTimers();
    render(<ToastProvider><Emit /></ToastProvider>);
    const polite = document.querySelector("[aria-live=polite]") as HTMLElement;
    const assertive = document.querySelector("[aria-live=assertive]") as HTMLElement;
    fireEvent.click(screen.getByRole("button", { name: "ok" }));
    fireEvent.click(screen.getByRole("button", { name: "erro" }));
    expect(polite.textContent).toContain("Página publicada");
    expect(assertive.textContent).toContain("Falha ao salvar");
    act(() => vi.advanceTimersByTime(4500));
    expect(polite.textContent).not.toContain("Página publicada");
    expect(assertive.textContent).toContain("Falha ao salvar");
    fireEvent.click(screen.getByRole("button", { name: "Dispensar aviso" }));
    expect(assertive.textContent).not.toContain("Falha ao salvar");
  });
});
