import { Archive, ArchiveRestore, BookOpen, Cpu, MoreHorizontal, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Input } from '@/components/ui/Input';
import { EmptyState, ErrorState, Segmented, Skeleton } from '@/components/ui/misc';
import { ProgressBar } from '@/components/ui/Progress';
import { useAction, useMaterialCounts, useYearData } from '@/data/hooks';
import { setSubjectArchived } from '@/data/services/subjects';
import { seedOfficialSubjects } from '@/data/services/workspace';
import type { Subject, SubjectCategory } from '@/data/types';
import { subjectColorStyle } from '@/lib/colors';
import { CATEGORY_LABELS } from '@/lib/labels';
import { formatPercent, pendingExamsProgress, type ProgressInfo } from '@/lib/progress';
import { cn, pluralize, searchable } from '@/lib/utils';
import { DeleteSubjectDialog } from './SubjectDialogs';
import { SubjectFormDialog } from './SubjectFormDialog';

type CategoryFilter = 'todas' | SubjectCategory;

interface CardData {
  subject: Subject;
  examCount: number;
  pendingCount: number;
  materialCount: number;
  progress: ProgressInfo;
}

function SubjectCard({ data, onEdit, onDelete }: { data: CardData; onEdit: () => void; onDelete: () => void }) {
  const { subject, examCount, pendingCount, materialCount, progress } = data;
  const archive = useAction((db, archived: boolean) => setSubjectArchived(db, subject.id, archived), {
    success: (s) => (s.archived_at ? 'Disciplina arquivada.' : 'Disciplina restaurada.'),
  });
  const CategoryIcon = subject.category === 'formacao_tecnica' ? Cpu : BookOpen;

  return (
    <div
      style={subjectColorStyle(subject.color)}
      className={cn(
        'sc group relative flex flex-col rounded-xl border border-border bg-surface p-4 shadow-card transition-[border-color,transform] duration-200 hover:-translate-y-px hover:border-border-strong',
        subject.archived_at && 'opacity-60',
      )}
    >
      <div className="flex items-start gap-3">
        <span className="sc-soft sc-text flex size-9 shrink-0 items-center justify-center rounded-lg" aria-hidden>
          <CategoryIcon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <Link to={`/disciplinas/${subject.id}`} className="block text-sm leading-snug font-semibold text-fg after:absolute after:inset-0 after:rounded-xl">
            {subject.name}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {subject.code ? (
              <span className="font-mono text-[11px] text-fg-subtle">{subject.code}</span>
            ) : (
              <Badge tone="warning">Código a confirmar</Badge>
            )}
            {subject.archived_at ? <Badge tone="neutral">Arquivada</Badge> : null}
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            className="relative z-10 -mt-1 -mr-1.5 rounded-md p-1 text-fg-subtle opacity-70 transition hover:bg-surface-2 hover:text-fg group-hover:opacity-100 data-[state=open]:opacity-100"
            aria-label={`Ações de ${subject.name}`}
          >
            <MoreHorizontal className="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem icon={<Pencil />} onSelect={onEdit}>
              Editar
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={subject.archived_at ? <ArchiveRestore /> : <Archive />}
              onSelect={() => archive.mutate(!subject.archived_at)}
            >
              {subject.archived_at ? 'Restaurar' : 'Arquivar'}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem icon={<Trash2 />} danger onSelect={onDelete}>
              Excluir…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <p className="mt-3 truncate text-xs text-fg-muted">{subject.teacher ?? <span className="text-fg-subtle">Professor(a) não informado(a)</span>}</p>

      <div className="mt-4 flex items-center gap-4 text-xs text-fg-muted">
        <span>
          <strong className="font-semibold text-fg tabular">{examCount}</strong> {examCount === 1 ? 'prova' : 'provas'}
        </span>
        <span>
          <strong className="font-semibold text-fg tabular">{materialCount}</strong> {materialCount === 1 ? 'material' : 'materiais'}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <ProgressBar value={progress.value} subjectColor className="flex-1" label={`Preparação em ${subject.name}`} />
        <span className="w-9 text-right text-xs font-medium text-fg tabular">{formatPercent(progress.value)}</span>
      </div>
      <p className="mt-1.5 text-[11px] text-fg-subtle">
        {pendingCount ? `${pluralize(pendingCount, 'prova pendente', 'provas pendentes')}` : 'Nenhuma prova pendente'}
      </p>
    </div>
  );
}

