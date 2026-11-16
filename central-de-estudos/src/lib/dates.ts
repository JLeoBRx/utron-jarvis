import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';

const DAY_MS = 24 * 60 * 60 * 1000;

/** Data de hoje no fuso LOCAL, formato `YYYY-MM-DD`. */
export function todayISO(now: Date = new Date()): string {
  return format(now, 'yyyy-MM-dd');
}

/** Converte `YYYY-MM-DD` em Date à meia-noite local (sem deslocamento de fuso). */
export function parseISODate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y!, (m ?? 1) - 1, d ?? 1);
}

export function isValidISODate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = parseISODate(value);
  return isValid(date) && format(date, 'yyyy-MM-dd') === value;
}

/** Diferença em dias de calendário entre hoje e a data (negativo = passado). */
export function daysUntil(value: string, now: Date = new Date()): number {
  const target = parseISODate(value);
  const today = parseISODate(todayISO(now));
  return Math.round((target.getTime() - today.getTime()) / DAY_MS);
}

export function relativeDaysLabel(days: number): string {
  if (days === 0) return 'Hoje';
  if (days === 1) return 'Amanhã';
  if (days === -1) return 'Ontem';
  if (days > 1) return `Em ${days} dias`;
  return `Há ${Math.abs(days)} dias`;
}

export function formatDate(value: string | null | undefined, pattern = 'dd/MM/yyyy'): string {
  if (!value) return '';
  const date = value.length === 10 ? parseISODate(value) : parseISO(value);
  return isValid(date) ? format(date, pattern, { locale: ptBR }) : '';
}

export function formatLongDate(value: string): string {
  return formatDate(value, "EEEE, d 'de' MMMM 'de' yyyy");
}

export function formatShortDate(value: string): string {
  return formatDate(value, "d 'de' MMM");
}

/** `HH:MM:SS` → `HH:MM`. */
export function formatTime(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : '';
}

/** `HH:MM` → `HH:MM:00` (formato do PostgreSQL). */
export function normalizeTime(value: string | null | undefined): string | null {
  if (!value) return null;
  return /^\d{2}:\d{2}$/.test(value) ? `${value}:00` : value;
}

export function timeAgo(value: string, now: Date = new Date()): string {
  const date = parseISO(value);
  if (!isValid(date)) return '';
  if (now.getTime() - date.getTime() < 60_000) return 'agora mesmo';
  return `há ${formatDistanceToNowStrict(date, { locale: ptBR })}`;
}

export function greeting(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 5) return 'Boa noite';
  if (h < 12) return 'Bom dia';
  if (h < 18) return 'Boa tarde';
  return 'Boa noite';
}
