import { useState, type FormEvent } from "react";

import { get, patch, post } from "../api";
import { ErrorBox, Field, Loading, Modal, useAction, useLoad } from "../components/ui";
import { when } from "../format";
import { useSession } from "../session";
import type { AdminUser, RoleInfo } from "../types";

interface Listing { roles: RoleInfo[]; items: AdminUser[] }

export function UsersPage() {
  const { identity } = useSession();
  const { data, error, loading, reload } = useLoad(() => get<Listing>("/users"));
  const [form, setForm] = useState({ email: "", name: "", role: "editor" });
  const [token, setToken] = useState<{ name: string; value: string } | null>(null);
  const action = useAction();
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const result = await action.run(() => post<{ user: AdminUser; recovery_token: string }>("/users", form));
    if (result) {
      setToken({ name: result.user.name, value: result.recovery_token });
      setForm({ email: "", name: "", role: "editor" });
      reload();
    }
  };
  const change = async (user: AdminUser, body: Partial<{ role: string; is_active: boolean }>) => {
    if (await action.run(() => patch(`/users/${user.id}`, body))) reload();
  };
  const recovery = async (user: AdminUser) => {
    const result = await action.run(() => post<{ recovery_token: string }>(`/users/${user.id}/recovery-token`));
    if (result) setToken({ name: user.name, value: result.recovery_token });
  };
  return (
    <>
      <header className="pagina__cabecalho"><h1>Usuários</h1><p>Contas novas nascem sem senha: o dono define a própria senha com um código de uso único.</p></header>
      <form className="cartao formulario-envio" onSubmit={create} aria-label="Nova conta">
        <Field label="Nome" id="u-nome"><input id="u-nome" required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="E-mail" id="u-email"><input id="u-email" type="email" required maxLength={254} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Papel" id="u-papel">
          <select id="u-papel" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {(data?.roles ?? []).map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}
          </select>
        </Field>
        <button className="botao botao--principal" type="submit" disabled={action.busy}>Criar conta</button>
      </form>
      <ErrorBox error={action.error} />
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead><tr><th scope="col">Nome</th><th scope="col">E-mail</th><th scope="col">Papel</th><th scope="col">Situação</th><th scope="col">Última entrada</th><th scope="col"><span className="visualmente-oculto">Ações</span></th></tr></thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}{u.id === identity.user.id && " (você)"}</td>
                  <td>{u.email}</td>
                  <td>
                    <select aria-label={`Papel de ${u.name}`} value={u.role} onChange={(e) => void change(u, { role: e.target.value })}>
                      {data.roles.map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}
                    </select>
                  </td>
                  <td>{!u.is_active ? "desativada" : u.locked ? "bloqueada por tentativas" : u.has_password ? "ativa" : "aguardando senha"}</td>
                  <td>{when(u.last_login_at)}</td>
                  <td className="acoes">
                    <button type="button" className="botao botao--discreto" onClick={() => void change(u, { is_active: !u.is_active })}>{u.is_active ? "Desativar" : "Reativar"}</button>
                    <button type="button" className="botao botao--discreto" onClick={() => void recovery(u)}>Código de recuperação</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && (
        <details className="cartao">
          <summary>O que cada papel pode fazer</summary>
          <ul>{data.roles.map((r) => <li key={r.key}><strong>{r.name}</strong>: {r.permissions.join(", ")}</li>)}</ul>
        </details>
      )}
      {token && (
        <Modal title="Código de recuperação" onClose={() => setToken(null)}>
          <p>Entregue este código a <strong>{token.name}</strong> por um canal seguro. Ele vale uma única vez, por tempo limitado, e <strong>não será mostrado de novo</strong>.</p>
          <p><code className="codigo">{token.value}</code></p>
          <p className="campo__ajuda">A pessoa define a senha em <code>/admin/#/recuperar</code>.</p>
          <div className="modal__acoes"><button type="button" className="botao botao--principal" onClick={() => setToken(null)}>Já copiei</button></div>
        </Modal>
      )}
    </>
  );
}
