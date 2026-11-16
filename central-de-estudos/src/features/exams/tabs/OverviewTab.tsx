import { ArrowRight, CheckCircle2, Circle, ListChecks } from 'lucide-react';
import { Link } from 'react-router';
import { ExamStatusBadge, PriorityBadge, TOPIC_STATUS_STYLES } from '@/components/domain/badges';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/misc';
import { ProgressRing } from '@/components/ui/Progress';
import type { Exam, ExamTopic, Subject } from '@/data/types';
import { daysUntil, formatLongDate, formatTime, relativeDaysLabel } from '@/lib/dates';
import { TOPIC_STATUS_LABELS, TOPIC_STATUS_ORDER } from '@/lib/labels';
import { topicsProgress } from '@/lib/progress';
import { capitalize, cn, pluralize } from '@/lib/utils';

interface Step {
  label: string;
  done: boolean;
  hint?: string;
  to?: string;
}

/** Próximos passos calculados a partir dos dados reais da prova. */
function buildSteps(exam: Exam, topics: ExamTopic[]): Step[] {
  const topicsUrl = `/provas/${exam.id}/conteudos`;
  const progress = topicsProgress(topics);
  const allStarted = topics.length > 0 && progress.byStatus.nao_estudado === 0;
  const allReviewed = topics.length > 0 && topics.every((t) => t.status === 'revisado' || t.status === 'dominado');
  const allMastered = topics.length > 0 && progress.byStatus.dominado === topics.length;
  return [
    { label: 'Definir a data da avaliação', done: Boolean(exam.exam_date), hint: 'Edite a prova para informar a data.' },
    {
      label: 'Cadastrar os conteúdos cobrados',
      done: topics.length > 0,
      hint: 'Liste os assuntos informados pelo professor.',
      to: topicsUrl,
    },
    {
      label: 'Começar a estudar todos os conteúdos',
      done: allStarted,
      hint: topics.length ? `${pluralize(progress.byStatus.nao_estudado, 'conteúdo ainda não estudado', 'conteúdos ainda não estudados')}.` : undefined,
      to: topicsUrl,
    },
    {
      label: 'Revisar todos os conteúdos',
      done: allReviewed,
      to: topicsUrl,
    },
    {
      label: 'Dominar todos os conteúdos',
      done: allMastered,
      hint: allMastered && exam.status !== 'preparacao_concluida' && exam.status !== 'realizada'
        ? 'Tudo dominado: considere marcar a preparação como concluída.'
        : undefined,
      to: topicsUrl,
    },
  ];
}

