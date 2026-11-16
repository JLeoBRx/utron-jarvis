import { Layers, Timer } from 'lucide-react';
import { TOPIC_STATUS_STYLES } from '@/components/domain/badges';
import { Card, CardHeader } from '@/components/ui/Card';
import type { Exam, ExamTopic } from '@/data/types';
import { TOPIC_STATUS_LABELS, TOPIC_STATUS_ORDER } from '@/lib/labels';
import { formatPercent, topicsProgress } from '@/lib/progress';
import { cn } from '@/lib/utils';

export function PerformanceTab({ exam, topics }: { exam: Exam; topics: ExamTopic[] }) {
  const progress = topicsProgress(topics);
  const pending = topics.filter((t) => t.status === 'nao_estudado' || t.status === 'estudando');
  const scorePct = exam.score !== null && exam.max_score ? exam.score / exam.max_score : null;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="animate-rise">
        <CardHeader title="Domínio dos conteúdos" description="Registrado por você em cada conteúdo." />
        <div className="space-y-3 px-4 pb-5 sm:px-5">
          {TOPIC_STATUS_ORDER.map((status) => {
            const n = progress.byStatus[status];
            const pct = progress.total ? n / progress.total : 0;
            return (
              <div key={status}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-fg-muted">{TOPIC_STATUS_LABELS[status]}</span>
                  <span className="text-fg tabular">
                    {n} <span className="text-fg-subtle">· {Math.round(pct * 100)}%</span>
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                  <div className={cn('h-full rounded-full', TOPIC_STATUS_STYLES[status].dot)} style={{ width: `${pct * 100}%` }} />
                </div>
              </div>
            );
          })}
          <p className="pt-1 text-xs text-fg-subtle">Preparação geral: {formatPercent(progress.value)}</p>
        </div>
      </Card>

      <Card className="animate-rise">
        <CardHeader title="Conteúdos que precisam de atenção" description="Não estudados ou ainda em estudo." />
        {pending.length ? (
          <ul className="divide-y divide-border border-t border-border">
            {pending.map((topic) => (
              <li key={topic.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px] sm:px-5">
                <span className="min-w-0 truncate text-fg">{topic.title}</span>
                <span className={cn('shrink-0 text-xs', TOPIC_STATUS_STYLES[topic.status].text)}>{TOPIC_STATUS_LABELS[topic.status]}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 pb-5 text-xs text-fg-muted sm:px-5">
            {topics.length ? 'Todos os conteúdos já foram revisados ou dominados.' : 'Cadastre os conteúdos da prova para acompanhar.'}
          </p>
        )}
      </Card>

      {scorePct !== null ? (
        <Card className="animate-rise p-4 sm:p-5">
          <p className="text-xs font-medium text-fg-muted">Nota na avaliação</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight text-fg tabular">
            {exam.score!.toLocaleString('pt-BR')}
            <span className="text-base font-normal text-fg-muted"> / {exam.max_score!.toLocaleString('pt-BR')}</span>
          </p>
          <p className="mt-1 text-xs text-fg-subtle">{Math.round(scorePct * 100)}% de aproveitamento</p>
        </Card>
      ) : null}

      <Card className="animate-rise p-4 sm:p-5 lg:col-span-2">
        <div className="flex items-start gap-3 text-xs leading-relaxed text-fg-muted">
          <span className="flex gap-1.5 text-fg-subtle">
            <Timer className="size-4" aria-hidden />
            <Layers className="size-4" aria-hidden />
          </span>
          <p>
            Aproveitamento em simulados, evolução das notas e flashcards dominados passam a compor este painel na{' '}
            <strong className="font-medium text-fg">Fase 5</strong>, quando esses módulos forem entregues.
          </p>
        </div>
      </Card>
    </div>
  );
}
