import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button, Checkbox, IconButton, SearchField, Select, Switch, TextArea, TextField } from "../src";
import { axeViolations } from "./axe";

afterEach(cleanup);

describe("Button", () => {
  it("tem as variantes e responde ao clique", () => {
    const onClick = vi.fn();
    render(<Button variant="principal" icon="mais" onClick={onClick}>Criar</Button>);
    const button = screen.getByRole("button", { name: "Criar" });
    expect(button.className).toContain("ui-botao--principal");
    expect(button.getAttribute("type")).toBe("button");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("desabilitado não dispara", () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>Salvar</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("carregando: desabilita, marca aria-busy e anuncia", () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Publicar</Button>);
    const button = screen.getByRole("button", { name: /Publicar/ });
    expect(button).toHaveProperty("disabled", true);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.textContent).toContain("carregando");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("botão só com ícone exige nome acessível e passa no axe", async () => {
    const { container } = render(<IconButton icon="lixeira" label="Excluir" />);
    expect(screen.getByRole("button", { name: "Excluir" })).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("campos", () => {
  it("rótulo, ajuda e erro ficam associados ao campo", async () => {
    const { container } = render(<TextField label="Nome" help="Como aparece no painel" error="Informe o nome" required />);
    const input = screen.getByLabelText(/Nome/);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const described = (input.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
    expect(described.join(" ")).toContain("Informe o nome");
    expect(described.join(" ")).toContain("Como aparece no painel");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sem erro, o campo não é inválido", () => {
    render(<TextArea label="Descrição" />);
    expect(screen.getByLabelText("Descrição").getAttribute("aria-invalid")).toBeNull();
  });

  it("seleção, busca e caixa têm nome e valor", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <>
        <Select label="Canal" options={[{ value: "a", label: "Estável" }, { value: "b", label: "Beta" }]} onChange={onChange} />
        <SearchField label="Buscar" hideLabel />
        <Checkbox label="Lembrar" />
      </>,
    );
    fireEvent.change(screen.getByLabelText("Canal"), { target: { value: "b" } });
    expect(onChange).toHaveBeenCalled();
    expect(screen.getByRole("searchbox", { name: "Buscar" })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "Lembrar" })).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("alternador anuncia ligado e desligado", async () => {
    const onChange = vi.fn();
    const { container, rerender } = render(<Switch label="Movimento reduzido" checked={false} onChange={onChange} />);
    const control = screen.getByRole("switch", { name: "Movimento reduzido" });
    expect(control.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(control);
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(<Switch label="Movimento reduzido" checked onChange={onChange} />);
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
    await act(async () => expect(await axeViolations(container)).toEqual([]));
  });
});