export function OverviewTab({ exam, subject, topics }: { exam: Exam; subject?: Subject; topics: ExamTopic[] }) {
  const progress = topicsProgress(topics);
  const steps = buildSteps(exam, topics);
  const teacher = exam.teacher ?? subject?.teacher ?? null;
  const topicsUrl = `/provas/${exam.id}/conteudos`;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex flex-col gap-6">
        <Card className="animate-rise">
          <CardHeader title="Preparação" description="Baseada no status de estudo de cada conteúdo cadastrado." />
          <div className="flex flex-col gap-5 px-4 pb-5 sm:flex-row sm:items-center sm:px-5">
            <ProgressRing value={progress.value} size={92} stroke={7} label="Preparação" />
            {progress.total ? (
              <div className="flex-1 space-y-2.5">
                <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-3" aria-hidden>
                  {TOPIC_STATUS_ORDER.map((status) =>
                    progress.byStatus[status] ? (
                      <span
                        key={status}
                        className={cn('h-full', TOPIC_STATUS_STYLES[status].dot)}
                        style={{ width: `${(progress.byStatus[status] / progress.total) * 100}%` }}
                      />
                    ) : null,
                  )}
                </div>
                <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
                  {TOPIC_STATUS_ORDER.map((status) => (
                    <li key={status} className="text-xs">
                      <span className="flex items-center gap-1.5 text-fg-subtle">
                        <span className={cn('size-1.5 rounded-full', TOPIC_STATUS_STYLES[status].dot)} aria-hidden />
                        {TOPIC_STATUS_LABELS[status]}
                      </span>
                      <span className="text-sm font-semibold text-fg tabular">{progress.byStatus[status]}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="flex-1 text-sm text-fg-muted">
                Nenhum conteúdo cadastrado ainda.{' '}
                <Link to={topicsUrl} className="font-medium text-accent-text hover:underline">
                  Cadastrar conteúdos
                </Link>
              </p>
            )}
          </div>
        </Card>

        <Card className="animate-rise">
          <CardHeader
            title="Conteúdos cobrados"
            description={topics.length ? pluralize(topics.length, 'conteúdo', 'conteúdos') : undefined}
            actions={
              <Link to={topicsUrl} className="inline-flex items-center gap-1 text-xs font-medium text-accent-text hover:underline">
                {topics.length ? 'Gerenciar' : 'Adicionar'} <ArrowRight className="size-3.5" />
              </Link>
            }
          />
          {topics.length ? (
            <ul className="divide-y divide-border border-t border-border">
              {topics.slice(0, 8).map((topic) => (
                <li key={topic.id} className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
                  <span className="min-w-0 truncate text-[13px] text-fg">{topic.title}</span>
                  <span className={cn('flex shrink-0 items-center gap-1.5 text-xs', TOPIC_STATUS_STYLES[topic.status].text)}>
                    <span className={cn('size-1.5 rounded-full', TOPIC_STATUS_STYLES[topic.status].dot)} aria-hidden />
                    {TOPIC_STATUS_LABELS[topic.status]}
                  </span>
                </li>
              ))}
              {topics.length > 8 ? (
                <li className="px-4 py-2.5 text-xs text-fg-subtle sm:px-5">
                  <Link to={topicsUrl} className="hover:text-fg">
                    + {pluralize(topics.length - 8, 'outro conteúdo', 'outros conteúdos')}
                  </Link>
                </li>
              ) : null}
            </ul>
          ) : (
            <EmptyState compact icon={<ListChecks />} title="Sem conteúdos" description="Os assuntos desta avaliação aparecerão aqui." />
          )}
        </Card>
      </div>

      <div className="flex flex-col gap-6">
        <Card className="animate-rise">
          <CardHeader title="Detalhes" />
          <dl className="space-y-3 px-4 pb-4 text-xs sm:px-5">
            <div>
              <dt className="text-fg-subtle">Data</dt>
              <dd className="mt-0.5 text-fg">
                {exam.exam_date ? (
                  <>
                    {capitalize(formatLongDate(exam.exam_date))}
                    {exam.exam_time ? `, às ${formatTime(exam.exam_time)}` : ''}
                    {exam.status !== 'realizada' ? (
                      <span className="ml-1.5 text-fg-muted">({relativeDaysLabel(daysUntil(exam.exam_date)).toLowerCase()})</span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-fg-subtle">Ainda não definida</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-fg-subtle">Professor(a)</dt>
              <dd className="mt-0.5 text-fg">
                {teacher ?? <span className="text-fg-subtle">Não informado(a)</span>}
                {!exam.teacher && subject?.teacher ? <span className="text-fg-subtle"> · da disciplina</span> : null}
              </dd>
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              <ExamStatusBadge status={exam.status} />
              <PriorityBadge priority={exam.priority} />
            </div>
            {exam.score !== null ? (
              <div>
                <dt className="text-fg-subtle">Nota</dt>
                <dd className="mt-0.5 text-base font-semibold text-fg tabular">
                  {exam.score.toLocaleString('pt-BR')}
                  {exam.max_score !== null ? <span className="text-sm font-normal text-fg-muted"> / {exam.max_score.toLocaleString('pt-BR')}</span> : null}
                </dd>
              </div>
            ) : null}
            {exam.description ? (
              <div>
                <dt className="text-fg-subtle">Descrição</dt>
                <dd className="mt-0.5 leading-relaxed whitespace-pre-line text-fg-muted">{exam.description}</dd>
              </div>
            ) : null}
          </dl>
        </Card>

        <Card className="animate-rise">
          <CardHeader title="Próximos passos" />
          <ul className="space-y-2.5 px-4 pb-4 sm:px-5">
            {steps.map((step) => (
              <li key={step.label} className="flex gap-2.5 text-xs">
                {step.done ? (
                  <CheckCircle2 className="mt-px size-4 shrink-0 text-success" aria-label="Concluído" />
                ) : (
                  <Circle className="mt-px size-4 shrink-0 text-fg-subtle" aria-label="Pendente" />
                )}
                <span>
                  {step.to && !step.done ? (
                    <Link to={step.to} className="font-medium text-fg hover:text-accent-text">
                      {step.label}
                    </Link>
                  ) : (
                    <span className={cn('font-medium', step.done ? 'text-fg-muted line-through decoration-fg-subtle/50' : 'text-fg')}>
                      {step.label}
                    </span>
                  )}
                  {step.hint && !step.done ? <span className="mt-0.5 block text-fg-subtle">{step.hint}</span> : null}
                  {step.hint && step.done && step.label.startsWith('Dominar') ? (
                    <span className="mt-0.5 block text-success">{step.hint}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
