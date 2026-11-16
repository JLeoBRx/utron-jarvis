import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SafraSymbol, SYMBOL_STATE_LABEL, type SymbolState } from "../src";
import { axeViolations } from "./axe";

afterEach(cleanup);

const STATES = Object.keys(SYMBOL_STATE_LABEL) as SymbolState[];

describe("símbolo do SAFRA", () => {
  it("tem os sete estados pedidos, cada um com rótulo para leitores de tela", async () => {
    expect(STATES).toEqual(["inativo", "inicializando", "ouvindo", "processando", "respondendo", "erro", "desconectado"]);
    for (const state of STATES) {
      const { container, unmount } = render(<SafraSymbol state={state} showLabel />);
      expect(screen.getByRole("img", { name: `SAFRA — ${SYMBOL_STATE_LABEL[state]}` })).toBeTruthy();
      expect(container.firstElementChild?.className).toContain(`ui-simbolo--${state}`);
      expect(screen.getByText(SYMBOL_STATE_LABEL[state])).toBeTruthy();
      expect(await axeViolations(container)).toEqual([]);
      unmount();
    }
  });

  it("é só SVG: sem canvas, sem WebGL, sem rosto ou figura", () => {
    const { container } = render(<SafraSymbol state="processando" />);
    expect(container.querySelector("canvas")).toBeNull();
    expect(container.querySelectorAll("svg path.ui-simbolo__sulco")).toHaveLength(4);
    expect(container.querySelectorAll("circle, ellipse")).toHaveLength(0);
  });

  it("em tamanho de ícone usa a versão de três sulcos", () => {
    const { container } = render(<SafraSymbol size={32} />);
    expect(container.querySelectorAll("path.ui-simbolo__sulco")).toHaveLength(3);
    expect(container.firstElementChild?.className).toContain("ui-simbolo--compacto");
  });

  it("ao iniciar, mostra os sulcos na proporção do progresso real", () => {
    const { container } = render(<SafraSymbol state="inicializando" progress={0.5} />);
    const hidden = container.querySelectorAll("path[data-oculto]");
    expect(hidden).toHaveLength(2);
    expect(container.firstElementChild?.className).toContain("ui-simbolo--com-progresso");
  });

  it("ao responder, recebe o nível real da voz quando existe", () => {
    const { container } = render(<SafraSymbol state="respondendo" level={0.4} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.getPropertyValue("--nivel")).toBe("0.40");
  });

  it("erro e desconexão trazem ícone além da cor; movimento reduzido para tudo", () => {
    const { container, rerender } = render(<SafraSymbol state="erro" />);
    expect(container.querySelector(".ui-simbolo__marca svg")).toBeTruthy();
    rerender(<SafraSymbol state="desconectado" reducedMotion />);
    expect(container.querySelector(".ui-simbolo__marca svg")).toBeTruthy();
    expect(container.firstElementChild?.className).toContain("ui-simbolo--parado");
  });
});
