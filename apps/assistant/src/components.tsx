import type { ReactNode } from "react";

import { Banner, Button, StatusBadge } from "@safra/ui";

import { useConnection } from "./connection";
import { SITUATION_LABEL, SITUATION_TONE } from "./format";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="pagina__cabecalho">
      <div>
        <h1 className="pagina__titulo" id="titulo-da-pagina" tabIndex={-1}>
          {title}
        </h1>
        {description && <p className="pagina__descricao">{description}</p>}
      </div>
      {actions && <div className="pagina__acoes">{actions}</div>}
    </header>
  );
}

/** Faixa de "ainda não existe", com a fase em que chega. Nada é simulado no lugar. */
export function NotImplemented({ title, phase, children }: { title: string; phase: number; children?: ReactNode }) {
  return (
    <Banner tone="atencao" title={title}>
      {children}
      <p>Previsto para a Fase {phase} do plano.</p>
    </Banner>
  );
}

export function SituationBadge({ situation }: { situation: keyof typeof SITUATION_LABEL }) {
  return <StatusBadge tone={SITUATION_TONE[situation]}>{SITUATION_LABEL[situation]}</StatusBadge>;
}

/** Faixa global quando a ligação com o Assistant cai: as ações ficam desabilitadas até voltar. */
export function ConnectionBanner() {
  const { state, lastOk, retry } = useConnection();
  if (state === "conectado") return null;
  if (state === "conectando")
    return (
      <Banner tone="informacao" title="Conectando ao Assistant…">
        Conferindo a API local neste computador.
      </Banner>
    );
  return (
    <Banner
      tone="erro"
      title={state === "reconectando" ? "Reconectando ao Assistant…" : "Sem conexão com o Assistant"}
      action={<Button size="pequeno" icon="atualizar" onClick={retry}>Tentar de novo</Button>}
    >
      {lastOk ? `Os dados mostrados são de ${lastOk.toLocaleTimeString("pt-BR")}. ` : ""}As ações ficam desabilitadas até a conexão voltar.
    </Banner>
  );
}

export function useCanAct(): boolean {
  return useConnection().state === "conectado";
}
