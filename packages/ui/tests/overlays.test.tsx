import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button, ConfirmDialog, Menu, Modal } from "../src";
import { axeViolations } from "./axe";

afterEach(cleanup);

function ModalHarness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Abrir</Button>
      <Modal open={open} title="Nova página" description="Preencha o título." onClose={() => { onClose?.(); setOpen(false); }}
        actions={<Button variant="principal">Criar</Button>}>
        <input aria-label="Título" />
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("abre com papel de diálogo, prende o foco, fecha com Esc e devolve o foco", async () => {
    const onClose = vi.fn();
    render(<ModalHarness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Abrir" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Nova página" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    const buttons = dialog.querySelectorAll("button");
    const last = buttons[buttons.length - 1] as HTMLElement;
    last.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(buttons[0]);
    expect(await axeViolations(document.body)).toEqual([]);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("confirmação destrutiva começa com o foco em Cancelar", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="Excluir página?" message="A página sai do site." confirmLabel="Excluir" variant="perigo" onConfirm={onConfirm} onCancel={() => {}} />);
    expect(document.activeElement?.textContent).toBe("Cancelar");
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

describe("Menu", () => {
  it("abre, navega com as setas, fecha com Esc e executa a ação escolhida", async () => {
    const onEdit = vi.fn();
    const { container } = render(
      <Menu label="Ações da página" items={[
        { id: "editar", label: "Editar", icon: "editar", onSelect: onEdit },
        { id: "excluir", label: "Excluir", icon: "lixeira", danger: true, onSelect: () => {} },
      ]} />,
    );
    const trigger = screen.getByRole("button", { name: "Ações da página" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const items = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[0]);
    expect(await axeViolations(container)).toEqual([]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Editar" }));
    expect(onEdit).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
