import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronDown, Cloud, HardDrive, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { LogoMark } from '@/components/layout/Logo';
import { SubjectDot } from '@/components/domain/SubjectTag';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { useBackend } from '@/data/DataContext';
import { useAction } from '@/data/hooks';
import { academicYearSchema } from '@/data/schemas';
import { OFFICIAL_SUBJECTS } from '@/data/seed/officialSubjects';
import { importBackup, readBackupBundle } from '@/data/services/backup';
import { createAcademicYear, saveProfile } from '@/data/services/workspace';
import { errorMessage } from '@/lib/errors';
import { CATEGORY_LABELS } from '@/lib/labels';
import { cn } from '@/lib/utils';

const onboardingSchema = academicYearSchema.and(
  z.object({
    display_name: z.string().trim().max(80, 'Use no máximo 80 caracteres.').optional(),
    seed: z.boolean(),
  }),
);
type OnboardingInput = z.input<typeof onboardingSchema>;
type OnboardingValues = z.output<typeof onboardingSchema>;

export function OnboardingPage() {
  const db = useBackend();
  const [showList, setShowList] = useState(false);
  const { register, handleSubmit, formState, watch } = useForm<OnboardingInput, unknown, OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { name: '', start_date: '', end_date: '', display_name: '', seed: true },
  });
  const seed = watch('seed');

  const start = useAction(
    async (backend, values: OnboardingValues) => {
      if (values.display_name) await saveProfile(backend, { display_name: values.display_name });
      return createAcademicYear(
        backend,
        { name: values.name, start_date: values.start_date, end_date: values.end_date },
        { activate: true, seedOfficialSubjects: values.seed },
      );
    },
    {
      success: ({ seeded }) =>
        seeded.length ? `Tudo pronto! ${seeded.length} disciplinas cadastradas.` : 'Ano letivo criado.',
    },
  );

  const fileInput = useRef<HTMLInputElement>(null);
  const restore = useAction(async (backend, file: File) => importBackup(backend, await readBackupBundle(file)), {
    success: (report) => {
      const total = Object.values(report.inserted).reduce((sum, n) => sum + (n ?? 0), 0);
      return `Backup restaurado: ${total} registros importados.`;
    },
    onSuccess: (report) => {
      if (report.failed.length) toast.warning(`${report.failed.length} registro(s) não puderam ser importados.`);
    },
  });
  const onBackupFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      restore.mutate(file);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const year = new Date().getFullYear();

  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg animate-rise">
        <div className="mb-8 flex flex-col items-center text-center">
          <LogoMark size={44} />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight">Bem-vindo à Central de Estudos</h1>
          <p className="mt-2 max-w-sm text-sm text-fg-muted">
            Seu ambiente para organizar disciplinas, provas, materiais e a preparação para cada avaliação.
          </p>
        </div>

        <form
          onSubmit={handleSubmit((values) => start.mutate(values))}
          className="space-y-5 rounded-2xl border border-border bg-surface p-5 shadow-card sm:p-6"
          noValidate
        >
          <Field label="Como você quer ser chamado(a)?" optional error={formState.errors.display_name?.message}>
            <Input placeholder="Seu nome" autoComplete="given-name" {...register('display_name')} />
          </Field>

          <div className="space-y-3">
            <Field label="Ano letivo" hint="Você poderá criar outros períodos letivos depois." error={formState.errors.name?.message}>
              <Input placeholder={`Ex.: ${year}`} autoFocus {...register('name')} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Início" optional error={formState.errors.start_date?.message}>
                <Input type="date" {...register('start_date')} />
              </Field>
              <Field label="Término" optional error={formState.errors.end_date?.message}>
                <Input type="date" {...register('end_date')} />
              </Field>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface-2/50">
            <label className="flex cursor-pointer items-start gap-3 p-3.5">
              <input type="checkbox" className="mt-0.5 size-4 accent-[var(--ce-accent)]" {...register('seed')} />
              <span className="space-y-0.5">
                <span className="block text-sm font-medium text-fg">Cadastrar as 20 disciplinas oficiais</span>
                <span className="block text-xs text-fg-muted">
                  13 de Formação Geral e 7 de Formação Técnica, com os códigos institucionais. Todas começam vazias.
                </span>
              </span>
            </label>
            {seed ? (
              <div className="border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowList((v) => !v)}
                  className="flex w-full items-center justify-between px-3.5 py-2.5 text-xs font-medium text-fg-muted hover:text-fg"
                  aria-expanded={showList}
                >
                  Conferir a lista
                  <ChevronDown className={cn('size-4 transition-transform', showList && 'rotate-180')} aria-hidden />
                </button>
                {showList ? (
                  <div className="max-h-64 space-y-3 overflow-y-auto px-3.5 pb-3.5">
                    {(['formacao_geral', 'formacao_tecnica'] as const).map((category) => (
                      <div key={category}>
                        <p className="mb-1.5 text-[11px] font-medium tracking-wide text-fg-subtle uppercase">
                          {CATEGORY_LABELS[category]}
                        </p>
                        <ul className="space-y-1">
                          {OFFICIAL_SUBJECTS.filter((s) => s.category === category).map((s) => (
                            <li key={s.name} className="flex items-center justify-between gap-3 text-xs">
                              <span className="flex min-w-0 items-center gap-2 text-fg">
                                <SubjectDot color={s.color} />
                                <span className="truncate">{s.name}</span>
                              </span>
                              <span className={cn('shrink-0 font-mono text-[11px]', s.code ? 'text-fg-subtle' : 'text-warning')}>
                                {s.code ?? 'código a confirmar'}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="flex items-start gap-2.5 rounded-xl bg-surface-2/50 p-3 text-xs leading-relaxed text-fg-muted">
            {db.mode === 'local' ? (
              <>
                <HardDrive className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                <span>
                  <strong className="font-medium text-fg">Modo local:</strong> os dados ficarão salvos neste navegador. Para
                  sincronizar entre dispositivos, configure o Supabase — você poderá migrar tudo depois pelo backup.
                </span>
              </>
            ) : (
              <>
                <Cloud className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
                <span>Seus dados serão salvos na nuvem, protegidos pela sua conta.</span>
              </>
            )}
          </div>

          <Button type="submit" variant="primary" size="lg" className="w-full" loading={start.isPending} disabled={restore.isPending}>
            Começar
          </Button>
        </form>

        <div className="mt-5 text-center">
          <Button variant="ghost" size="sm" onClick={() => fileInput.current?.click()} loading={restore.isPending} disabled={start.isPending}>
            <Upload /> Já tenho um backup — restaurar
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".zip,application/zip,application/json,.json"
            className="hidden"
            aria-label="Arquivo de backup"
            onChange={(e) => void onBackupFile(e.target.files?.[0])}
          />
        </div>
      </div>
    </div>
  );
}
