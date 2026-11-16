import { Card, DataTable, ErrorState, Select, Skeleton, StatusBadge, type Column } from "@safra/ui";

import { NotImplemented, PageHeader } from "../components";
import { useResource, useTitle } from "../hooks";
import type { AiStatus } from "../types";

type Provider = AiStatus["providers"][number];

export function AiPage() {
  useTitle("Inteligência artificial");
  const status = useResource<AiStatus>("/ai/status");
  const columns: Column<Provider>[] = [
    { key: "nome", header: "Provedor", sortValue: (p) => p.name, render: (p) => <strong>{p.name}</strong> },
    { key: "tipo", header: "Onde roda", render: (p) => (p.kind === "local" ? "neste computador" : "remoto") },
    { key: "modelo", header: "Modelo padrão", render: (p) => p.default_model || "—" },
    { key: "privado", header: "Pode receber conteúdo privado", render: (p) => <StatusBadge tone={p.allows_private ? "atencao" : "sucesso"}>{p.allows_private ? "sim" : "não"}</StatusBadge> },
    { key: "situacao", header: "Situação", render: (p) => (p.enabled ? "habilitado" : "desabilitado") },
  ];
  return (
    <div className="pagina">
      <PageHeader title="Inteligência artificial" description="IA híbrida: modelos locais, neste computador, e remotos, quando você permitir — com uma política que decide o que pode sair daqui." />
      {status.error ? <ErrorState message={status.error} onRetry={status.reload} /> : !status.data ? <Skeleton lines={4} /> : (
        <>
          <NotImplemented title="O gateway de IA ainda não existe" phase={status.data.gateway.fase}>
            <p>{status.data.gateway.mensagem}</p>
          </NotImplemented>
          <div className="grade grade--2">
            <Card title="Provedor em uso" icon="ia">
              <Select label="Provedor para as próximas respostas" disabled options={status.data.providers.length ? status.data.providers.map((p) => ({ value: String(p.id), label: p.name })) : [{ value: "", label: "Nenhum provedor cadastrado" }]}
                help="A escolha fica disponível quando o gateway existir e houver provedores habilitados." />
            </Card>
            <Card title="Como a escolha vai funcionar" icon="escudo">
              <ul className="lista-pontos">
                <li>Conteúdo privado só vai para provedores marcados como aptos a recebê-lo.</li>
                <li>Modelos locais são preferidos quando atendem ao pedido.</li>
                <li>Se o provedor escolhido falhar, a resposta diz isso — nada é inventado no lugar.</li>
                <li>Credenciais ficam no cofre do sistema; a interface nunca as vê.</li>
              </ul>
            </Card>
          </div>
          <Card title="Provedores cadastrados" icon="lista">
            <DataTable caption="Provedores de IA cadastrados" columns={columns} rows={status.data.providers} rowKey={(p) => p.id}
              empty={{ title: "Nenhum provedor cadastrado", description: "O cadastro de provedores chega com o gateway de IA.", icon: "ia" }} />
          </Card>
        </>
      )}
    </div>
  );
}
