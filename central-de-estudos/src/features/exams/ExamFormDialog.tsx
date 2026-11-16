import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Field } from '@/components/ui/Field';
import { Input, Select, Textarea } from '@/components/ui/Input';
import { Segmented } from '@/components/ui/misc';
import { useAction } from '@/data/hooks';
import { examSchema, type ExamInput, type ExamValues } from '@/data/schemas';
import { createExam, updateExam } from '@/data/services/exams';
import type { Exam, Subject } from '@/data/types';
import { formatTime } from '@/lib/dates';
import { CATEGORY_LABELS, EXAM_STATUS_LABELS, EXAM_STATUS_ORDER, PRIORITY_LABELS } from '@/lib/labels';

interface ExamFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subjects: Subject[];
  exam?: Exam;
  defaultSubjectId?: string;
  onSaved?: (exam: Exam) => void;
}

function toForm(exam?: Exam, defaultSubjectId?: string): ExamInput {
  return {
    subject_id: exam?.subject_id ?? defaultSubjectId ?? '',
    title: exam?.title ?? '',
    exam_date: exam?.exam_date ?? '',
    exam_time: formatTime(exam?.exam_time),
    teacher: exam?.teacher ?? '',
    description: exam?.description ?? '',
    priority: exam?.priority ?? 'media',
    status: exam?.status ?? 'nao_iniciada',
    score: exam?.score ?? '',
    max_score: exam?.max_score ?? '',
  };
}

export function ExamFormDialog({ open, onOpenChange, subjects, exam, defaultSubjectId, onSaved }: ExamFormDialogProps) {
  const { register, handleSubmit, control, reset, formState } = useForm<ExamInput, unknown, ExamValues>({
    resolver: zodResolver(examSchema),
    defaultValues: toForm(exam, defaultSubjectId),
  });

  useEffect(() => {
    if (open) reset(toForm(exam, defaultSubjectId));
  }, [open, exam, defaultSubjectId, reset]);

  const subjectId = useWatch({ control, name: 'subject_id' });
  const status = useWatch({ control, name: 'status' });
  const selectedSubject = subjects.find((s) => s.id === subjectId);
  const showScore = status === 'realizada' || exam?.score != null;

  const groups = useMemo(() => {
    const active = subjects.filter((s) => !s.archived_at || s.id === exam?.subject_id);
    return (['formacao_geral', 'formacao_tecnica'] as const)
      .map((category) => ({ category, items: active.filter((s) => s.category === category) }))
      .filter((g) => g.items.length);
  }, [subjects, exam?.subject_id]);

  const save = useAction((db, values: ExamValues) => (exam ? updateExam(db, exam.id, values) : createExam(db, values)), {
    success: exam ? 'Prova atualizada.' : 'Prova cadastrada.',
    onSuccess: (saved) => {
      onOpenChange(false);
      onSaved?.(saved);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={exam ? 'Editar prova' : 'Nova prova'}
      description={exam ? undefined : 'Cadastre a avaliação. Os conteúdos cobrados podem ser adicionados em seguida.'}
      size="lg"
      modalLocked={formState.isDirty}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" type="submit" form="exam-form" loading={save.isPending}>
            {exam ? 'Salvar alterações' : 'Cadastrar prova'}
          </Button>
        </>
      }
    >
      <form id="exam-form" className="grid gap-4" onSubmit={handleSubmit((values) => save.mutate(values))} noValidate>
        <div className="grid gap-4 sm:grid-cols-[1.1fr_1fr]">
          <Field label="Disciplina" error={formState.errors.subject_id?.message}>
            <Select {...register('subject_id')}>
              <option value="">Selecione…</option>
              {groups.map((group) => (
                <optgroup key={group.category} label={CATEGORY_LABELS[group.category]}>
                  {group.items.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Nome da avaliação" error={formState.errors.title?.message}>
            <Input autoFocus={!exam} placeholder="Ex.: Avaliação 2" {...register('title')} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Data" optional hint="Deixe em branco se ainda não foi definida." error={formState.errors.exam_date?.message}>
            <Input type="date" {...register('exam_date')} />
          </Field>
          <Field label="Horário" optional error={formState.errors.exam_time?.message}>
            <Input type="time" {...register('exam_time')} />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-fg-muted">Prioridade</span>
            <Controller
              control={control}
              name="priority"
              render={({ field }) => (
                <Segmented
                  label="Prioridade"
                  value={field.value}
                  onChange={field.onChange}
                  className="self-start"
                  options={(['baixa', 'media', 'alta'] as const).map((value) => ({ value, label: PRIORITY_LABELS[value] }))}
                />
              )}
            />
          </div>
          <Field label="Status">
            <Select {...register('status')}>
              {EXAM_STATUS_ORDER.map((value) => (
                <option key={value} value={value}>
                  {EXAM_STATUS_LABELS[value]}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field
          label="Professor(a)"
          optional
          hint={selectedSubject?.teacher ? `Em branco, vale o professor da disciplina: ${selectedSubject.teacher}.` : undefined}
          error={formState.errors.teacher?.message}
        >
          <Input placeholder={selectedSubject?.teacher ?? 'Nome do(a) professor(a)'} {...register('teacher')} />
        </Field>

        <Field label="Descrição" optional error={formState.errors.description?.message}>
          <Textarea rows={3} placeholder="Formato da prova, orientações do professor, materiais permitidos…" {...register('description')} />
        </Field>

        {showScore ? (
          <div className="grid grid-cols-2 gap-4 rounded-xl border border-border bg-surface-2/50 p-3">
            <Field label="Nota obtida" optional error={formState.errors.score?.message as string | undefined}>
              <Input inputMode="decimal" placeholder="Ex.: 8,5" {...register('score')} />
            </Field>
            <Field label="Nota máxima" optional error={formState.errors.max_score?.message as string | undefined}>
              <Input inputMode="decimal" placeholder="Ex.: 10" {...register('max_score')} />
            </Field>
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