export function SubjectsPage() {
  const { activeYear, subjects, exams, topicsByExam, isLoading, error, refetch } = useYearData();
  const materialCounts = useMaterialCounts(subjects.map((s) => s.id));
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<CategoryFilter>('todas');
  const [showArchived, setShowArchived] = useState(false);
  const [formState, setFormState] = useState<{ open: boolean; subject?: Subject }>({ open: false });
  const [deleting, setDeleting] = useState<Subject | null>(null);

  const seed = useAction((db, yearId: string) => seedOfficialSubjects(db, yearId), {
    success: (rows) => (rows.length ? `${rows.length} disciplinas oficiais cadastradas.` : 'As disciplinas oficiais já estavam cadastradas.'),
  });

  const cards = useMemo<CardData[]>(
    () =>
      subjects.map((subject) => {
        const list = exams.filter((e) => e.subject_id === subject.id);
        return {
          subject,
          examCount: list.length,
          pendingCount: list.filter((e) => e.status !== 'realizada').length,
          materialCount: materialCounts.data?.[subject.id] ?? 0,
          progress: pendingExamsProgress(list, topicsByExam),
        };
      }),
    [subjects, exams, topicsByExam, materialCounts.data],
  );

  const archivedCount = subjects.filter((s) => s.archived_at).length;
  const term = searchable(query.trim());
  const visible = cards.filter(
    ({ subject }) =>
      (showArchived || !subject.archived_at) &&
      (category === 'todas' || subject.category === category) &&
      (!term || searchable(`${subject.name} ${subject.code ?? ''} ${subject.teacher ?? ''}`).includes(term)),
  );
  const activeCards = cards.filter((c) => !c.subject.archived_at);
  const countBy = (cat: SubjectCategory) => activeCards.filter((c) => c.subject.category === cat).length;

  if (error) return <ErrorState error={error} onRetry={refetch} />;

  return (
    <>
      <PageHeader
        title="Disciplinas"
        description={activeYear ? `${pluralize(activeCards.length, 'disciplina', 'disciplinas')} no ano letivo ${activeYear.name}.` : undefined}
        actions={
          <Button variant="primary" onClick={() => setFormState({ open: true })} disabled={!activeYear}>
            <Plus /> Nova disciplina
          </Button>
        }
      />

      <div className="mb-5 flex animate-rise flex-col gap-3 md:flex-row md:items-center">
        <div className="relative md:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por nome, código ou professor"
            className="pr-8 pl-9"
            aria-label="Buscar disciplinas"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-fg-subtle hover:text-fg"
              aria-label="Limpar busca"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
          <Segmented
            label="Categoria"
            value={category}
            onChange={setCategory}
            options={[
              { value: 'todas', label: 'Todas', count: activeCards.length },
              { value: 'formacao_geral', label: 'Formação Geral', count: countBy('formacao_geral') },
              { value: 'formacao_tecnica', label: 'Formação Técnica', count: countBy('formacao_tecnica') },
            ]}
          />
        </div>
        {archivedCount ? (
          <label className="flex items-center gap-2 text-xs text-fg-muted md:ml-auto">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="accent-[var(--ce-accent)]" />
            Mostrar arquivadas ({archivedCount})
          </label>
        ) : null}
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      ) : !subjects.length ? (
        <EmptyState
          icon={<BookOpen />}
          title="Nenhuma disciplina neste ano letivo"
          description="Cadastre as 20 disciplinas oficiais de uma vez ou crie disciplinas manualmente."
          actions={
            <>
              <Button variant="primary" loading={seed.isPending} onClick={() => activeYear && seed.mutate(activeYear.id)}>
                Cadastrar disciplinas oficiais
              </Button>
              <Button onClick={() => setFormState({ open: true })}>
                <Plus /> Nova disciplina
              </Button>
            </>
          }
        />
      ) : !visible.length ? (
        <EmptyState icon={<Search />} title="Nenhuma disciplina encontrada" description="Ajuste a busca ou os filtros." />
      ) : (
        <div className="space-y-8">
          {(['formacao_geral', 'formacao_tecnica'] as const)
            .filter((cat) => category === 'todas' || category === cat)
            .map((cat) => {
              const group = visible.filter((c) => c.subject.category === cat);
              if (!group.length) return null;
              return (
                <section key={cat} aria-labelledby={`grupo-${cat}`} className="animate-rise">
                  <h2 id={`grupo-${cat}`} className="mb-3 flex items-center gap-2 text-xs font-medium tracking-wide text-fg-subtle uppercase">
                    {CATEGORY_LABELS[cat]}
                    <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-fg-muted tabular">{group.length}</span>
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {group.map((data) => (
                      <SubjectCard
                        key={data.subject.id}
                        data={data}
                        onEdit={() => setFormState({ open: true, subject: data.subject })}
                        onDelete={() => setDeleting(data.subject)}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
        </div>
      )}

      {activeYear ? (
        <SubjectFormDialog
          open={formState.open}
          onOpenChange={(open) => setFormState((s) => ({ ...s, open }))}
          academicYearId={activeYear.id}
          subject={formState.subject}
          defaultCategory={category === 'todas' ? undefined : category}
        />
      ) : null}
      {deleting ? (
        <DeleteSubjectDialog subject={deleting} open onOpenChange={(open) => !open && setDeleting(null)} />
      ) : null}
    </>
  );
}
