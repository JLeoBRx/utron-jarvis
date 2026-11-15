import { get } from "../api";
import { Badge, Empty, ErrorBox, Loading, Notice, useLoad } from "../components/ui";
import { action, when } from "../format";
import { href } from "../router";
import { useSession } from "../session";
import type { Dashboard } from "../types";

export function DashboardPage() {
  const { identity } = useSession();
  const { data, error, loading, reload } = useLoad(() => get<Dashboard>("/dashboard"));
  return (
    <>
      <header className="pagina__cabecalho"><h1>Resumo</h1><p>Olá, {identity.user.name}.</p></header>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && (
        <>
          <div className="metricas">
            <Metric label="Páginas publicadas" value={data.pages.published} />
            <Metric label="Páginas em rascunho" value={data.pages.draft} />
            <Metric label="Notícias publicadas" value={data.news.published} />
            <Metric label="Notícias em rascunho" value={data.news.draft} />
            <Metric label="Imagens" value={data.media} />
          </div>
          {data.downloads_blocked && (
            <Notice tone="atencao">A publicação de instaladores está bloqueada até a conclusão do inventário de licenças.</Notice>
          )}
          <div className="grade-2">
            <section className="cartao" aria-labelledby="ultimas">
              <h2 id="ultimas">Últimas alterações</h2>
              {data.recent_changes.length === 0 ? <Empty>Nenhum conteúdo ainda.</Empty> : (
                <ul className="lista-simples">
                  {data.recent_changes.map((item) => (
                    <li key={`${item.type}-${item.id}`}>
                      <a href={href(`${item.type === "page" ? "pages" : "news"}/${item.id}`)}>{item.title}</a>
                      <span><Badge status={item.status} />{item.has_unpublished_changes && <span className="selo selo--pendente">alterações não publicadas</span>} {when(item.updated_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="cartao" aria-labelledby="atividades">
              <h2 id="atividades">Atividades administrativas</h2>
              {data.activity.length === 0 ? <Empty>Nenhuma atividade registrada.</Empty> : (
                <ul className="lista-simples">
                  {data.activity.map((entry) => (
                    <li key={entry.id}><span>{entry.actor || "sistema"} {action(entry.action)}</span><span>{when(entry.at)}</span></li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metrica"><span className="metrica__valor">{value}</span><span className="metrica__rotulo">{label}</span></div>;
}
