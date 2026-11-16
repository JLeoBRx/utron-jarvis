import { Card, DataTable, ErrorState, Skeleton, StatusBadge, type Column } from "@safra/ui";

import { NotImplemented, PageHeader } from "../components";
import { formatDateTime } from "../format";
import { useResource, useTitle } from "../hooks";
import type { ToolsOverview } from "../types";

type Tool = ToolsOverview["tools"][number];
type Execution = ToolsOverview["executions"][number];

export function ToolsPage() {
  useTitle("Ferramentas");
  const data = useResource<ToolsOverview>("/tools");
  const tools: Column<Tool>[] = [
    { key: "nome", header: "Ferramenta", sortValue: (t) => t.name, render: (t) => <div className="celula-principal"><strong>{t.name}</strong><span className="apoio">{t.description}</span></div> },
    { key: "categoria", header: "Categoria", sortValue: (t) => t.category, render: (t) => t.category },
    { key: "risco", header: "Risco", render: (t) => <StatusBadge tone={t.risk === "high" ? "erro" : t.risk === "medium" ? "atencao" : "neutro"}>{t.risk}</StatusBadge> },
    { key: "ativa", header: "Situação", render: (t) => (t.enabled ? "habilitada" : "desabilitada") },
  ];
  const executions: Column<Execution>[] = [
    { key: "quando", header: "Quando", render: (e) => formatDateTime(e.requested_at) },
    { key: "ferramenta", header: "Ferramenta", render: (e) => e.tool },
    { key: "estado", header: "Estado", render: (e) => e.status },
    { key: "verificada", header: "Efeito conferido", render: (e) => (e.verified === null ? "—" : e.verified ? "sim" : "não") },
  ];
  return (
    <div className="pagina">
      <PageHeader title="Ferramentas" description="Ações que o SAFRA poderá executar no computador, sempre pelo executor único e com as suas políticas." />
      {data.error ? <ErrorState message={data.error} onRetry={data.reload} /> : !data.data ? <Skeleton lines={4} /> : (
        <>
          <NotImplemented title="Nenhuma ferramenta pode ser executada nesta versão" phase={data.data.executor.fase}>
            <p>{data.data.executor.mensagem}</p>
          </NotImplemented>
          <Card title="Ferramentas cadastradas" icon="ferramentas">
            <DataTable caption="Ferramentas cadastradas" columns={tools} rows={data.data.tools} rowKey={(t) => t.name}
              empty={{ title: "Nenhuma ferramenta cadastrada", description: "O catálogo é preenchido junto com o executor e as políticas de permissão.", icon: "ferramentas" }} />
          </Card>
          <Card title="Execuções registradas" icon="lista">
            <DataTable caption="Execuções registradas" columns={executions} rows={data.data.executions} rowKey={(e) => e.id}
              empty={{ title: "Nenhuma execução", description: "Sem executor, nada foi executado.", icon: "lista" }} />
          </Card>
        </>
      )}
    </div>
  );
}
