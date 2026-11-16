import { useId } from 'react';
import { cn } from '@/lib/utils';

/** Marca da Central de Estudos: um "C" aberto em torno de um núcleo (o ponto central). */
export function LogoMark({ size = 28, className }: { size?: number; className?: string }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={cn('shrink-0', className)} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8f8aff" />
          <stop offset="1" stopColor="#4f46e5" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${id})`} />
      <path d="M21.6 10.4A7.9 7.9 0 1 0 21.6 21.6" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="16" cy="16" r="2.7" fill="#fff" />
    </svg>
  );
}

export function Logo({ collapsed, className }: { collapsed?: boolean; className?: string }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <LogoMark />
      {!collapsed ? (
        <span className="flex flex-col leading-none">
          <span className="text-[13px] font-semibold tracking-tight text-fg">Central de Estudos</span>
        </span>
      ) : null}
    </span>
  );
}
