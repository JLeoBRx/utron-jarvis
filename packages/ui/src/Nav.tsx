import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type NavItem = {
  id: string;
  label: string;
  href: string;
  icon: IconName;
  /** Número de pendências (ex.: rascunhos). Lido junto com o nome. */
  badge?: number;
};

export type NavGroup = { label?: string; items: NavItem[] };

export type SideNavProps = {
  label: string;
  groups: NavGroup[];
  current: string;
  /** Marca e informação no topo. */
  header?: ReactNode;
  footer?: ReactNode;
};

/**
 * Navegação principal. Larga: barra lateral com rótulos. De 600 a 899 px: só ícones (o nome continua para leitores
 * de tela e como dica). Abaixo de 600 px: barra rolável no rodapé da tela.
 */
export function SideNav({ label, groups, current, header, footer }: SideNavProps) {
  return (
    <nav className="ui-navegacao" aria-label={label}>
      {header && <div className="ui-navegacao__topo">{header}</div>}
      <div className="ui-navegacao__grupos">
        {groups.map((group, index) => (
          <div key={group.label ?? index} className="ui-navegacao__grupo">
            {group.label && <p className="ui-navegacao__titulo">{group.label}</p>}
            <ul>
              {group.items.map((item) => (
                <li key={item.id}>
                  <a
                    href={item.href}
                    className="ui-navegacao__item"
                    aria-current={item.id === current ? "page" : undefined}
                    title={item.label}
                  >
                    <Icon name={item.icon} size={20} />
                    <span className="ui-navegacao__rotulo">{item.label}</span>
                    {item.badge ? (
                      <span className="ui-navegacao__pendencias">
                        {item.badge}
                        <span className="ui-oculto"> pendentes</span>
                      </span>
                    ) : null}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {footer && <div className="ui-navegacao__rodape">{footer}</div>}
    </nav>
  );
}
