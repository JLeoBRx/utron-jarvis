import { useState, type FormEvent } from "react";

import { del, get, post, put } from "../api";
import { Empty, ErrorBox, Field, Loading, Notice, useAction, useLoad } from "../components/ui";
import { when } from "../format";
import type { Release } from "../types";

interface Listing { publication_enabled: boolean; block_reason: string; items: Release[] }
type Form = Pick<Release, "version" | "channel" | "notes" | "platform">;
const EMPTY: Form = { version: "", channel: "experimental", notes: "", platform: "windows" };
const CHANNEL: Record<Release["channel"], string> = { stable: "estável", beta: "beta", experimental: "experimental" };

export function ReleasesPage() {
  const { data, error, loading, reload } = useLoad(() => get<Listing>("/releases"));
  const [form, setForm] = useState<Form>(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);
  const action = useAction();
  const [message, setMessage] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    const saved = await action.run(() => (editing ? put(`/releases/${editing}`, form) : post("/releases", form)));
    if (saved) {
      setForm(EMPTY);
      setEditing(null);
      reload();
    }
  };
  const publish = async (release: Release) => {
    setMessage("");
    await action.run(() => post(`/releases/${release.id}/publish`));
    reload();
  };
  const remove = async (release: Release) => {
    if (window.confirm(`Remover a versão ${release.version}?`) && await action.run(() => del(`/releases/${release.id}`))) reload();
  };
  return (
    <>
      <header className="pagina__cabecalho"><h1>Downloads</h1><p>Cadastro de versões do SAFRA para a página pública de downloads.</p></header>
      {data && !data.publication_enabled && <Notice tone="atencao"><strong>Publicação bloqueada.</strong> {data.block_reason}</Notice>}
      {message && <Notice tone="sucesso">{message}</Notice>}
      <form className="cartao formulario-envio" onSubmit={submit} aria-label={editing ? "Editar versão" : "Cadastrar versão"}>
        <Field label="Número da versão" id="versao" hint="Ex.: 4.0.0 ou 4.0.0-beta.1"><input id="versao" required maxLength={40} value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></Field>
        <Field label="Canal" id="canal">
          <select id="canal" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value as Release["channel"] })}>
            <option value="experimental">Experimental</option><option value="beta">Beta</option><option value="stable">Estável</option>
          </select>
        </Field>
        <Field label="Plataforma" id="plataforma"><select id="plataforma" value={form.platform} disabled><option value="windows">Windows</option></select></Field>
        <Field label="Notas da versão" id="notas"><textarea id="notas" rows={3} maxLength={8000} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
        <div className="acoes">
          {editing && <button type="button" className="botao botao--discreto" onClick={() => { setEditing(null); setForm(EMPTY); }}>Cancelar</button>}
          <button className="botao botao--principal" type="submit" disabled={action.busy}>{editing ? "Salvar" : "Cadastrar"}</button>
        </div>
      </form>
      <p className="campo__ajuda">O envio de arquivos de instalação será liberado junto com a publicação, com conferência de integridade (SHA-256).</p>
      <ErrorBox error={action.error} />
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty>Nenhuma versão cadastrada.</Empty>}
      {data && data.items.length > 0 && (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead><tr><th scope="col">Versão</th><th scope="col">Canal</th><th scope="col">Situação</th><th scope="col">Atualizada</th><th scope="col"><span className="visualmente-oculto">Ações</span></th></tr></thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  <td>{r.version}</td><td>{CHANNEL[r.channel]}</td><td>{r.status === "published" ? "publicada" : "rascunho"}</td><td>{when(r.updated_at)}</td>
                  <td className="acoes">
                    <button type="button" className="botao botao--discreto" onClick={() => { setEditing(r.id); setForm({ version: r.version, channel: r.channel, notes: r.notes, platform: r.platform }); }}>Editar</button>
                    <button type="button" className="botao botao--discreto" onClick={() => void publish(r)}>Publicar</button>
                    <button type="button" className="botao botao--discreto" onClick={() => void remove(r)}>Remover</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
