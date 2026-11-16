import { AlertTriangle, Loader2, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { errorMessage } from '@/lib/errors';
import { cn } from '@/lib/utils';
import { Button } from './Button';

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-surface-2', className)} aria-hidden />;
}

export function Spinner({ className, label = 'Carregando…' }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn('inline-flex items-center gap-2 text-fg-subtle', className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  compact?: boolean;
}

export function EmptyState({ icon, title, description, actions, className, compact }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'gap-2 px-4 py-8' : 'gap-3 px-6 py-14',
        className,
      )}
    >
      <div className="flex size-11 items-center justify-center rounded-xl border border-border bg-surface-2 text-fg-subtle [&_svg]:size-5">
        {icon}
      </div>
      <div className="max-w-sm space-y-1">
        <p className="text-sm font-medium text-fg">{title}</p>
        {description ? <p className="text-xs leading-relaxed text-fg-muted">{description}</p> : null}
      </div>
      {actions ? <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center gap-3 rounded-xl border border-danger/30 bg-danger-soft px-6 py-8 text-center', className)}
    >
      <AlertTriangle className="size-5 text-danger" aria-hidden />
      <div className="space-y-1">
        <p className="text-sm font-medium text-fg">Não foi possível carregar os dados</p>
        <p className="text-xs text-fg-muted">{errorMessage(error)}</p>
      </div>
      {onRetry ? (
        <Button size="sm" onClick={onRetry}>
          <RotateCw /> Tentar novamente
        </Button>
      ) : null}
    </div>
  );
}

interface SegmentedProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: ReactNode; count?: number }[];
  className?: string;
  label: string;
}

export function Segmented<T extends string>({ value, onChange, options, className, label }: SegmentedProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className={cn('inline-flex rounded-lg border border-border bg-surface-2 p-0.5', className)}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium whitespace-nowrap transition-colors',
              active ? 'bg-surface text-fg shadow-card dark:bg-surface-3' : 'text-fg-muted hover:text-fg',
            )}
          >
            {option.label}
            {option.count !== undefined ? <span className="text-fg-subtle tabular">{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-surface-2 px-1 font-mono text-[10px] text-fg-subtle">
      {children}
    </kbd>
  );
}
