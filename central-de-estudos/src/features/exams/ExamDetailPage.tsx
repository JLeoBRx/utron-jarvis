import { useQuery } from '@tanstack/react-query';
import {
  BarChart3,
  ChevronDown,
  FileText,
  FolderOpen,
  Info,
  Layers,
  ListChecks,
  MoreHorizontal,
  Pencil,
  PencilLine,
  Timer,
  Trash2,
} from 'lucide-react';
import { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router';
import { ExamDate, ExamStatusDot, PriorityBadge } from '@/components/domain/badges';
import { SubjectTag } from '@/components/domain/SubjectTag';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { ErrorState, Skeleton, Spinner } from '@/components/ui/misc';
import { TabNav } from '@/components/ui/TabNav';
import { useBackend } from '@/data/DataContext';
import { useAction, useExamCounts, useYearData } from '@/data/hooks';
import { deleteExam, getExamDeletionImpact, setExamStatus } from '@/data/services/exams';
import type { Exam, ExamStatus } from '@/data/types';
import { subjectColorStyle } from '@/lib/colors';
import { EXAM_STATUS_LABELS, EXAM_STATUS_ORDER } from '@/lib/labels';
import { pluralize } from '@/lib/utils';
import { NotFoundPage } from '../modules/NotFoundPage';
import { ExamFormDialog } from './ExamFormDialog';
import { MaterialsTab } from './tabs/MaterialsTab';
import { ModuleTab } from './tabs/ModuleTab';
import { OverviewTab } from './tabs/OverviewTab';
import { PerformanceTab } from './tabs/PerformanceTab';
import { TopicsTab } from './tabs/TopicsTab';

const TABS = ['visao-geral', 'conteudos', 'materiais', 'resumo', 'flashcards', 'exercicios', 'simulado', 'desempenho'] as const;
type Tab = (typeof TABS)[number];

function StatusMenu({ exam }: { exam: Exam }) {
  const change = useAction((db, status: ExamStatus) => setExamStatus(db, exam.id, status), {
    success: (e) => `Status: ${EXAM_STATUS_LABELS[e.status]}.`,
  });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="inline-flex h-8.5 items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 text-sm font-medium text-fg transition-colors hover:border-border-strong">
        <ExamStatusDot status={exam.status} />
        {EXAM_STATUS_LABELS[exam.status]}
        <ChevronDown className="size-3.5 text-fg-subtle" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56">
        <DropdownMenuLabel>Status da prova</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={exam.status} onValueChange={(value) => change.mutate(value as ExamStatus)}>
          {EXAM_STATUS_ORDER.map((status) => (
            <DropdownMenuRadioItem key={status} value={status}>
              {EXAM_STATUS_LABELS[status]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DeleteExamDialog({ exam, open, onOpenChange }: { exam: Exam; open: boolean; onOpenChange: (open: boolean) => void }) {
  const db = useBackend();
  const navigate = useNavigate();
  const impact = useQuery({
    queryKey: [db.mode, db.userId, 'exam-impact', exam.id],
    queryFn: () => getExamDeletionImpact(db, exam.id),
    enabled: open,
    staleTime: 0,
  });
  const remove = useAction((backend) => deleteExam(backend, exam.id), {
    success: 'Prova excluída.',
    onSuccess: () => navigate(`/disciplinas/${exam.subject_id}`, { replace: true }),
  });
  const data = impact.data;
  const deleted = data
    ? [
        data.topics && pluralize(data.topics, 'conteúdo', 'conteúdos'),
        data.flashcards && pluralize(data.flashcards, 'flashcard', 'flashcards'),
        data.questions && pluralize(data.questions, 'questão', 'questões'),
        data.quizzes && pluralize(data.quizzes, 'simulado', 'simulados'),
        data.events && pluralize(data.events, 'evento do calendário', 'eventos do calendário'),
      ].filter(Boolean)
    : [];
  const preserved = data
    ? [data.materials && pluralize(data.materials, 'material', 'materiais'), data.summaries && pluralize(data.summaries, 'resumo', 'resumos')].filter(
        Boolean,
      )
    : [];

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Excluir "${exam.title}"?`}
      description="Esta ação não pode ser desfeita."
      confirmLabel="Excluir prova"
      requireText={deleted.length ? exam.title : undefined}
      loading={remove.isPending}
      onConfirm={() => remove.mutate(undefined)}
    >
      {impact.isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-2 text-xs">
          {deleted.length ? (
            <div className="rounded-lg border border-danger/25 bg-danger-soft p-3 text-fg-muted">
              <p className="mb-1 font-medium text-danger">Serão apagados junto com a prova:</p>
              <ul className="list-disc space-y-0.5 pl-4">
                {deleted.map((line) => (
                  <li key={String(line)}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {preserved.length ? (
            <div className="rounded-lg border border-border bg-surface-2 p-3 text-fg-muted">
              <p className="mb-1 font-medium text-fg">Serão preservados na disciplina:</p>
              <ul className="list-disc space-y-0.5 pl-4">
                {preserved.map((line) => (
                  <li key={String(line)}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {!deleted.length && !preserved.length ? <p className="text-fg-muted">A prova não possui itens vinculados.</p> : null}
        </div>
      )}
    </ConfirmDialog>
  );
}

export function ExamDetailPage() {
  const { examId, tab: tabParam } = useParams();
  const { subjects, subjectById, exams, topicsByExam, isLoading, error, refetch } = useYearData();
  const exam = exams.find((e) => e.id === examId);
  const counts = useExamCounts(exam?.id);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (tabParam && !TABS.includes(tabParam as Tab)) return <Navigate to={`/provas/${examId}`} replace />;
  const tab: Tab = (tabParam as Tab | undefined) ?? 'visao-geral';

  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }
  if (!exam) return <NotFoundPage message="Esta prova não existe no ano letivo ativo." />;

  const subject = subjectById.get(exam.subject_id);
  const topics = topicsByExam.get(exam.id) ?? [];
  const c = counts.data;
  const base = `/provas/${exam.id}`;

  return (
    <div style={subjectColorStyle(subject?.color)} className="sc">
      <PageHeader
        breadcrumbs={[
          { label: 'Disciplinas', to: '/disciplinas' },
          ...(subject ? [{ label: subject.name, to: `/disciplinas/${subject.id}` }] : []),
          { label: exam.title },
        ]}
        eyebrow={
          <div className="flex flex-wrap items-center gap-2">
            <SubjectTag subject={subject} link />
            <PriorityBadge priority={exam.priority} />
          </div>
        }
        title={exam.title}
        description={<ExamDate date={exam.exam_date} time={exam.exam_time} realizada={exam.status === 'realizada'} className="text-sm" />}
        actions={
          <>
            <StatusMenu exam={exam} />
            <Button onClick={() => setEditing(true)}>
              <Pencil /> Editar
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                className="inline-flex size-8.5 items-center justify-center rounded-lg border border-border bg-surface-2 text-fg-muted hover:text-fg"
                aria-label="Mais ações"
              >
                <MoreHorizontal className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem icon={<Trash2 />} danger onSelect={() => setDeleting(true)}>
                  Excluir prova…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      <TabNav
        label="Seções da prova"
        items={[
          { to: base, label: 'Visão geral', icon: Info, end: true },
          { to: `${base}/conteudos`, label: 'Conteúdos', icon: ListChecks, count: topics.length },
          { to: `${base}/materiais`, label: 'Materiais', icon: FolderOpen, count: c?.materials },
          { to: `${base}/resumo`, label: 'Resumo', icon: FileText, count: c?.summaries },
          { to: `${base}/flashcards`, label: 'Flashcards', icon: Layers, count: c?.flashcards },
          { to: `${base}/exercicios`, label: 'Exercícios', icon: PencilLine, count: c?.questions },
          { to: `${base}/simulado`, label: 'Simulado', icon: Timer, count: c?.quizzes },
          { to: `${base}/desempenho`, label: 'Desempenho', icon: BarChart3 },
        ]}
      />

      {tab === 'visao-geral' ? <OverviewTab exam={exam} subject={subject} topics={topics} /> : null}
      {tab === 'conteudos' ? <TopicsTab exam={exam} topics={topics} /> : null}
      {tab === 'materiais' ? <MaterialsTab exam={exam} /> : null}
      {tab === 'resumo' ? (
        <ModuleTab
          icon={FileText}
          title="O resumo desta prova ainda não foi criado."
          description="O resumo será construído a partir dos materiais enviados, com histórico de versões e indicação da origem de cada informação."
          phase={4}
          count={c?.summaries ?? 0}
          noun={['resumo', 'resumos']}
        />
      ) : null}
      {tab === 'flashcards' ? (
        <ModuleTab
          icon={Layers}
          title="Não existem flashcards cadastrados para esta avaliação."
          description="Cartões de revisão com autoavaliação e preparação para repetição espaçada."
          phase={5}
          count={c?.flashcards ?? 0}
          noun={['flashcard', 'flashcards']}
        />
      ) : null}
      {tab === 'exercicios' ? (
        <ModuleTab
          icon={PencilLine}
          title="Nenhum exercício cadastrado para esta prova."
          description="Questões de múltipla escolha, verdadeiro ou falso, discursivas, cálculos e outros formatos, com explicação de cada resposta."
          phase={5}
          count={c?.questions ?? 0}
          noun={['questão', 'questões']}
        />
      ) : null}
      {tab === 'simulado' ? (
        <ModuleTab
          icon={Timer}
          title="Seu primeiro simulado aparecerá aqui."
          description="Simulados com tempo opcional, correção ao final, nota e explicações das respostas."
          phase={5}
          count={c?.quizzes ?? 0}
          noun={['simulado', 'simulados']}
        />
      ) : null}
      {tab === 'desempenho' ? <PerformanceTab exam={exam} topics={topics} /> : null}

      <ExamFormDialog open={editing} onOpenChange={setEditing} subjects={subjects} exam={exam} />
      <DeleteExamDialog exam={exam} open={deleting} onOpenChange={setDeleting} />
    </div>
  );
}
