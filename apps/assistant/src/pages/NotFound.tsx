import { Button, EmptyState } from "@safra/ui";

import { PageHeader } from "../components";
import { useTitle } from "../hooks";
import { navigate } from "../router";

export function NotFoundPage() {
  useTitle("Área não encontrada");
  return (
    <div className="pagina">
      <PageHeader title="Área não encontrada" />
      <EmptyState title="Este endereço não leva a nenhuma área" description="Use o menu ao lado ou volte ao início." icon="busca"
        action={<Button variant="principal" icon="inicio" onClick={() => navigate("/")}>Ir para o início</Button>} />
    </div>
  );
}
