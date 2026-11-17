import { ClipboardCheck, Plus, Search, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input, Select } from '@/components/ui/Input';
import { EmptyState, ErrorState, Segmented, Skeleton } from '@/components/ui/misc';
import { useYearData } from '@/data/hooks';
import type { Exam, ExamPriority, ExamStatus } from '@/data/types';
import { daysUntil } from '@/lib/dates';
import { CATEGORY_LABELS, EXAM_STATUS_LABELS, EXAM_STATUS_ORDER, PRIORITY_LABELS, PRIORITY_ORDER } from '@/lib/labels';
import { sortExamsForDisplay } from '@/lib/progress';
import { useUrlFilters } from '@/lib/useUrlFilters';
import { pluralize, searchable } from '@/lib/utils';
import { ExamFormDialog } from './ExamFormDialog';
import { ExamRow } from './ExamRow';

type Period = 'proximas' | 'sem_data' | 'passadas' | 'todas';

function periodOf(exam: Exam): Exclude<Period, 'todas'> {
  if (exam.status === 'realizada') return 'passadas';
  if (!exam.exam_date) return 'sem_data';
  return daysUntil(exam.exam_date) >= 0 ? 'proximas' : 'passadas';
}

export function ExamsPage() {
  const navigate = useNavigate();
  const { subjects, subjectById, exams, topicsByExam, isLoading, error, refetch } = useYearData();
  const { params, update, clear } = useUrlFilters();
  const [dialog, setDialog] = useState(false);

  // Filtros ficam na URL: voltar da página da prova mantém a seleção.
  const period = (params.get('periodo') as Period | null) ?? 'todas';
  const subjectFilter = params.get('disciplina') ?? '';
  const statusFilter = (params.get('status') as ExamStatus | null) ?? '';
  const priorityFilter = (params.get('prioridade') as ExamPriority | null) ?? '';
  const query = params.get('q') ?? '';

  const setParam = (key: string, value: string) => update({ [key]: value });

  const counts = useMemo(() => {
    const result = { proximas: 0, sem_data: 0, passadas: 0, todas: exams.length };
    for (const exam of exams) result[periodOf(exam)] += 1;
    return result;
  }, [exams]);

  const term = searchable(query.trim());
  const filtered = useMemo(
    () =>
      sortExamsForDisplay(
        exams.filter((exam) => {
          if (period !== 'todas' && periodOf(exam) !== period) return false;
          if (subjectFilter && exam.subject_id !== subjectFilter) return false;
          if (statusFilter && exam.status !== statusFilter) return false;
          if (priorityFilter && exam.priority !== priorityFilter) return false;
          if (term) {
            const subject = subjectById.get(exam.subject_id);
            const topics = (topicsByExam.get(exam.id) ?? []).map((t) => t.title).join(' ');
            if (!searchable(`${exam.title} ${subject?.name ?? ''} ${exam.description ?? ''} ${topics}`).includes(term)) return false;
          }
          return true;
        }),
      ),
    [exams, period, subjectFilter, statusFilter, priorityFilter, term, subjectById, topicsByExam],
  );

  const hasFilters = Boolean(subjectFilter || statusFilter || priorityFilter || query || period !== 'todas');
  const activeSubjects = subjects.filter((s) => !s.archived_at);

  if (error) return <ErrorState error={error} onRetry={refetch} />;

  return (
    <>
      <PageHeader
        title="Provas"
        description={exams.length ? `${pluralize(exams.length, 'avaliação cadastrada', 'avaliações cadastradas')} no ano letivo.` : 'Todas as avaliações do ano letivo em um só lugar.'}
        actions={
          <Button variant="primary" onClick={() => setDialog(true)} disabled={!activeSubjects.length}>
            <Plus /> Nova prova
          </Button>
        }
      />

      <div className="mb-4 flex animate-rise flex-col gap-3">
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
          <Segmented
            label="Período"
            value={period}
            onChange={(value) => setParam('periodo', value === 'todas' ? '' : value)}
            options={[
              { value: 'todas', label: 'Todas', count: counts.todas },
              { value: 'proximas', label: 'Próximas', count: counts.proximas },
              { value: 'sem_data', label: 'Sem data', count: counts.sem_data },
              { value: 'passadas', label: 'Passadas', count: counts.passadas },
            ]}
          />
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,0.8fr)_auto]">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
            <Input
              value={query}
              onChange={(e) => setParam('q', e.target.value)}
              placeholder="Buscar prova, disciplina ou conteúdo"
              className="pl-9"
              aria-label="Buscar provas"
            />
          </div>
          <Select value={subjectFilter} onChange={(e) => setParam('disciplina', e.target.value)} aria-label="Filtrar por disciplina">
            <option value="">Todas as disciplinas</option>
            {(['formacao_geral', 'formacao_tecnica'] as const).map((category) => (
              <optgroup key={category} label={CATEGORY_LABELS[category]}>
                {subjects
                  .filter((s) => s.category === category)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </optgroup>
            ))}
          </Select>
          <Select value={statusFilter} onChange={(e) => setParam('status', e.target.value)} aria-label="Filtrar por status">
            <option value="">Todos os status</option>
            {EXAM_STATUS_ORDER.map((status) => (
              <option key={status} value={status}>
                {EXAM_STATUS_LABELS[status]}
              </option>
            ))}
          </Select>
          <Select value={priorityFilter} onChange={(e) => setParam('prioridade', e.target.value)} aria-label="Filtrar por prioridade">
            <option value="">Prioridade</option>
            {PRIORITY_ORDER.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </Select>
          {hasFilters ? (
            <Button variant="ghost" onClick={clear}>
              <X /> Limpar
            </Button>
          ) : null}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-72 w-full rounded-xl" />
      ) : !exams.length ? (
        <Card>
          <EmptyState
            icon={<ClipboardCheck />}
            title="Você ainda não cadastrou provas"
            description="Cadastre as avaliações de cada disciplina. Cada prova terá seus próprios conteúdos, materiais e simulados."
            actions={
              activeSubjects.length ? (
                <Button variant="primary" onClick={() => setDialog(true)}>
                  <Plus /> Cadastrar a primeira prova
                </Button>
              ) : null
            }
          />
        </Card>
      ) : !filtered.length ? (
        <Card>
          <EmptyState icon={<Search />} title="Nenhuma prova encontrada" description="Ajuste a busca ou os filtros selecionados." />
        </Card>
      ) : (
        <Card className="animate-rise overflow-hidden">
          <div className="hidden grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_140px_150px] gap-4 border-b border-border px-5 py-2 text-[11px] font-medium tracking-wide text-fg-subtle uppercase md:grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_140px_220px]">
            <span>Avaliação</span>
            <span>Data</span>
            <span>Preparação</span>
            <span className="pr-6 text-right">Status</span>
          </div>
          <div className="divide-y divide-border">
            {filtered.map((exam) => (
              <ExamRow key={exam.id} exam={exam} subject={subjectById.get(exam.subject_id)} topics={topicsByExam.get(exam.id) ?? []} />
            ))}
          </div>
        </Card>
      )}

      <ExamFormDialog
        open={dialog}
        onOpenChange={setDialog}
        subjects={subjects}
        defaultSubjectId={subjectFilter || undefined}
        onSaved={(exam) => navigate(`/provas/${exam.id}/conteudos`)}
      />
    </>
  );
}
