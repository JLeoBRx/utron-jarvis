import { useState } from "react";

import { get } from "../api";
import { Badge, Empty, ErrorBox, Loading, useLoad } from "../components/ui";
import { when } from "../format";
import { href } from "../router";
import { useSession } from "../session";
import type { ContentKind, ContentSummary } from "../types";

export const KIND_LABEL: Record<ContentKind, { plural: string; singular: string; novo: string }> = {
  pages: { plural: "Páginas", singular: "página", novo: "Nova página" },
  news: { plural: "Notícias", singular: "notícia", novo: "Nova notícia" },
};

export function ContentList({ kind }: { kind: ContentKind }) {
  const { can } = useSession();
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const { data, error, loading, reload } = useLoad(() => get<ContentSummary[]>(`/${kind}`, { status, q: query }), [kind, status, query]);
  const label = KIND_LABEL[kind];
  return (
    <>
      <header className="pagina__cabecalho pagina__cabecalho--acoes">
        <h1>{label.plural}</h1>
        {can("content.edit") && <a className="botao botao--principal" href={href(`${kind}/novo`)}>{label.novo}</a>}
      </header>
      <div className="filtros" role="search">
        <label htmlFor="filtro-status">Situação</label>
        <select id="filtro-status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Todas</option><option value="published">Publicadas</option><option value="draft">Rascunhos</option>
        </select>
        <label htmlFor="filtro-busca">Buscar no título</label>
        <input id="filtro-busca" type="search" value={query} maxLength={80} onChange={(e) => setQuery(e.target.value)} />
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.length === 0 && <Empty>Nenhuma {label.singular} encontrada.</Empty>}
      {data && data.length > 0 && (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead><tr><th scope="col">Título</th><th scope="col">Endereço</th><th scope="col">Situação</th><th scope="col">Atualizada</th></tr></thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.id}>
                  <td><a href={href(`${kind}/${item.id}`)}>{item.title}</a></td>
                  <td><code>{item.public_path ?? (kind === "pages" ? `/${item.slug}` : `/atualizacoes/${item.slug}`)}</code></td>
                  <td><Badge status={item.status} />{item.has_unpublished_changes && <span className="selo selo--pendente">alterações não publicadas</span>}</td>
                  <td>{when(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
