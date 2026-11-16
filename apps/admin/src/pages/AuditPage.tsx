import { useState } from "react";

import { get } from "../api";
import { Empty, ErrorBox, Loading, useAction, useLoad } from "../components/ui";
import { action as describe, when } from "../format";
import type { AuditEntry } from "../types";

export function AuditPage() {
  const first = useLoad(() => get<AuditEntry[]>("/audit", { limit: "50" }));
  const [more, setMore] = useState<AuditEntry[]>([]);
  const [ended, setEnded] = useState(false);
  const loader = useAction();
  const entries = [...(first.data ?? []), ...more];
  const next = async () => {
    const last = entries[entries.length - 1];
    if (!last) return;
    const page = await loader.run(() => get<AuditEntry[]>("/audit", { limit: "50", before_id: String(last.id) }));
    if (page) {
      setMore((m) => [...m, ...page]);
      if (page.length < 50) setEnded(true);
    }
  };
  return (
    <>
      <header className="pagina__cabecalho"><h1>Auditoria</h1><p>Ações administrativas e tentativas de acesso. Senhas, códigos e conteúdo não são registrados.</p></header>
      {first.loading && <Loading />}
      <ErrorBox error={first.error ?? loader.error} onRetry={first.reload} />
      {first.data && entries.length === 0 && <Empty>Nenhum registro.</Empty>}
      {entries.length > 0 && (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead><tr><th scope="col">Quando</th><th scope="col">Quem</th><th scope="col">O quê</th><th scope="col">Alvo</th></tr></thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}><td>{when(e.at)}</td><td>{e.actor || "—"}</td><td>{describe(e.action)}</td><td>{e.target_type ? `${e.target_type} ${e.target_id}` : ""}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {entries.length >= 50 && !ended && <button type="button" className="botao botao--secundario" disabled={loader.busy} onClick={() => void next()}>Mais antigos</button>}
    </>
  );
}
