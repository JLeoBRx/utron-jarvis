import { ChevronRight } from 'lucide-react';
import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router';
import { cn } from '@/lib/utils';

export interface Crumb {
  label: string;
  to?: string;
}

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
  eyebrow?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, breadcrumbs, eyebrow, className }: PageHeaderProps) {
  return (
    <header className={cn('mb-6 animate-rise lg:mb-8', className)}>
      {breadcrumbs?.length ? (
        <nav aria-label="Trilha de navegação" className="mb-3 flex flex-wrap items-center gap-1 text-xs text-fg-subtle">
          {breadcrumbs.map((crumb, index) => (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 ? <ChevronRight className="size-3" aria-hidden /> : null}
              {crumb.to ? (
                <Link to={crumb.to} className="rounded transition-colors hover:text-fg">
                  {crumb.label}
                </Link>
              ) : (
                <span className="max-w-[40ch] truncate text-fg-muted" aria-current="page">
                  {crumb.label}
                </span>
              )}
            </Fragment>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {eyebrow ? <div className="mb-2">{eyebrow}</div> : null}
          <h1 className="text-xl font-semibold tracking-tight text-fg sm:text-2xl">{title}</h1>
          {description ? <p className="mt-1.5 max-w-2xl text-sm text-fg-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
