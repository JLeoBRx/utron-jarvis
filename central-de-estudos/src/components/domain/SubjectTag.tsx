import { Link } from 'react-router';
import type { Subject } from '@/data/types';
import { subjectColorStyle } from '@/lib/colors';
import { cn } from '@/lib/utils';

export function SubjectDot({ color, className }: { color: string; className?: string }) {
  return <span className={cn('sc sc-bg inline-block size-2 shrink-0 rounded-full', className)} style={subjectColorStyle(color)} aria-hidden />;
}

/** Identificação visual da disciplina (ponto colorido + nome). */
export function SubjectTag({
  subject,
  link,
  className,
}: {
  subject: Pick<Subject, 'id' | 'name' | 'color'> | undefined;
  link?: boolean;
  className?: string;
}) {
  if (!subject) return <span className="text-xs text-fg-subtle">Disciplina removida</span>;
  const content = (
    <>
      <SubjectDot color={subject.color} />
      <span className="truncate">{subject.name}</span>
    </>
  );
  const classes = cn('inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-fg-muted', className);
  return link ? (
    <Link to={`/disciplinas/${subject.id}`} className={cn(classes, 'hover:text-fg')}>
      {content}
    </Link>
  ) : (
    <span className={classes}>{content}</span>
  );
}
