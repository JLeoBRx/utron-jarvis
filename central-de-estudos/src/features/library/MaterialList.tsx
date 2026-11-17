import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import { SubjectTag } from '@/components/domain/SubjectTag';
import type { Exam, Material, Subject } from '@/data/types';
import { formatDate } from '@/lib/dates';
import { formatBytes } from '@/lib/files';
import { MATERIAL_CATEGORY_LABELS } from '@/lib/labels';
import { KIND_INFO, MaterialIcon, visualKind } from './materialKind';

interface MaterialListProps {
  materials: Material[];
  subjectById: Map<string, Subject>;
  examById: Map<string, Exam>;
  showSubject?: boolean;
  showExam?: boolean;
}

/** Lista de materiais (responsiva). Cada item abre a página do material. */
export function MaterialList({ materials, subjectById, examById, showSubject = true, showExam = true }: MaterialListProps) {
  return (
    <ul className="divide-y divide-border" aria-label="Materiais">
      {materials.map((material) => {
        const exam = material.exam_id ? examById.get(material.exam_id) : undefined;
        const kind = KIND_INFO[visualKind(material)];
        return (
          <li key={material.id}>
            <Link
              to={`/biblioteca/${material.id}`}
              className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-2/60 sm:px-5"
            >
              <MaterialIcon material={material} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-fg group-hover:text-accent-text">{material.title}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-fg-subtle">
                  {showSubject ? <SubjectTag subject={subjectById.get(material.subject_id)} className="text-[11px] font-normal" /> : null}
                  {showExam ? <span>{exam ? exam.title : 'Geral da disciplina'}</span> : null}
                  <span>{MATERIAL_CATEGORY_LABELS[material.category]}</span>
                </span>
              </span>
              <span className="hidden shrink-0 text-right text-[11px] text-fg-subtle sm:block">
                <span className="block text-fg-muted">{kind.label}{material.kind !== 'link' ? ` · ${formatBytes(material.size_bytes)}` : ''}</span>
                <span className="block">{formatDate(material.created_at)}{material.version > 1 ? ` · v${material.version}` : ''}</span>
              </span>
              <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
