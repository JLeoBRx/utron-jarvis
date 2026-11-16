import { Button, Card, EmptyState, ErrorState, MetricCard, SafraSymbol, Skeleton } from "@safra/ui";

import { useSymbolState } from "../activity";
import { NotImplemented, PageHeader } from "../components";
import { formatRelative } from "../format";
import { useResource, useTitle } from "../hooks";
import { usePreferences, useReducedMotion } from "../preferences";
import { href, navigate } from "../router";
import type { Activity, ConversationSummary, SystemStatus } from "../types";

export function HomePage() {
  useTitle("Início");
  const state = useSymbolState();
  const reduced = useReducedMotion();
  const { prefs } = usePreferences();
  const status = useResource<SystemStatus>("/system/status");
  const recent = useResource<ConversationSummary[]>("/conversations?limit=5");
  const events = useResource<Activity[]>("/activity?limit=5");
  const name = typeof prefs?.nome.value === "string" && prefs.nome.value ? prefs.nome.value : "";
  return (
    <div className="pagina pagina--inicio">
      <PageHeader title={name ? `Olá, ${name}` : "Início"} description="O SAFRA roda neste computador. Seus dados ficam aqui." />
      <section className="inicio__presenca" aria-label="Estado do SAFRA">
        <SafraSymbol state={state} size={168} showLabel reducedMotion={reduced} />
        <div className="inicio__acoes">
          <Button variant="principal" icon="conversa" onClick={() => navigate("/conversas")}>Nova conversa</Button>
          <Button icon="memoria" onClick={() => navigate("/memoria")}>Registrar na memória</Button>
          <Button variant="discreto" icon="painel" onClick={() => navigate("/console")}>Abrir o console</Button>
        </div>
      </section>
      <NotImplemented title="O SAFRA ainda não gera respostas" phase={5}>
        <p>O gateway de IA não foi implementado. Você já pode conversar e organizar projetos e memórias: tudo fica guardado e pronto para quando ele chegar.</p>
      </NotImplemented>
      <div className="grade grade--3">
        {status.data ? (
          <>
            <MetricCard label="Conversas" icon="conversa" value={status.data.database.counts.conversations} hint={`${status.data.database.counts.messages} ${status.data.database.counts.messages === 1 ? "mensagem" : "mensagens"}`} />
            <MetricCard label="Memórias" icon="memoria" value={status.data.database.counts.memories} />
            <MetricCard label="Projetos" icon="projetos" value={status.data.database.counts.projects} />
          </>
        ) : status.error ? (
          <ErrorState message={status.error} onRetry={status.reload} />
        ) : (
          <Skeleton lines={2} />
        )}
      </div>
      <div className="grade grade--2">
        <Card title="Conversas recentes" icon="historico" actions={<a className="link" href={href("/historico")}>Ver histórico</a>}>
          {recent.error ? <ErrorState message={recent.error} onRetry={recent.reload} /> : !recent.data ? <Skeleton /> : recent.data.length === 0 ? (
            <EmptyState title="Nenhuma conversa ainda" description="Comece uma conversa: ela fica guardada neste computador." icon="conversa" />
          ) : (
            <ul className="lista-simples">
              {recent.data.map((c) => (
                <li key={c.id}>
                  <a href={href(`/conversas/${c.id}`)}>{c.title}</a>
                  <span className="apoio">{formatRelative(c.updated_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Atividade recente" icon="monitoramento" actions={<a className="link" href={href("/monitoramento")}>Ver tudo</a>}>
          {events.error ? <ErrorState message={events.error} onRetry={events.reload} /> : !events.data ? <Skeleton /> : events.data.length === 0 ? (
            <EmptyState title="Sem atividade registrada" icon="monitoramento" />
          ) : (
            <ul className="lista-simples">
              {events.data.map((e) => (
                <li key={e.id}>
                  <span>{e.title}</span>
                  <span className="apoio">{formatRelative(e.at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
