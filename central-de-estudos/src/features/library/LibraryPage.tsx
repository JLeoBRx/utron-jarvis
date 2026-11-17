import { FolderOpen, Search, X } from 'lucide-react';
import { useMemo } from 'react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input, Select } from '@/components/ui/Input';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/misc';
import { useMaterials, useYearData } from '@/data/hooks';
import type { MaterialCategory } from '@/data/types';
import { formatBytes } from '@/lib/files';
import { CATEGORY_LABELS, MATERIAL_CATEGORY_LABELS } from '@/lib/labels';
import { useUrlFilters } from '@/lib/useUrlFilters';
import { pluralize, searchable } from '@/lib/utils';
import { AddMaterialActions } from './AddMaterialActions';
import { MaterialList } from './MaterialList';
import { KIND_INFO, visualKind, type MaterialVisualKind } from './materialKind';

const TYPE_FILTERS: { value: string; label: string; kinds: MaterialVisualKind[] }[] = [
  { value: 'documentos', label: 'Documentos (PDF, Word, PowerPoint, TXT)', kinds: ['pdf', 'docx', 'pptx', 'txt'] },
  { value: 'imagens', label: 'Imagens', kinds: ['imagem'] },
  { value: 'cadernos', label: 'Cadernos fotografados', kinds: ['caderno'] },
  { value: 'links', label: 'Links e vídeos', kinds: ['link', 'video'] },
];

export function LibraryPage() {
  const { subjects, subjectById, exams, isLoading: yearLoading, error: yearError } = useYearData();
  const subjectIds = useMemo(() => subjects.map((s) => s.id), [subjects]);
  const materials = useMaterials(subjectIds);
  const { params, update, clear } = useUrlFilters();

  const subjectFilter = params.get('disciplina') ?? '';
  const examFilter = params.get('prova') ?? '';
  const categoryFilter = (params.get('categoria') as MaterialCategory | null) ?? '';
  const typeFilter = params.get('tipo') ?? '';
  const query = params.get('q') ?? '';

  const setParam = (key: string, value: string, extra?: Record<string, string>) => update({ [key]: value, ...extra });

  const examById = useMemo(() => new Map(exams.map((e) => [e.id, e])), [exams]);
  const term = searchable(query.trim());
  const typeKinds = TYPE_FILTERS.find((t) => t.value === typeFilter)?.kinds;
  const list = materials.data ?? [];
  const filtered = list.filter((m) => {
    if (subjectFilter && m.subject_id !== subjectFilter) return false;
    if (examFilter === 'geral' && m.exam_id) return false;
    if (examFilter && examFilter !== 'geral' && m.exam_id !== examFilter) return false;
    if (categoryFilter && m.category !== categoryFilter) return false;
    if (typeKinds && !typeKinds.includes(visualKind(m))) return false;
    if (term) {
      const haystack = `${m.title} ${m.description ?? ''} ${m.origin ?? ''} ${m.file_name ?? ''} ${subjectById.get(m.subject_id)?.name ?? ''} ${m.exam_id ? (examById.get(m.exam_id)?.title ?? '') : ''} ${KIND_INFO[visualKind(m)].label}`;
      if (!searchable(haystack).includes(term)) return false;
    }
    return true;
  });
  const totalBytes = list.reduce((sum, m) => sum + (m.size_bytes ?? 0), 0);
  const hasFilters = Boolean(subjectFilter || examFilter || categoryFilter || typeFilter || query);
  const subjectExams = exams.filter((e) => e.subject_id === subjectFilter);

  const error = yearError ?? materials.error;
  if (error) return <ErrorState error={error} onRetry={() => void materials.refetch()} />;

  return (
    <>
      <PageHeader
        title="Biblioteca"
        description={
          list.length
            ? `${pluralize(list.length, 'material', 'materiais')} · ${formatBytes(totalBytes)} armazenados com acesso privado.`
            : 'Slides, PDFs, documentos, imagens, fotos do caderno e links — organizados por disciplina e prova.'
        }
        actions={<AddMaterialActions subjectId={subjectFilter || undefined} examId={examFilter && examFilter !== 'geral' ? examFilter : undefined} />}
      />

      <div className="mb-4 animate-rise space-y-2">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
            <Input value={query} onChange={(e) => setParam('q', e.target.value)} placeholder="Buscar materiais" className="pl-9" aria-label="Buscar materiais" />
          </div>
          {hasFilters ? (
            <Button variant="ghost" onClick={clear}>
              <X /> Limpar
            </Button>
          ) : null}
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Select value={subjectFilter} onChange={(e) => setParam('disciplina', e.target.value, { prova: '' })} aria-label="Filtrar por disciplina">
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
        <Select value={examFilter} onChange={(e) => setParam('prova', e.target.value)} disabled={!subjectFilter} aria-label="Filtrar por prova">
          <option value="">{subjectFilter ? 'Todas as provas' : 'Prova (escolha a disciplina)'}</option>
          <option value="geral">Somente materiais gerais</option>
          {subjectExams.map((exam) => (
            <option key={exam.id} value={exam.id}>
              {exam.title}
            </option>
          ))}
        </Select>
        <Select value={categoryFilter} onChange={(e) => setParam('categoria', e.target.value)} aria-label="Filtrar por categoria">
          <option value="">Todas as categorias</option>
          {(Object.entries(MATERIAL_CATEGORY_LABELS) as [MaterialCategory, string][]).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select value={typeFilter} onChange={(e) => setParam('tipo', e.target.value)} aria-label="Filtrar por tipo">
          <option value="">Todos os tipos</option>
          {TYPE_FILTERS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
        </div>
      </div>

      {yearLoading || materials.isLoading ? (
        <Skeleton className="h-72 w-full rounded-xl" />
      ) : !list.length ? (
        <Card>
          <EmptyState
            icon={<FolderOpen />}
            title="Envie os materiais para começar a construir seu resumo."
            description="Cada material fica ligado à disciplina e, se você quiser, a uma prova específica — sem misturar avaliações."
            actions={<AddMaterialActions size="sm" />}
          />
        </Card>
      ) : !filtered.length ? (
        <Card>
          <EmptyState icon={<Search />} title="Nenhum material encontrado" description="Ajuste a busca ou os filtros." />
        </Card>
      ) : (
        <Card className="animate-rise overflow-hidden">
          <MaterialList materials={filtered} subjectById={subjectById} examById={examById} showSubject={!subjectFilter} />
        </Card>
      )}
    </>
  );
}
