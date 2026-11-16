import { Card, DataTable, ErrorState, MetricCard, Skeleton, StatusBadge, type Column } from "@safra/ui";

import { PageHeader } from "../components";
import { formatBytes, formatDateTime, formatDuration } from "../format";
import { useResource, useTitle } from "../hooks";
import type { Activity, Resources, SystemStatus } from "../types";

export const RESOURCE_REFRESH_MS = 5_000;
const CHECK_LABEL: Record<string, string> = { storage: "Banco de dados", schema: "Versão do banco" };

export function ResourceCards({ resources }: { resources: ReturnType<typeof useResource<Resources>> }) {
  if (resources.error) return <ErrorState message={resources.error} onRetry={resources.reload} />;
  if (!resources.data) return <Skeleton lines={2} />;
  const r = resources.data;
  return (
    <div className="grade grade--4">
      <MetricCard label="Memória do Assistant" icon="processador" value={r.process.rss_mb.toFixed(1)} unit="MB" hint={`${r.process.threads} linhas de execução`} />
      <MetricCard label="CPU do Assistant" icon="monitoramento" value={r.process.cpu_percent.toFixed(1)} unit="%" hint="100% = um núcleo" />
      <MetricCard label="Memória do computador" icon="processador" value={r.system.memory_used_percent.toFixed(0)} unit="%" hint={`de ${(r.system.memory_total_mb / 1024).toFixed(1)} GB`} />
      <MetricCard label="Banco de dados" icon="banco" value={formatBytes(r.storage.database_bytes)} hint={r.storage.disk_free_mb !== null ? `${(r.storage.disk_free_mb / 1024).toFixed(1)} GB livres no disco` : undefined} />
    </div>
  );
}

export function HealthList({ status }: { status: SystemStatus }) {
  return (
    <ul className="lista-saude">
      {status.health.checks.map((c) => (
        <li key={c.name}>
          <StatusBadge tone={c.ok ? "sucesso" : "erro"}>{c.ok ? "ok" : "falhou"}</StatusBadge>
          <span>{CHECK_LABEL[c.name] ?? c.name}</span>
          <span className="apoio">{c.elapsed_ms.toFixed(1)} ms{c.detail ? ` · ${c.detail}` : ""}</span>
        </li>
      ))}
    </ul>
  );
}

export const activityColumns: Column<Activity>[] = [
  { key: "quando", header: "Quando", sortValue: (a) => a.at, render: (a) => <span className="dado">{formatDateTime(a.at)}</span> },
  { key: "tipo", header: "Tipo", secondary: true, sortValue: (a) => a.kind, render: (a) => a.kind },
  { key: "titulo", header: "O que aconteceu", render: (a) => a.title },
  { key: "estado", header: "Estado", render: (a) => <StatusBadge tone={a.state === "done" ? "sucesso" : a.state === "indisponivel" ? "atencao" : "neutro"}>{a.state === "done" ? "concluído" : a.state === "indisponivel" ? "indisponível" : a.state}</StatusBadge> },
];

export function MonitoringPage() {
  useTitle("Monitoramento");
  const status = useResource<SystemStatus>("/system/status", 15_000);
  const resources = useResource<Resources>("/system/resources", RESOURCE_REFRESH_MS);
  const activity = useResource<Activity[]>("/activity?limit=50", 15_000);
  return (
    <div className="pagina">
      <PageHeader title="Monitoramento" description="Medido agora, neste computador. Os recursos se atualizam a cada 5 segundos enquanto esta tela está aberta." />
      <ResourceCards resources={resources} />
      <div className="grade grade--2">
        <Card title="Saúde" icon="sucesso">
          {status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : !status.data ? <Skeleton /> : (
            <>
              <p className="saude-geral">
                <StatusBadge tone={status.data.health.status === "ok" ? "sucesso" : status.data.health.status === "degraded" ? "atencao" : "erro"}>
                  {status.data.health.status === "ok" ? "tudo certo" : status.data.health.status === "degraded" ? "com avisos" : "com falha"}
                </StatusBadge>
                <span className="apoio">no ar há {formatDuration(Math.round(Date.now() / 1000 - status.data.started_at))}</span>
              </p>
              <HealthList status={status.data} />
            </>
          )}
        </Card>
        <Card title="Banco privado" icon="banco">
          {!status.data ? <Skeleton /> : (
            <dl className="dados">
              <dt>Arquivo</dt><dd className="dado">{status.data.database.file ?? "—"}</dd>
              <dt>Versão</dt><dd className="dado">{status.data.database.revision} {status.data.database.revision === status.data.database.head ? "(atual)" : `(esperada ${status.data.database.head})`}</dd>
              <dt>Tamanho</dt><dd className="dado">{formatBytes(status.data.database.size_bytes)}</dd>
              <dt>Conteúdo</dt><dd>{status.data.database.counts.conversations} conversas, {status.data.database.counts.messages} mensagens, {status.data.database.counts.memories} memórias, {status.data.database.counts.projects} projetos</dd>
            </dl>
          )}
        </Card>
      </div>
      <Card title="Atividades" icon="lista">
        <DataTable caption="Atividades recentes" columns={activityColumns} rows={activity.data} rowKey={(a) => a.id} loading={activity.loading}
          error={activity.error} onRetry={activity.reload} empty={{ title: "Nenhuma atividade registrada", icon: "monitoramento" }} />
      </Card>
    </div>
  );
}
