import {
  ArrowRight,
  BookOpen,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Clock,
  FilePlus2,
  FileText,
  FolderOpen,
  HardDrive,
  Info,
  Layers,
  NotebookPen,
  Plus,
  Timer,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { ExamDate, ExamStatusBadge, PriorityBadge } from '@/components/domain/badges';
import { SubjectTag } from '@/components/domain/SubjectTag';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/misc';
import { ProgressBar, ProgressRing } from '@/components/ui/Progress';
import { Tooltip } from '@/components/ui/Tooltip';
import { useBackend } from '@/data/DataContext';
import { useContentCounts, useProfile, useRecentActivity, useYearData } from '@/data/hooks';
import type { ActivityItem } from '@/data/services/activity';
import type { Exam, Subject } from '@/data/types';
import { daysUntil, formatLongDate, greeting, relativeDaysLabel, timeAgo, todayISO } from '@/lib/dates';
import { formatPercent, pendingExamsProgress, topicsProgress, upcomingExams } from '@/lib/progress';
import { subjectColorStyle } from '@/lib/colors';
import { capitalize, cn, pluralize } from '@/lib/utils';
import { ExamFormDialog } from '../exams/ExamFormDialog';

const LOCAL_NOTICE_KEY = 'ce:local-notice-dismissed';

function Stat({
  icon: Icon,
  label,
  value,
  detail,
  to,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  to?: string;
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-fg-muted">{label}</span>
        <Icon className="size-4 text-fg-subtle" aria-hidden />
      </div>
      <div className="mt-2.5 text-2xl font-semibold tracking-tight text-fg tabular">{value}</div>
      {detail ? <div className="mt-1 truncate text-xs text-fg-subtle">{detail}</div> : null}
    </>
  );
  const classes = 'block rounded-xl border border-border bg-surface p-4 shadow-card transition-colors';
  return to ? (
    <Link to={to} className={cn(classes, 'hover:border-border-strong')}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}

function UpcomingExamCard({ exam, subject, topicsCount, progress }: { exam: Exam; subject?: Subject; topicsCount: number; progress: number | null }) {
  return (
    <Link
      to={`/provas/${exam.id}`}
      style={subjectColorStyle(subject?.color)}
      className="sc group relative flex flex-col gap-3 overflow-hidden rounded-xl border border-border bg-surface p-4 transition-colors hover:border-border-strong"
    >
      <span className="sc-bg absolute inset-y-0 left-0 w-0.5 opacity-70" aria-hidden />
      <div className="flex items-start justify-between gap-2">
        <SubjectTag subject={subject} className="text-[11px]" />
        <PriorityBadge priority={exam.priority} compact />
      </div>
      <div>
        <p className="truncate text-sm font-semibold text-fg group-hover:text-accent-text">{exam.title}</p>
        <ExamDate date={exam.exam_date} time={exam.exam_time} className="mt-1" />
      </div>
      <div className="mt-auto space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-fg-muted">{topicsCount ? pluralize(topicsCount, 'conteúdo', 'conteúdos') : 'Sem conteúdos'}</span>
          <span className="font-medium text-fg tabular">{formatPercent(progress)}</span>
        </div>
        <ProgressBar value={progress} subjectColor label={`Preparação para ${exam.title}`} />
        <ExamStatusBadge status={exam.status} />
      </div>
    </Link>
  );
}

const ACTIVITY_ICONS: Record<ActivityItem['kind'], LucideIcon> = {
  material: FolderOpen,
  resumo: FileText,
  simulado: Timer,
  sessao: Clock,
  prova: ClipboardCheck,
};

function ActivityList({ items, subjects }: { items: ActivityItem[]; subjects: Map<string, Subject> }) {
  return (
    <ul className="divide-y divide-border">
      {items.map((item) => {
        const Icon = ACTIVITY_ICONS[item.kind];
        const subject = item.subjectId ? subjects.get(item.subjectId) : undefined;
        const href = item.examId ? `/provas/${item.examId}` : item.subjectId ? `/disciplinas/${item.subjectId}` : undefined;
        const content = (
          <>
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-fg-subtle">
              <Icon className="size-3.5" aria-hidden />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] text-fg">{item.title}</span>
              {subject ? <SubjectTag subject={subject} className="mt-0.5 flex max-w-full text-[11px] font-normal" /> : null}
              <span className="mt-0.5 block truncate text-[11px] text-fg-subtle">
                {item.detail ? `${item.detail} · ` : ''}
                {timeAgo(item.at)}
              </span>
            </span>
          </>
        );
        return (
          <li key={item.id}>
            {href ? (
              <Link to={href} className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-2/60 sm:px-5">
                {content}
              </Link>
            ) : (
              <div className="flex items-center gap-3 px-4 py-2.5 sm:px-5">{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function QuickAction({
  icon: Icon,
  label,
  onClick,
  phase,
}: {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  phase?: number;
}) {
  const disabled = !onClick;
  const button = (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      className={cn(
        'flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left text-[13px] transition-colors',
        disabled ? 'cursor-not-allowed text-fg-subtle' : 'text-fg hover:border-border-strong hover:bg-surface-2',
      )}
    >
      <Icon className={cn('size-4 shrink-0', disabled ? 'text-fg-subtle' : 'text-accent-text')} aria-hidden />
      <span className="flex-1 truncate font-medium">{label}</span>
      {phase ? (
        <span className="text-[10px] text-fg-subtle">Fase {phase}</span>
      ) : (
        <ArrowRight className="size-3.5 text-fg-subtle" aria-hidden />
      )}
    </button>
  );
  return phase ? (
    <Tooltip content={`Disponível quando o módulo for entregue (Fase ${phase}).`}>
      <span className="block">{button}</span>
    </Tooltip>
  ) : (
    button
  );
}

function LocalModeNotice() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(LOCAL_NOTICE_KEY) === '1';
    } catch {
      return false;
    }
  });
  if (dismissed) return null;
  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(LOCAL_NOTICE_KEY, '1');
    } catch {
      /* ignora */
    }
  };
  return (
    <div className="mb-6 flex animate-rise items-start gap-3 rounded-xl border border-warning/25 bg-warning-soft px-4 py-3 text-xs leading-relaxed">
      <HardDrive className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <p className="flex-1 text-fg-muted">
        <strong className="font-medium text-fg">Modo local ativo.</strong> Seus dados estão salvos apenas neste navegador. Faça
        backups em{' '}
        <Link to="/configuracoes#dados" className="font-medium text-fg underline-offset-2 hover:underline">
          Configurações
        </Link>{' '}
        ou configure o Supabase para sincronizar com segurança.
      </p>
      <button type="button" onClick={dismiss} className="rounded p-0.5 text-fg-subtle hover:text-fg" aria-label="Dispensar aviso">
        <X className="size-4" />
      </button>
    </div>
  );
}

export function DashboardPage() {
  const db = useBackend();
  const profile = useProfile();
  const { activeYear, subjects, subjectById, exams, topicsByExam, isLoading, error, refetch } = useYearData();
  const activeSubjects = useMemo(() => subjects.filter((s) => !s.archived_at), [subjects]);
  const subjectIds = useMemo(() => subjects.map((s) => s.id), [subjects]);
  const counts = useContentCounts(subjectIds);
  const activity = useRecentActivity(subjectIds);
  const [examDialog, setExamDialog] = useState(false);

  const upcoming = useMemo(() => upcomingExams(exams), [exams]);
  const overall = useMemo(() => pendingExamsProgress(exams, topicsByExam), [exams, topicsByExam]);
  const withoutDate = exams.filter((e) => !e.exam_date && e.status !== 'realizada').length;
  const doneExams = exams.filter((e) => e.status === 'realizada').length;

  const subjectProgress = useMemo(
    () =>
      activeSubjects
        .map((subject) => {
          const subjectExams = exams.filter((e) => e.subject_id === subject.id);
          return { subject, exams: subjectExams, progress: pendingExamsProgress(subjectExams, topicsByExam) };
        })
        .filter((row) => row.exams.some((e) => e.status !== 'realizada'))
        .sort((a, b) => (a.progress.value ?? -1) - (b.progress.value ?? -1)),
    [activeSubjects, exams, topicsByExam],
  );

  const name = profile.data?.display_name;
  const today = todayISO();
  const next = upcoming[0];

  if (error) return <ErrorState error={error} onRetry={refetch} />;

  return (
    <>
      <PageHeader
        title={`${greeting()}${name ? `, ${name}` : ''}`}
        description={`${capitalize(formatLongDate(today))}${activeYear ? ` · Ano letivo ${activeYear.name}` : ''}`}
        actions={
          <Button variant="primary" onClick={() => setExamDialog(true)} disabled={!activeSubjects.length}>
            <Plus /> Nova prova
          </Button>
        }
      />

      {db.mode === 'local' ? <LocalModeNotice /> : null}

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-[104px] rounded-xl" />
          ))}
        </div>
      ) : (
        <section aria-label="Indicadores" className="grid animate-rise grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            icon={BookOpen}
            label="Disciplinas"
            value={activeSubjects.length}
            detail={`${activeSubjects.filter((s) => s.category === 'formacao_geral').length} gerais · ${activeSubjects.filter((s) => s.category === 'formacao_tecnica').length} técnicas`}
            to="/disciplinas"
          />
          <Stat
            icon={ClipboardCheck}
            label="Provas cadastradas"
            value={exams.length}
            detail={exams.length ? `${doneExams} ${doneExams === 1 ? 'realizada' : 'realizadas'}` : 'Nenhuma ainda'}
            to="/provas"
          />
          <Stat
            icon={ClipboardList}
            label="Próximas avaliações"
            value={upcoming.length}
            detail={
              next
                ? `${subjectById.get(next.subject_id)?.name ?? ''} · ${relativeDaysLabel(daysUntil(next.exam_date!)).toLowerCase()}`
                : withoutDate
                  ? `${withoutDate} sem data definida`
                  : 'Nenhuma com data futura'
            }
            to="/provas"
          />
          <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-fg-muted">Progresso geral</span>
              <Tooltip content="Média do status de estudo dos conteúdos das provas pendentes (não estudado, estudando, revisado, dominado).">
                <button type="button" className="rounded text-fg-subtle hover:text-fg" aria-label="Como o progresso geral é calculado">
                  <Info className="size-4" />
                </button>
              </Tooltip>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <ProgressRing value={overall.value} size={48} stroke={4.5} label="Progresso geral" />
              <span className="text-xs text-fg-subtle">
                {overall.total ? `${overall.byStatus.dominado} de ${overall.total} conteúdos dominados` : 'Cadastre os conteúdos das provas'}
              </span>
            </div>
          </div>
          <Stat icon={FileText} label="Resumos disponíveis" value={counts.data?.summaries ?? 0} detail="Módulo de resumos · Fase 4" />
          <Stat
            icon={CheckCircle2}
            label="Resumos concluídos"
            value={counts.data?.summariesDone ?? 0}
            detail={`de ${counts.data?.summaries ?? 0} resumos`}
          />
          <Stat icon={FolderOpen} label="Materiais armazenados" value={counts.data?.materials ?? 0} detail="Biblioteca · Fase 3" />
          <Stat icon={Layers} label="Flashcards disponíveis" value={counts.data?.flashcards ?? 0} detail="Flashcards · Fase 5" />
        </section>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <Card className="animate-rise">
          <CardHeader
            title="Próximas provas"
            description={upcoming.length ? `${pluralize(upcoming.length, 'avaliação', 'avaliações')} pela frente` : undefined}
            actions={
              exams.length ? (
                <ButtonLink to="/provas" variant="ghost" size="sm">
                  Ver todas <ArrowRight />
                </ButtonLink>
              ) : null
            }
          />
          <div className="px-4 pb-4 sm:px-5 sm:pb-5">
            {isLoading ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Skeleton className="h-40 rounded-xl" />
                <Skeleton className="h-40 rounded-xl" />
              </div>
            ) : upcoming.length ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {upcoming.slice(0, 6).map((exam) => {
                  const topics = topicsByExam.get(exam.id) ?? [];
                  return (
                    <UpcomingExamCard
                      key={exam.id}
                      exam={exam}
                      subject={subjectById.get(exam.subject_id)}
                      topicsCount={topics.length}
                      progress={topicsProgress(topics).value}
                    />
                  );
                })}
              </div>
            ) : (
              <EmptyState
                compact
                icon={<ClipboardCheck />}
                title={exams.length ? 'Nenhuma prova com data futura' : 'Você ainda não cadastrou provas'}
                description={
                  exams.length
                    ? withoutDate
                      ? `${pluralize(withoutDate, 'prova está', 'provas estão')} sem data definida. Informe a data para acompanhar a contagem regressiva.`
                      : 'Quando houver avaliações agendadas, elas aparecerão aqui.'
                    : 'Cadastre a primeira avaliação para começar a organizar sua preparação.'
                }
                actions={
                  activeSubjects.length ? (
                    <Button size="sm" variant="primary" onClick={() => setExamDialog(true)}>
                      <Plus /> Cadastrar prova
                    </Button>
                  ) : null
                }
              />
            )}
          </div>
        </Card>

        <div className="flex flex-col gap-6">
          <Card className="animate-rise">
            <CardHeader title="Acesso rápido" />
            <div className="grid gap-2 px-4 pb-4 sm:px-5 sm:pb-5">
              <QuickAction icon={ClipboardCheck} label="Cadastrar prova" onClick={activeSubjects.length ? () => setExamDialog(true) : undefined} />
              <QuickAction icon={FilePlus2} label="Adicionar material" phase={3} />
              <QuickAction icon={NotebookPen} label="Criar resumo" phase={4} />
              <QuickAction icon={Timer} label="Iniciar simulado" phase={5} />
            </div>
          </Card>

          <div className="relative animate-rise overflow-hidden rounded-xl border border-accent/25 bg-accent-soft p-4">
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-fg">
                <Camera className="size-4.5" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-fg">Fotografar meu caderno</p>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                  Transforme fotos das páginas do caderno em resumos organizados. A captura chega na Fase 3 e a leitura por IA, na
                  Fase 7.
                </p>
                <Badge tone="accent" className="mt-2.5">
                  <Clock aria-hidden /> Em desenvolvimento
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="animate-rise">
          <CardHeader
            title="Preparação por disciplina"
            description="Disciplinas com provas pendentes — as menos preparadas primeiro."
          />
          {subjectProgress.length ? (
            <ul className="divide-y divide-border border-t border-border">
              {subjectProgress.slice(0, 8).map(({ subject, exams: list, progress }) => (
                <li key={subject.id}>
                  <Link
                    to={`/disciplinas/${subject.id}`}
                    style={subjectColorStyle(subject.color)}
                    className="sc grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-3 transition-colors hover:bg-surface-2/60 sm:grid-cols-[minmax(0,1fr)_160px_48px] sm:px-5"
                  >
                    <span className="min-w-0">
                      <SubjectTag subject={subject} className="text-[13px] text-fg" />
                      <span className="mt-0.5 block text-[11px] text-fg-subtle">
                        {pluralize(list.filter((e) => e.status !== 'realizada').length, 'prova pendente', 'provas pendentes')} ·{' '}
                        {pluralize(progress.total, 'conteúdo', 'conteúdos')}
                      </span>
                    </span>
                    <span className="text-right text-xs font-medium text-fg tabular sm:order-last">{formatPercent(progress.value)}</span>
                    <ProgressBar value={progress.value} subjectColor className="col-span-2 sm:col-span-1" label={`Preparação em ${subject.name}`} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              compact
              icon={<BookOpen />}
              title="Nenhuma disciplina com provas pendentes"
              description="Cadastre provas e seus conteúdos para acompanhar a preparação de cada disciplina."
            />
          )}
        </Card>

        <Card className="animate-rise">
          <CardHeader title="Atividades recentes" />
          {activity.data?.length ? (
            <div className="border-t border-border">
              <ActivityList items={activity.data} subjects={subjectById} />
            </div>
          ) : (
            <EmptyState
              compact
              icon={<Clock />}
              title="Nada por aqui ainda"
              description="Materiais enviados, resumos atualizados, simulados e sessões de estudo aparecerão aqui."
            />
          )}
        </Card>
      </div>

      <ExamFormDialog open={examDialog} onOpenChange={setExamDialog} subjects={subjects} />
    </>
  );
}
