import { useQuery } from '@tanstack/react-query';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Spinner } from '@/components/ui/misc';
import { useBackend } from '@/data/DataContext';
import { useAction } from '@/data/hooks';
import { deleteSubject, getSubjectDeletionImpact } from '@/data/services/subjects';
import type { Subject } from '@/data/types';
import { pluralize } from '@/lib/utils';

/** Exclusão de disciplina com prévia do que será apagado e confirmação digitada. */
export function DeleteSubjectDialog({
  subject,
  open,
  onOpenChange,
  onDeleted,
}: {
  subject: Subject;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const db = useBackend();
  const impact = useQuery({
    queryKey: [db.mode, db.userId, 'subject-impact', subject.id],
    queryFn: () => getSubjectDeletionImpact(db, subject.id),
    enabled: open,
    staleTime: 0,
  });
  const remove = useAction((backend, id: string) => deleteSubject(backend, id), {
    success: 'Disciplina excluída.',
    onSuccess: () => {
      onOpenChange(false);
      onDeleted?.();
    },
  });
  const data = impact.data;
  const hasContent = data ? Object.values(data).some((n) => n > 0) : true;
  const lines = data
    ? [
        data.exams && pluralize(data.exams, 'prova (com seus conteúdos)', 'provas (com seus conteúdos)'),
        data.materials && pluralize(data.materials, 'material e seus arquivos', 'materiais e seus arquivos'),
        data.summaries && pluralize(data.summaries, 'resumo', 'resumos'),
        data.flashcards && pluralize(data.flashcards, 'flashcard', 'flashcards'),
        data.questions && pluralize(data.questions, 'questão', 'questões'),
      ].filter(Boolean)
    : [];

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Excluir "${subject.name}"?`}
      description="Esta ação não pode ser desfeita. Se quiser apenas ocultar a disciplina, use “Arquivar”."
      confirmLabel="Excluir definitivamente"
      requireText={hasContent ? subject.name : undefined}
      loading={remove.isPending}
      onConfirm={() => remove.mutate(subject.id)}
    >
      {impact.isLoading ? (
        <Spinner />
      ) : lines.length ? (
        <div className="rounded-lg border border-danger/25 bg-danger-soft p-3 text-xs text-fg-muted">
          <p className="mb-1.5 font-medium text-danger">Também serão apagados:</p>
          <ul className="list-disc space-y-0.5 pl-4">
            {lines.map((line) => (
              <li key={String(line)}>{line}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-fg-muted">A disciplina está vazia — nenhum outro dado será afetado.</p>
      )}
    </ConfirmDialog>
  );
}
