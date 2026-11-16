import type { LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';
import { cn } from '@/lib/utils';

export interface TabItem {
  to: string;
  label: string;
  icon?: LucideIcon;
  count?: number;
  end?: boolean;
}

/** Abas baseadas em rotas (cada aba tem URL própria). Rola horizontalmente no celular. */
export function TabNav({ items, label }: { items: TabItem[]; label: string }) {
  return (
    <nav aria-label={label} className="-mx-4 mb-6 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
      <ul className="flex min-w-max gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                replace
                className={({ isActive }) =>
                  cn(
                    'relative flex h-10 items-center gap-1.5 px-2.5 text-[13px] font-medium whitespace-nowrap transition-colors',
                    isActive ? 'text-fg' : 'text-fg-subtle hover:text-fg-muted',
                    "after:absolute after:inset-x-1.5 after:-bottom-px after:h-0.5 after:rounded-full after:content-['']",
                    isActive ? 'after:bg-accent' : 'after:bg-transparent',
                  )
                }
              >
                {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
                {item.label}
                {item.count !== undefined && item.count > 0 ? (
                  <span className="rounded bg-surface-2 px-1 text-[10px] text-fg-muted tabular">{item.count}</span>
                ) : null}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
