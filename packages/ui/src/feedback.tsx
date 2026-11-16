import type { ReactNode } from "react";

import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";

/** Progresso indeterminado. Anunciado como "carregando" (ou o rótulo dado). */
export function Spinner({ label = "Carregando", size = "normal" }: { label?: string; size?: "normal" | "pequeno" }) {
  return (
    <span className={`ui-carregando ui-carregando--${size}`} role="status">
      <span className="ui-giro" aria-hidden="true" />
      <span className="ui-carregando__texto">{label}</span>
    </span>
  );
}

/** Esqueleto: marca o espaço do conteúdo que ainda vai chegar. Decorativo: quem anuncia é o contêiner. */
export function Skeleton({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={["ui-esqueleto", className].filter(Boolean).join(" ")} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="ui-esqueleto__linha" />
      ))}
    </div>
  );
}

export type EmptyStateProps = {
  title: string;
  description?: ReactNode;
  icon?: IconName;
  /** A próxima ação: o que a pessoa pode fazer agora. */
  action?: ReactNode;
};

export function EmptyState({ title, description, icon = "lista", action }: EmptyStateProps) {
  return (
    <div className="ui-vazio">
      <span className="ui-vazio__icone">
        <Icon name={icon} size={24} />
      </span>
      <p className="ui-vazio__titulo">{title}</p>
      {description && <p className="ui-vazio__texto">{description}</p>}
      {action && <div className="ui-vazio__acao">{action}</div>}
    </div>
  );
}

export type ErrorStateProps = {
  title?: string;
  /** O que aconteceu e o que fazer. */
  message: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
};

/** Erro num painel, com "Tentar de novo". Anunciado assim que aparece. */
export function ErrorState({ title = "Não foi possível carregar", message, onRetry, retryLabel = "Tentar de novo" }: ErrorStateProps) {
  return (
    <div className="ui-erro" role="alert">
      <span className="ui-erro__icone">
        <Icon name="erro" size={24} />
      </span>
      <div>
        <p className="ui-erro__titulo">{title}</p>
        <p className="ui-erro__texto">{message}</p>
        {onRetry && (
          <Button size="pequeno" icon="atualizar" onClick={onRetry}>
            {retryLabel}
          </Button>
        )}
      </div>
    </div>
  );
}

export type Tone = "neutro" | "sucesso" | "atencao" | "erro" | "informacao" | "marca";

const TONE_ICON: Record<Tone, IconName> = {
  neutro: "informacao",
  sucesso: "sucesso",
  atencao: "alerta",
  erro: "erro",
  informacao: "informacao",
  marca: "ia",
};

/** Faixa persistente (sem conexão, dados simulados, não implementado). Nunca depende só da cor: tem ícone e texto. */
export function Banner({ tone = "informacao", title, children, action }: { tone?: Tone; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={`ui-faixa ui-faixa--${tone}`} role={tone === "erro" ? "alert" : "status"}>
      <Icon name={TONE_ICON[tone]} size={20} />
      <div className="ui-faixa__corpo">
        <p className="ui-faixa__titulo">{title}</p>
        {children && <div className="ui-faixa__texto">{children}</div>}
      </div>
      {action && <div className="ui-faixa__acao">{action}</div>}
    </div>
  );
}

/** Selo de estado: ícone + texto (nunca só a cor). */
export function StatusBadge({ tone = "neutro", children, icon }: { tone?: Tone; children: ReactNode; icon?: IconName }) {
  return (
    <span className={`ui-selo ui-selo--${tone}`}>
      <Icon name={icon ?? TONE_ICON[tone]} size={14} />
      {children}
    </span>
  );
}
