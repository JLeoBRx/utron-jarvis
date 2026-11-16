import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';

interface ProgressBarProps {
  /** 0–1, ou null (sem dados). */
  value: number | null;
  className?: string;
  /** Usa a cor da disciplina (precisa de um ancestral com `.sc`). */
  subjectColor?: boolean;
  label?: string;
}

export function ProgressBar({ value, className, subjectColor, label }: ProgressBarProps) {
  const pct = value === null ? 0 : Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label ?? 'Progresso'}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value === null ? undefined : pct}
      aria-valuetext={value === null ? 'Sem conteúdos cadastrados' : `${pct}%`}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-surface-3', className)}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-500 ease-out', subjectColor ? 'sc-bg' : 'bg-accent')}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

interface ProgressRingProps {
  value: number | null;
  size?: number;
  stroke?: number;
  className?: string;
  label?: string;
}

export function ProgressRing({ value, size = 56, stroke = 5, className, label }: ProgressRingProps) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = value === null ? 0 : Math.min(1, Math.max(0, value));
  return (
    <div className={cn('relative inline-flex shrink-0', className)} style={{ width: size, height: size } as CSSProperties}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} className="stroke-surface-3" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - pct)}
          className="stroke-accent transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-fg tabular"
        aria-label={label}
      >
        {value === null ? '—' : `${Math.round(pct * 100)}%`}
      </span>
    </div>
  );
}
