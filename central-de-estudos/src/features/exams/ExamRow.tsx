import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import { ExamDate, ExamStatusBadge, ExamStatusDot, PriorityBadge } from '@/components/domain/badges';
import { SubjectTag } from '@/components/domain/SubjectTag';
import { ProgressBar } from '@/components/ui/Progress';
import type { Exam, ExamTopic, Subject } from '@/data/types';
import { subjectColorStyle } from '@/lib/colors';
import { formatPercent, topicsProgress } from '@/lib/progress';
import { pluralize } from '@/lib/utils';

interface ExamRowProps {
  exam: Exam;
  subject?: Subject;
  topics: ExamTopic[];
  showSubject?: boolean;
}

/** Linha de prova usada nas listagens (responsiva: empilha no celular). */
export function ExamRow({ exam, subject, topics, showSubject = true }: ExamRowProps) {
  const progress = topicsProgress(topics);
  return (
    <Link
      to={`/provas/${exam.id}`}
      style={subjectColorStyle(subject?.color)}
      className="sc group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-3.5 transition-colors hover:bg-surface-2/60 sm:px-5 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_140px_auto]"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <ExamStatusDot status={exam.status} />
          <span className="truncate text-sm font-medium text-fg group-hover:text-accent-text">{exam.title}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 pl-4">
          {showSubject ? <SubjectTag subject={subject} className="max-w-full text-[11px]" /> : null}
          <ExamDate date={exam.exam_date} time={exam.exam_time} realizada={exam.status === 'realizada'} className="md:hidden" />
        </div>
      </div>

      <div className="hidden md:block">
        <ExamDate date={exam.exam_date} time={exam.exam_time} realizada={exam.status === 'realizada'} />
      </div>

      <div className="col-span-2 flex items-center gap-3 pl-4 md:col-span-1 md:pl-0">
        <ProgressBar value={progress.value} subjectColor className="flex-1" label={`Preparação para ${exam.title}`} />
        <span className="w-9 text-right text-xs text-fg-muted tabular" title={pluralize(progress.total, 'conteúdo', 'conteúdos')}>
          {formatPercent(progress.value)}
        </span>
      </div>

      <div className="col-start-2 row-start-1 flex items-center gap-2 md:col-start-auto md:row-start-auto">
        <span className="hidden lg:inline-flex">
          <PriorityBadge priority={exam.priority} compact />
        </span>
        <ExamStatusBadge status={exam.status} />
        <ChevronRight className="hidden size-4 text-fg-subtle sm:block" aria-hidden />
      </div>
    </Link>
  );
}
