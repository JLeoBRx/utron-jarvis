import { ArrowDown, ArrowUp, CalendarClock, CalendarX2, Equal } from 'lucide-react';
import type { ExamPriority, ExamStatus, TopicStatus } from '@/data/types';
import { daysUntil, formatDate, formatTime, relativeDaysLabel } from '@/lib/dates';
import { EXAM_STATUS_LABELS, PRIORITY_LABELS, TOPIC_STATUS_LABELS } from '@/lib/labels';
import { examUrgency } from '@/lib/progress';
import { cn } from '@/lib/utils';
import { Badge, type BadgeTone } from '../ui/Badge';

export const EXAM_STATUS_TONES: Record<ExamStatus, BadgeTone> = {
  nao_iniciada: 'neutral',
  em_preparacao: 'info',
  em_revisao: 'warning',
  preparacao_concluida: 'success',
  realizada: 'accent',
};

const STATUS_DOT: Record<ExamStatus, string> = {
  nao_iniciada: 'bg-fg-subtle',
  em_preparacao: 'bg-info',
  em_revisao: 'bg-warning',
  preparacao_concluida: 'bg-success',
  realizada: 'bg-accent',
};

export function ExamStatusDot({ status, className }: { status: ExamStatus; className?: string }) {
  return <span className={cn('inline-block size-2 shrink-0 rounded-full', STATUS_DOT[status], className)} aria-hidden />;
}

export function ExamStatusBadge({ status }: { status: ExamStatus }) {
  return (
    <Badge tone={EXAM_STATUS_TONES[status]}>
      <ExamStatusDot status={status} className="size-1.5" />
      {EXAM_STATUS_LABELS[status]}
    </Badge>
  );
}

export function PriorityBadge({ priority, compact }: { priority: ExamPriority; compact?: boolean }) {
  const Icon = priority === 'alta' ? ArrowUp : priority === 'baixa' ? ArrowDown : Equal;
  const tone: BadgeTone = priority === 'alta' ? 'danger' : priority === 'media' ? 'warning' : 'neutral';
  return (
    <Badge tone={tone} title={`Prioridade ${PRIORITY_LABELS[priority].toLowerCase()}`}>
      <Icon aria-hidden />
      {compact ? PRIORITY_LABELS[priority] : `Prioridade ${PRIORITY_LABELS[priority].toLowerCase()}`}
    </Badge>
  );
}

export const TOPIC_STATUS_STYLES: Record<TopicStatus, { dot: string; text: string; tone: BadgeTone }> = {
  nao_estudado: { dot: 'bg-fg-subtle/60', text: 'text-fg-muted', tone: 'neutral' },
  estudando: { dot: 'bg-info', text: 'text-info', tone: 'info' },
  revisado: { dot: 'bg-warning', text: 'text-warning', tone: 'warning' },
  dominado: { dot: 'bg-success', text: 'text-success', tone: 'success' },
};

export function TopicStatusBadge({ status }: { status: TopicStatus }) {
  return <Badge tone={TOPIC_STATUS_STYLES[status].tone}>{TOPIC_STATUS_LABELS[status]}</Badge>;
}

/** Data da prova com indicação relativa ("Em 3 dias") e cor de urgência. */
export function ExamDate({
  date,
  time,
  realizada,
  className,
}: {
  date: string | null;
  time?: string | null;
  realizada?: boolean;
  className?: string;
}) {
  if (!date) {
    return (
      <span className={cn('inline-flex items-center gap-1.5 text-xs text-fg-subtle', className)}>
        <CalendarX2 className="size-3.5" aria-hidden />
        Data não definida
      </span>
    );
  }
  const urgency = examUrgency({ exam_date: date });
  const days = daysUntil(date);
  const color = realizada
    ? 'text-fg-muted'
    : urgency === 'hoje' || urgency === 'urgente'
      ? 'text-danger'
      : urgency === 'proxima'
        ? 'text-warning'
        : 'text-fg-muted';
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs tabular', className)}>
      <CalendarClock className="size-3.5 text-fg-subtle" aria-hidden />
      <span className="text-fg">
        {formatDate(date)}
        {time ? ` · ${formatTime(time)}` : ''}
      </span>
      {!realizada ? <span className={cn('font-medium', color)}>{relativeDaysLabel(days)}</span> : null}
    </span>
  );
}
