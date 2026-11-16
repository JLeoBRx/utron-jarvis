import { useId, useMemo, useState, type HTMLAttributes, type KeyboardEvent, type ReactNode } from "react";

import { EmptyState, ErrorState, Skeleton, type EmptyStateProps } from "./feedback";
import { Icon, type IconName } from "./Icon";

// ------------------------------------------------------------------ cartões
export type CardProps = HTMLAttributes<HTMLElement> & {
  title?: ReactNode;
  /** Ícone ao lado do título. */
  icon?: IconName;
  /** Ações no canto do cabeçalho. */
  actions?: ReactNode;
  as?: "section" | "article" | "div";
};

export function Card({ title, icon, actions, as: Tag = "section", className, children, ...rest }: CardProps) {
  const titleId = useId();
  return (
    <Tag className={["ui-cartao", className].filter(Boolean).join(" ")} aria-labelledby={title ? titleId : undefined} {...rest}>
      {(title || actions) && (
        <header className="ui-cartao__cabecalho">
          {title && (
            <h2 className="ui-cartao__titulo" id={titleId}>
              {icon && <Icon name={icon} size={18} />}
              {title}
            </h2>
          )}
          {actions && <div className="ui-cartao__acoes">{actions}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}

export type MetricProps = {
  label: string;
  value: ReactNode;
  /** Unidade ou complemento ("MB", "de 13"). */
  unit?: string;
  hint?: ReactNode;
  tone?: "neutro" | "sucesso" | "atencao" | "erro";
  icon?: IconName;
};

/** Cartão de métrica: valor em fonte de dados, com algarismos tabulares. */
export function MetricCard({ label, value, unit, hint, tone = "neutro", icon }: MetricProps) {
  return (
    <div className={`ui-metrica ui-metrica--${tone}`}>
      <p className="ui-metrica__rotulo">
        {icon && <Icon name={icon} size={16} />}
        {label}
      </p>
      <p className="ui-metrica__valor">
        {value}
        {unit && <span className="ui-metrica__unidade"> {unit}</span>}
      </p>
      {hint && <p className="ui-metrica__dica">{hint}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ tabela
export type Column<Row> = {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  /** Valor usado para ordenar; sem ele, a coluna não ordena. */
  sortValue?: (row: Row) => string | number;
  align?: "inicio" | "fim";
  /** Esconde a coluna em telas estreitas (vira só o cartão principal). */
  secondary?: boolean;
};

export type DataTableProps<Row> = {
  caption: string;
  columns: Column<Row>[];
  rows: Row[] | null;
  rowKey: (row: Row) => string | number;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: EmptyStateProps;
  /** Mostra a legenda (por padrão ela fica só para leitores de tela). */
  showCaption?: boolean;
  initialSort?: { key: string; direction: "ascending" | "descending" };
};

/** Tabela com ordenação, estados de carregando, erro e vazio. Em telas estreitas as linhas viram cartões. */
export function DataTable<Row>({ caption, columns, rows, rowKey, loading, error, onRetry, empty, showCaption, initialSort }: DataTableProps<Row>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const sorted = useMemo(() => {
    if (!rows || !sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const value = column.sortValue;
    const factor = sort.direction === "ascending" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pt-BR")) * factor;
    });
  }, [rows, sort, columns]);

  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (loading && !rows)
    return (
      <div className="ui-tabela__carregando" role="status" aria-label={`${caption}: carregando`}>
        <Skeleton lines={4} />
      </div>
    );
  if (sorted && sorted.length === 0) return <EmptyState title={empty?.title ?? "Nada por aqui ainda"} {...empty} />;

  const toggle = (key: string) =>
    setSort((current) => ({ key, direction: current?.key === key && current.direction === "ascending" ? "descending" : "ascending" }));

  return (
    <div className="ui-tabela" aria-busy={loading || undefined}>
      <table>
        <caption className={showCaption ? "ui-tabela__legenda" : "ui-oculto"}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const direction = sort?.key === column.key ? sort.direction : undefined;
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={[column.align === "fim" && "ui-tabela--fim", column.secondary && "ui-tabela--secundaria"].filter(Boolean).join(" ") || undefined}
                  aria-sort={column.sortValue ? (direction ?? "none") : undefined}
                >
                  {column.sortValue ? (
                    <button type="button" className="ui-tabela__ordenar" onClick={() => toggle(column.key)}>
                      {column.header}
                      <Icon name={direction ? (direction === "ascending" ? "chevron-cima" : "chevron-baixo") : "ordenar"} size={14} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {(sorted ?? []).map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  data-rotulo={column.header}
                  className={[column.align === "fim" && "ui-tabela--fim", column.secondary && "ui-tabela--secundaria"].filter(Boolean).join(" ") || undefined}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ abas
export type TabsProps = {
  label: string;
  tabs: Array<{ id: string; label: string; content: ReactNode; icon?: IconName }>;
  selected?: string;
  onSelect?: (id: string) => void;
};

/** Abas com o padrão do WAI-ARIA: setas trocam de aba, Home e End vão às pontas. */
export function Tabs({ label, tabs, selected, onSelect }: TabsProps) {
  const [internal, setInternal] = useState(tabs[0]?.id ?? "");
  const current = selected ?? internal;
  const base = useId();
  const choose = (id: string) => {
    setInternal(id);
    onSelect?.(id);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((t) => t.id === current);
    const go = (to: number) => {
      const tab = tabs[(to + tabs.length) % tabs.length];
      if (!tab) return;
      choose(tab.id);
      document.getElementById(`${base}-aba-${tab.id}`)?.focus();
    };
    if (event.key === "ArrowRight") go(index + 1);
    else if (event.key === "ArrowLeft") go(index - 1);
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(tabs.length - 1);
    else return;
    event.preventDefault();
  };
  return (
    <div className="ui-abas">
      <div role="tablist" aria-label={label} className="ui-abas__lista" onKeyDown={onKeyDown}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            id={`${base}-aba-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={tab.id === current}
            aria-controls={`${base}-painel-${tab.id}`}
            tabIndex={tab.id === current ? 0 : -1}
            className="ui-abas__aba"
            onClick={() => choose(tab.id)}
          >
            {tab.icon && <Icon name={tab.icon} size={16} />}
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${base}-painel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`${base}-aba-${tab.id}`}
          hidden={tab.id !== current}
          className="ui-abas__painel"
          tabIndex={0}
        >
          {tab.id === current && tab.content}
        </div>
      ))}
    </div>
  );
}
