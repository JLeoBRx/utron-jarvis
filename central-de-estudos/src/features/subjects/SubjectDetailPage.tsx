import { Archive, ArchiveRestore, BookOpen, Camera, ClipboardCheck, Cpu, FolderOpen, ListChecks, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/misc';
import { ProgressRing } from '@/components/ui/Progress';
import { useAction, useMaterialCounts, useYearData } from '@/data/hooks';
import { setSubjectArchived } from '@/data/services/subjects';
import { subjectColorStyle } from '@/lib/colors';
import { CATEGORY_LABELS } from '@/lib/labels';
import { pendingExamsProgress, sortExamsForDisplay } from '@/lib/progress';
import { pluralize } from '@/lib/utils';
import { NotFoundPage } from '../modules/NotFoundPage';
import { ExamFormDialog } from '../exams/ExamFormDialog';
import { ExamRow } from '../exams/ExamRow';
import { DeleteSubjectDialog } from './SubjectDialogs';
import { SubjectFormDialog } from './SubjectFormDialog';

function MiniStat({ icon: Icon, label, value }: { icon: typeof BookOpen; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-card">
      <Icon className="size-4 text-fg-subtle" aria-hidden />
      <div>
        <p className="text-lg leading-tight font-semibold text-fg tabular">{value}</p>
        <p className="text-[11px] text-fg-subtle">{label}</p>
      </div>
    </div>
  );
}

export function SubjectDetailPage() {
  const { subjectId } = useParams();
  const navigate = useNavigate();
  const { subjects, exams, topicsByExam, isLoading, error, refetch } = useYearData();
  const subject = subjects.find((s) => s.id === subjectId);
  const materialCounts = useMaterialCounts(subject ? [subject.id] : []);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [examDialog, setExamDialog] = useState(false);

  const subjectExams = useMemo(() => sortExamsForDisplay(exams.filter((e) => e.subject_id === subjectId)), [exams, subjectId]);
  const progress = useMemo(() => pendingExamsProgress(subjectExams, topicsByExam), [subjectExams, topicsByExam]);
  const topicCount = subjectExams.reduce((sum, e) => sum + (topicsByExam.get(e.id)?.length ?? 0), 0);

  const archive = useAction((db, archived: boolean) => setSubjectArchived(db, subjectId!, archived), {
    success: (s) => (s.archived_at ? 'Disciplina arquivada.' : 'Disciplina restaurada.'),
  });

  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }
  if (!subject) return <NotFoundPage message="Esta disciplina não existe no ano letivo ativo." />;

  const CategoryIcon = subject.category === 'formacao_tecnica' ? Cpu : BookOpen;

  return (
    <div style={subjectColorStyle(subject.color)} className="sc">
      <PageHeader
        breadcrumbs={[{ label: 'Disciplinas', to: '/disciplinas' }, { label: subject.name }]}
        eyebrow={
          <div className="flex flex-wrap items-center gap-2">
            <span className="sc-soft sc-text inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium">
              <CategoryIcon className="size-3" aria-hidden />
              {CATEGORY_LABELS[subject.category]}
            </span>
            {subject.code ? (
              <span className="font-mono text-[11px] text-fg-subtle">{subject.code}</span>
            ) : (
              <Badge tone="warning">Código a confirmar</Badge>
            )}
            {subject.archived_at ? <Badge>Arquivada</Badge> : null}
          </div>
        }
        title={subject.name}
        description={subject.teacher ? `Professor(a): ${subject.teacher}` : 'Professor(a) não informado(a)'}
        actions={
          <>
            <Button onClick={() => setEditing(true)}>
              <Pencil /> Editar
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger className="inline-flex size-8.5 items-center justify-center rounded-lg border border-border bg-surface-2 text-fg-muted hover:text-fg" aria-label="Mais ações">
                <MoreHorizontal className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem
                  icon={subject.archived_at ? <ArchiveRestore /> : <Archive />}
                  onSelect={() => archive.mutate(!subject.archived_at)}
                >
                  {subject.archived_at ? 'Restaurar disciplina' : 'Arquivar disciplina'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem icon={<Trash2 />} danger onSelect={() => setDeleting(true)}>
                  Excluir disciplina…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="primary" onClick={() => setExamDialog(true)}>
              <Plus /> Nova prova
            </Button>
          </>
        }
      />

      <div className="grid animate-rise grid-cols-2 gap-3 md:grid-cols-4">
        <MiniStat icon={ClipboardCheck} label={subjectExams.length === 1 ? 'prova' : 'provas'} value={subjectExams.length} />
        <MiniStat icon={ListChecks} label={topicCount === 1 ? 'conteúdo' : 'conteúdos'} value={topicCount} />
        <MiniStat icon={FolderOpen} label="materiais" value={materialCounts.data?.[subject.id] ?? 0} />
        <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-2.5 shadow-card">
          <ProgressRing value={progress.value} size={40} stroke={4} label="Preparação" />
          <p className="text-[11px] leading-snug text-fg-subtle">
            Preparação
            <br />
            das provas pendentes
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="animate-rise">
          <CardHeader
            title="Provas e avaliações"
            description={subjectExams.length ? pluralize(subjectExams.length, 'avaliação cadastrada', 'avaliações cadastradas') : undefined}
            actions={
              subjectExams.length ? (
                <Button size="sm" onClick={() => setExamDialog(true)}>
                  <Plus /> Nova prova
                </Button>
              ) : null
            }
          />
          {subjectExams.length ? (
            <div className="divide-y divide-border border-t border-border">
              {subjectExams.map((exam) => (
                <ExamRow key={exam.id} exam={exam} subject={subject} topics={topicsByExam.get(exam.id) ?? []} showSubject={false} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<ClipboardCheck />}
              title="Você ainda não cadastrou provas nesta disciplina."
              description="Cada prova terá seus próprios conteúdos, materiais, resumo, flashcards e simulados — sem misturar avaliações."
              actions={
                <Button variant="primary" size="sm" onClick={() => setExamDialog(true)}>
                  <Plus /> Cadastrar prova
                </Button>
              }
            />
          )}
        </Card>

        <div className="flex flex-col gap-6">
          <Card className="animate-rise">
            <CardHeader title="Sobre a disciplina" actions={<Button size="icon-sm" variant="ghost" onClick={() => setEditing(true)} aria-label="Editar disciplina"><Pencil /></Button>} />
            <dl className="space-y-3 px-4 pb-4 text-xs sm:px-5">
              <div>
                <dt className="text-fg-subtle">Descrição</dt>
                <dd className="mt-0.5 leading-relaxed whitespace-pre-line text-fg-muted">
                  {subject.description ?? <span className="text-fg-subtle italic">Sem descrição.</span>}
                </dd>
              </div>
              <div>
                <dt className="text-fg-subtle">Código institucional</dt>
                <dd className="mt-0.5 font-mono text-fg-muted">{subject.code ?? 'A confirmar'}</dd>
              </div>
              <div>
                <dt className="text-fg-subtle">Categoria</dt>
                <dd className="mt-0.5 text-fg-muted">{CATEGORY_LABELS[subject.category]}</dd>
              </div>
            </dl>
          </Card>

          <Card className="animate-rise">
            <CardHeader title="Materiais da disciplina" icon={<FolderOpen />} />
            <div className="px-4 pb-4 text-xs leading-relaxed text-fg-muted sm:px-5">
              <p>
                Envie slides, PDFs e documentos para a disciplina ou para uma prova específica. A biblioteca chega na{' '}
                <strong className="font-medium text-fg">Fase 3</strong>.
              </p>
              <p className="mt-2 flex items-center gap-1.5 text-fg-subtle">
                <Camera className="size-3.5" aria-hidden /> “Fotografar meu caderno” também estará disponível aqui.
              </p>
            </div>
          </Card>
        </div>
      </div>

      <SubjectFormDialog open={editing} onOpenChange={setEditing} academicYearId={subject.academic_year_id} subject={subject} />
      <DeleteSubjectDialog subject={subject} open={deleting} onOpenChange={setDeleting} onDeleted={() => navigate('/disciplinas')} />
      <ExamFormDialog
        open={examDialog}
        onOpenChange={setExamDialog}
        subjects={subjects}
        defaultSubjectId={subject.id}
        onSaved={(exam) => navigate(`/provas/${exam.id}/conteudos`)}
      />
    </div>
  );
}
