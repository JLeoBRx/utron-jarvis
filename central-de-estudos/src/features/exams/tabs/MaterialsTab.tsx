import { FolderOpen } from 'lucide-react';
import { useMemo } from 'react';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState, Skeleton } from '@/components/ui/misc';
import { useMaterials, useYearData } from '@/data/hooks';
import type { Exam } from '@/data/types';
import { pluralize } from '@/lib/utils';
import { AddMaterialActions } from '../../library/AddMaterialActions';
import { MaterialList } from '../../library/MaterialList';

/** Materiais SOMENTE desta prova (nunca mistura avaliações). */
export function MaterialsTab({ exam }: { exam: Exam }) {
  const { subjectById, exams } = useYearData();
  const materials = useMaterials([exam.subject_id]);
  const examById = useMemo(() => new Map(exams.map((e) => [e.id, e])), [exams]);
  const list = (materials.data ?? []).filter((m) => m.exam_id === exam.id);

  return (
    <Card className="animate-rise">
      <CardHeader
        title="Materiais desta prova"
        description={list.length ? pluralize(list.length, 'material', 'materiais') : 'Slides, PDFs, fotos do caderno e links usados nesta avaliação.'}
      />
      <div className="flex flex-wrap gap-2 px-4 pb-4 sm:px-5">
        <AddMaterialActions subjectId={exam.subject_id} examId={exam.id} size="sm" />
      </div>
      {materials.isLoading ? (
        <Skeleton className="mx-4 mb-4 h-32 rounded-lg" />
      ) : list.length ? (
        <div className="border-t border-border">
          <MaterialList materials={list} subjectById={subjectById} examById={examById} showSubject={false} showExam={false} />
        </div>
      ) : (
        <EmptyState
          compact
          icon={<FolderOpen />}
          title="Envie os materiais para começar a construir seu resumo."
          description="Os materiais enviados aqui ficam vinculados somente a esta prova."
        />
      )}
    </Card>
  );
}
