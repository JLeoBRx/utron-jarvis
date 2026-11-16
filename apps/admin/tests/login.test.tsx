import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "../src/pages/LoginPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("tela de entrada", () => {
  it("mostra a mensagem do servidor quando a entrada é recusada", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "nao_autenticado",
      message: "E-mail ou senha incorretos.", correlation_id: "c-1" } }), { status: 401 })));
    const onSignedIn = vi.fn();
    render(<LoginPage onSignedIn={onSignedIn} />);
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "a@exemplo.test" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "qualquer coisa" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("E-mail ou senha incorretos."));
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("entrega a identidade e apaga a senha do formulário ao entrar", async () => {
    const identity = { user: { id: 1, email: "a@exemplo.test", name: "A", role: "editor", role_name: "Editor" }, permissions: [], csrf_token: "x" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(identity), { status: 200 })));
    const onSignedIn = vi.fn();
    render(<LoginPage onSignedIn={onSignedIn} />);
    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "a@exemplo.test" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "senha longa de teste" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(identity));
    expect((screen.getByLabelText("Senha") as HTMLInputElement).value).toBe("");
  });

  it("todos os campos têm rótulo", () => {
    render(<LoginPage onSignedIn={() => undefined} />);
    for (const input of document.querySelectorAll("input")) {
      expect(document.querySelector(`label[for="${input.id}"]`)).not.toBeNull();
    }
  });
});
