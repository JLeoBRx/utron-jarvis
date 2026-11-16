import { zodResolver } from '@hookform/resolvers/zod';
import { Check } from 'lucide-react';
import { useEffect } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Field } from '@/components/ui/Field';
import { Input, Textarea } from '@/components/ui/Input';
import { Segmented } from '@/components/ui/misc';
import { useAction } from '@/data/hooks';
import { subjectSchema, type SubjectInput, type SubjectValues } from '@/data/schemas';
import { createSubject, updateSubject } from '@/data/services/subjects';
import type { Subject, SubjectCategory } from '@/data/types';
import { SUBJECT_COLORS, subjectColorStyle } from '@/lib/colors';
import { CATEGORY_LABELS } from '@/lib/labels';
import { cn } from '@/lib/utils';

interface SubjectFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  academicYearId: string;
  subject?: Subject;
  defaultCategory?: SubjectCategory;
  onSaved?: (subject: Subject) => void;
}

function toForm(subject?: Subject, category: SubjectCategory = 'formacao_geral'): SubjectInput {
  return {
    name: subject?.name ?? '',
    code: subject?.code ?? '',
    category: subject?.category ?? category,
    teacher: subject?.teacher ?? '',
    description: subject?.description ?? '',
    color: subject?.color ?? 'indigo',
  };
}

export function SubjectFormDialog({ open, onOpenChange, academicYearId, subject, defaultCategory, onSaved }: SubjectFormDialogProps) {
  const form = useForm<SubjectInput, unknown, SubjectValues>({
    resolver: zodResolver(subjectSchema),
    defaultValues: toForm(subject, defaultCategory),
  });
  const { register, handleSubmit, control, reset, formState } = form;

  useEffect(() => {
    if (open) reset(toForm(subject, defaultCategory));
  }, [open, subject, defaultCategory, reset]);

  const save = useAction(
    (db, values: SubjectValues) => (subject ? updateSubject(db, subject.id, values) : createSubject(db, academicYearId, values)),
    {
      success: subject ? 'Disciplina atualizada.' : 'Disciplina cadastrada.',
      onSuccess: (saved) => {
        onOpenChange(false);
        onSaved?.(saved);
      },
    },
  );

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={subject ? 'Editar disciplina' : 'Nova disciplina'}
      description={subject ? undefined : 'A disciplina começa vazia — provas e materiais são adicionados depois.'}
      modalLocked={formState.isDirty}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" type="submit" form="subject-form" loading={save.isPending}>
            {subject ? 'Salvar alterações' : 'Cadastrar disciplina'}
          </Button>
        </>
      }
    >
      <form id="subject-form" className="grid gap-4" onSubmit={handleSubmit((values) => save.mutate(values))} noValidate>
        <Field label="Nome oficial" error={formState.errors.name?.message}>
          <Input autoFocus placeholder="Ex.: Física 2" {...register('name')} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Código institucional" optional hint="Deixe em branco se ainda não foi confirmado." error={formState.errors.code?.message}>
            <Input placeholder="Ex.: INT.12847" className="font-mono text-[13px]" {...register('code')} />
          </Field>
          <Field label="Professor(a)" optional error={formState.errors.teacher?.message}>
            <Input placeholder="Nome do(a) professor(a)" {...register('teacher')} />
          </Field>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-fg-muted">Categoria</span>
          <Controller
            control={control}
            name="category"
            render={({ field }) => (
              <Segmented
                label="Categoria"
                value={field.value}
                onChange={field.onChange}
                options={(['formacao_geral', 'formacao_tecnica'] as const).map((value) => ({ value, label: CATEGORY_LABELS[value] }))}
                className="self-start"
              />
            )}
          />
        </div>
        <Field label="Descrição" optional error={formState.errors.description?.message}>
          <Textarea placeholder="Ementa, objetivos ou observações sobre a disciplina" {...register('description')} />
        </Field>
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium text-fg-muted">Cor de identificação</span>
          <Controller
            control={control}
            name="color"
            render={({ field }) => (
              <div role="radiogroup" aria-label="Cor de identificação" className="flex flex-wrap gap-1.5">
                {SUBJECT_COLORS.map((color) => {
                  const selected = field.value === color.key;
                  return (
                    <button
                      key={color.key}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      aria-label={color.label}
                      title={color.label}
                      onClick={() => field.onChange(color.key)}
                      style={subjectColorStyle(color.key)}
                      className={cn(
                        'sc sc-bg flex size-7 items-center justify-center rounded-lg ring-offset-2 ring-offset-elevated transition-transform hover:scale-110',
                        selected && 'ring-2 ring-fg/60',
                      )}
                    >
                      {selected ? <Check className="size-3.5 text-white" strokeWidth={3} /> : null}
                    </button>
                  );
                })}
              </div>
            )}
          />
        </div>
      </form>
    </Dialog>
  );
}
