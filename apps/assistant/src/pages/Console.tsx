import { Card, DataTable, ErrorState, MetricCard, Skeleton, StatusBadge, type Column } from "@safra/ui";

import { NotImplemented, PageHeader, SituationBadge } from "../components";
import { formatDuration } from "../format";
import { useResource, useTitle } from "../hooks";
import { href } from "../router";
import type { Activity, AiStatus, ModuleStatus, ProcessSettings, Project, Resources, SystemStatus } from "../types";
import { activityColumns, HealthList, RESOURCE_REFRESH_MS, ResourceCards } from "./Monitoring";

const MODULE_LABEL: Record<string, string> = {
  core: "Núcleo", storage: "Armazenamento", security: "Segurança", monitoring: "Monitoramento", platform: "Plataforma (Windows)",
  memory: "Memória", ai_gateway: "Gateway de IA", voice: "Voz", communication: "Comunicação", projects: "Projetos",
  tools: "Ferramentas", intelligence: "Inteligência", api: "API local",
};

const moduleColumns: Column<ModuleStatus>[] = [
  { key: "modulo", header: "Módulo", sortValue: (m) => MODULE_LABEL[m.name] ?? m.name, render: (m) => <div className="celula-principal"><strong>{MODULE_LABEL[m.name] ?? m.name}</strong><span className="apoio dado">{m.name}</span></div> },
  { key: "situacao", header: "Situação", sortValue: (m) => m.situacao, render: (m) => <SituationBadge situation={m.situacao} /> },
  { key: "fase", header: "Fase", align: "fim", sortValue: (m) => m.fase, render: (m) => m.fase },
  { key: "resumo", header: "O que existe", secondary: true, render: (m) => <span className="apoio">{m.resumo}</span> },
];

/** Central de operação: denso, tudo vindo da API local. O que não existe aparece como não implementado. */
export function ConsolePage() {
  useTitle("Console");
  const status = useResource<SystemStatus>("/system/status", 15_000);
  const resources = useResource<Resources>("/system/resources", RESOURCE_REFRESH_MS);
  const activity = useResource<Activity[]>("/activity?limit=12", 15_000);
  const projects = useResource<Project[]>("/projects?status=active");
  const ai = useResource<AiStatus>("/ai/status");
  const settings = useResource<ProcessSettings>("/system/settings");
  const s = status.data;
  const implemented = s?.modules.filter((m) => m.situacao !== "planejado").length ?? 0;
  return (
    <div className="pagina pagina--console">
      <PageHeader title="Console" description="Operação do Assistant pela API local. Somente leitura nesta fase: nenhuma operação privilegiada fica exposta aqui." />
      {status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : !s ? <Skeleton lines={3} /> : (
        <div className="grade grade--4">
          <MetricCard label="Núcleo" icon="energia" value={s.health.status === "ok" ? "no ar" : s.health.status === "degraded" ? "com avisos" : "com falha"}
            tone={s.health.status === "ok" ? "sucesso" : s.health.status === "degraded" ? "atencao" : "erro"} hint={`versão ${s.version} · ${s.environment}`} />
          <MetricCard label="No ar há" icon="relogio" value={formatDuration(Math.round(Date.now() / 1000 - s.started_at))} />
          <MetricCard label="Módulos com código" icon="arquitetura" value={implemented} unit={`de ${s.modules.length}`} hint="os demais estão planejados" />
          <MetricCard label="Banco" icon="banco" value={s.database.revision === s.database.head ? "atual" : "desatualizado"}
            tone={s.database.revision === s.database.head ? "sucesso" : "erro"} hint={`versão ${s.database.revision ?? "—"}`} />
        </div>
      )}
      <ResourceCards resources={resources} />
      <div className="grade grade--console">
        <Card title="Módulos" icon="arquitetura" className="console__modulos">
          <DataTable caption="Módulos do Assistant" columns={moduleColumns} rows={s?.modules ?? null} rowKey={(m) => m.name} loading={!s} />
        </Card>
        <div className="pilha">
          <Card title="Provedor de IA" icon="ia">
            {!ai.data ? <Skeleton lines={2} /> : (
              <>
                <p><StatusBadge tone="atencao">não implementado</StatusBadge></p>
                <p className="apoio">{ai.data.providers.length === 0 ? "Nenhum provedor cadastrado." : `${ai.data.providers.length} provedores cadastrados.`} Gateway na Fase {ai.data.gateway.fase}.</p>
              </>
            )}
          </Card>
          <Card title="Saúde do banco" icon="banco">
            {!s ? <Skeleton lines={2} /> : <HealthList status={s} />}
          </Card>
          <Card title="Voz" icon="microfone">
            {!s ? <Skeleton lines={1} /> : <NotImplemented title="Voz ainda não implementada" phase={s.voice.fase} />}
          </Card>
        </div>
      </div>
      <div className="grade grade--2">
        <Card title="Atividade recente" icon="lista" actions={<a className="link" href={href("/monitoramento")}>Tudo</a>}>
          <DataTable caption="Atividade recente" columns={activityColumns} rows={activity.data} rowKey={(a) => a.id} loading={activity.loading}
            error={activity.error} onRetry={activity.reload} empty={{ title: "Nenhuma atividade", icon: "monitoramento" }} />
        </Card>
        <div className="pilha">
          <Card title="Projetos ativos" icon="projetos" actions={<a className="link" href={href("/projetos")}>Abrir</a>}>
            {!projects.data ? <Skeleton lines={2} /> : projects.data.length === 0 ? <p className="apoio">Nenhum projeto ativo.</p> : (
              <ul className="lista-simples">{projects.data.slice(0, 6).map((p) => <li key={p.id}><a href={href(`/projetos/${p.id}`)}>{p.name}</a><span className="apoio">{p.conversation_count} conv. · {p.memory_count} mem.</span></li>)}</ul>
            )}
          </Card>
          <Card title="Configuração do processo" icon="configuracoes" actions={<a className="link" href={href("/configuracoes")}>Detalhes</a>}>
            {settings.error ? <ErrorState message={settings.error} onRetry={settings.reload} /> : !settings.data ? <Skeleton lines={2} /> : (
              <dl className="dados dados--compacto">
                <dt>Endereço</dt><dd className="dado">{settings.data.api_host}:{settings.data.api_port}</dd>
                <dt>Ambiente</dt><dd className="dado">{settings.data.environment}</dd>
                <dt>Registro</dt><dd className="dado">{settings.data.log_level}{settings.data.log_to_file ? " · arquivo" : ""}</dd>
              </dl>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
