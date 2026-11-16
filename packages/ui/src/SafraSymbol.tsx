import { useId, type CSSProperties } from "react";

import { SYMBOL } from "@safra/design-tokens/symbol";

import { Icon } from "./Icon";

/** Os estados visuais do símbolo. Cada um vem de um estado real do Assistant; nenhum é decorativo. */
export type SymbolState = "inativo" | "inicializando" | "ouvindo" | "processando" | "respondendo" | "erro" | "desconectado";

export const SYMBOL_STATE_LABEL: Record<SymbolState, string> = {
  inativo: "em repouso",
  inicializando: "iniciando",
  ouvindo: "ouvindo",
  processando: "processando",
  respondendo: "respondendo",
  erro: "com erro",
  desconectado: "sem conexão",
};

export type SafraSymbolProps = {
  state?: SymbolState;
  /** Tamanho em px. Até 48 px usa a versão de ícone, com três sulcos. */
  size?: number;
  /** Mostra o rótulo do estado abaixo do símbolo (e o anuncia a leitores de tela quando muda). */
  showLabel?: boolean;
  /** Em "inicializando": fração dos componentes já iniciados (0 a 1). Sem valor, os sulcos surgem em sequência. */
  progress?: number;
  /** Em "respondendo": nível real da voz (0 a 1). Sem valor, o movimento é o da resposta em texto. */
  level?: number;
  /** Preferência do usuário por movimento reduzido (o sistema operacional também é respeitado pelo CSS). */
  reducedMotion?: boolean;
  className?: string;
};

/**
 * O símbolo do SAFRA, estudo "Sulcos": linhas paralelas levemente curvas — sulcos de um campo vistos de cima — sobre
 * uma placa com uma camada de profundidade (2.5D). Só SVG e CSS: sem canvas, sem WebGL, sem biblioteca de animação.
 * Os estados diferem por forma e movimento, além da cor, e sempre têm rótulo para leitores de tela.
 * Em repouso não há laço de animação: o símbolo parado não gasta processador.
 */
export function SafraSymbol({ state = "inativo", size = 160, showLabel = false, progress, level, reducedMotion = false, className }: SafraSymbolProps) {
  const clip = useId().replace(/:/g, "");
  const compact = size <= 48;
  const lines = compact ? SYMBOL.icone.sulcos : SYMBOL.sulcos;
  const width = compact ? SYMBOL.icone.espessura : SYMBOL.espessura;
  const visible = state === "inicializando" && typeof progress === "number" ? Math.ceil(Math.max(0, Math.min(1, progress)) * lines.length) : lines.length;
  const label = `SAFRA — ${SYMBOL_STATE_LABEL[state]}`;
  const style = (typeof level === "number" ? { "--nivel": Math.max(0, Math.min(1, level)).toFixed(2) } : {}) as CSSProperties;
  return (
    <div
      className={[
        "ui-simbolo",
        `ui-simbolo--${state}`,
        compact && "ui-simbolo--compacto",
        reducedMotion && "ui-simbolo--parado",
        typeof progress === "number" && "ui-simbolo--com-progresso",
        typeof level === "number" && "ui-simbolo--com-nivel",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ ...style, width: size }}
      data-estado={state}
    >
      <svg viewBox={SYMBOL.viewBox} width={size} height={size} role="img" aria-label={label}>
        <defs>
          <clipPath id={clip}>
            <rect {...SYMBOL.placa} />
          </clipPath>
        </defs>
        <rect className="ui-simbolo__fundo" {...SYMBOL.profundidade} />
        <rect className="ui-simbolo__placa" {...SYMBOL.placa} />
        <g clipPath={`url(#${clip})`}>
          <g className="ui-simbolo__sulcos" fill="none" strokeLinecap="round" strokeWidth={width}>
            {lines.map((d, index) => (
              <path
                key={index}
                d={d}
                className="ui-simbolo__sulco"
                data-oculto={index >= visible ? "" : undefined}
                style={{ "--i": index, opacity: index >= visible ? 0 : SYMBOL.opacidades[index] } as CSSProperties}
              />
            ))}
          </g>
        </g>
      </svg>
      {(state === "erro" || state === "desconectado") && (
        <span className="ui-simbolo__marca" aria-hidden="true">
          <Icon name={state === "erro" ? "alerta" : "sem-conexao"} size={compact ? 12 : Math.round(size / 7)} />
        </span>
      )}
      {showLabel && (
        <p className="ui-simbolo__rotulo" aria-live="polite">
          {SYMBOL_STATE_LABEL[state]}
        </p>
      )}
    </div>
  );
}
