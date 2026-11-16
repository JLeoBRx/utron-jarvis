import { useEffect, useState } from "react";

import { Button, DataTable, SearchField, Switch, useToast, type Column } from "@safra/ui";

import { api, messageOf } from "../api";
import { PageHeader, useCanAct } from "../components";
import { formatDateTime } from "../format";
import { useResource, useTitle } from "../hooks";
import { href } from "../router";
import type { ConversationSummary } from "../types";

export function HistoryPage() {
  useTitle("Histórico");
  const toast = useToast();
  const canAct = useCanAct();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [archived, setArchived] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const params = new URLSearchParams({ limit: "200", ...(debounced ? { q: debounced } : {}), ...(archived ? { archived: "true" } : {}) });
  const list = useResource<ConversationSummary[]>(`/conversations?${params.toString()}`);

  const toggleArchive = async (c: ConversationSummary) => {
    try {
      await api.patch(`/conversations/${c.id}`, { archived: !c.archived });
      toast.notify(c.archived ? "Conversa desarquivada." : "Conversa arquivada.");
      await list.reload();
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };

  const columns: Column<ConversationSummary>[] = [
    { key: "titulo", header: "Conversa", sortValue: (c) => c.title, render: (c) => (
      <div className="celula-principal">
        <a href={href(`/conversas/${c.id}`)}>{c.title}</a>
        <span className="apoio">{c.preview || "Sem mensagens"}</span>
      </div>
    ) },
    { key: "mensagens", header: "Mensagens", align: "fim", secondary: true, sortValue: (c) => c.message_count, render: (c) => c.message_count },
    { key: "atualizada", header: "Última atividade", sortValue: (c) => c.updated_at, render: (c) => formatDateTime(c.updated_at) },
    { key: "acoes", header: "Ações", align: "fim", render: (c) => (
      <Button size="pequeno" variant="discreto" icon={c.archived ? "restaurar" : "arquivar"} disabled={!canAct} onClick={() => void toggleArchive(c)}>
        {c.archived ? "Desarquivar" : "Arquivar"}
      </Button>
    ) },
  ];

  return (
    <div className="pagina">
      <PageHeader title="Histórico" description="Todas as conversas guardadas neste computador. A busca procura no título e no texto das mensagens." />
      <div className="filtros">
        <SearchField label="Buscar" placeholder="Palavras da conversa" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Switch label="Mostrar arquivadas" checked={archived} onChange={setArchived} />
      </div>
      <DataTable caption={archived ? "Conversas arquivadas" : "Conversas"} columns={columns} rows={list.data} rowKey={(c) => c.id}
        loading={list.loading} error={list.error} onRetry={list.reload} initialSort={{ key: "atualizada", direction: "descending" }}
        empty={{ title: debounced ? "Nenhuma conversa com essas palavras" : archived ? "Nenhuma conversa arquivada" : "Nenhuma conversa ainda", icon: "historico" }} />
    </div>
  );
}
