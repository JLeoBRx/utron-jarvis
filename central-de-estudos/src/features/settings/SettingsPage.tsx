import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import {
  Bell,
  Bot,
  Check,
  Cloud,
  Database,
  Download,
  FolderOpen,
  HardDrive,
  MoreHorizontal,
  Palette,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  Upload,
  User,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { useLocation } from 'react-router';
import { toast } from 'sonner';
import { useSession } from '@/app/session';
import { useTheme } from '@/app/theme';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Dialog } from '@/components/ui/Dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { Segmented } from '@/components/ui/misc';
import { useBackend } from '@/data/DataContext';
import { useAction, useProfile, useWorkspace } from '@/data/hooks';
import { LocalBackend } from '@/data/backend/local';
import { academicYearSchema, type AcademicYearInput, type AcademicYearValues } from '@/data/schemas';
import {
  backupFileName,
  exportBackupArchive,
  importBackup,
  readBackupBundle,
  referencedFilePaths,
  type BackupBundle,
  type ImportReport,
} from '@/data/services/backup';
import {
  createAcademicYear,
  deleteAcademicYear,
  saveProfile,
  seedOfficialSubjects,
  setActiveAcademicYear,
  updateAcademicYear,
} from '@/data/services/workspace';
import type { AcademicYear, TableName } from '@/data/types';
import { FRIENDLY_TABLE_NAMES } from '@/data/backend/relations';
import { formatDate } from '@/lib/dates';
import { errorMessage } from '@/lib/errors';
import type { ThemePreference } from '@/lib/theme';
import { downloadBlob } from '@/lib/utils';

function Section({ id, icon: Icon, title, description, children }: { id: string; icon: LucideIcon; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className="scroll-mt-20 animate-rise">
      <Card className="grid gap-0 md:grid-cols-[240px_minmax(0,1fr)]">
        <div className="border-b border-border p-4 sm:p-5 md:border-r md:border-b-0">
          <Icon className="mb-2 size-4 text-fg-subtle" aria-hidden />
          <h2 id={`${id}-titulo`} className="text-sm font-semibold text-fg">
            {title}
          </h2>
          {description ? <p className="mt-1 text-xs leading-relaxed text-fg-muted">{description}</p> : null}
        </div>
        <div className="min-w-0 p-4 sm:p-5">{children}</div>
      </Card>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Perfil
// ---------------------------------------------------------------------------
function ProfileForm() {
  const profile = useProfile();
  const { state } = useSession();
  const [name, setName] = useState('');
  useEffect(() => setName(profile.data?.display_name ?? ''), [profile.data?.display_name]);
  const save = useAction((db, displayName: string) => saveProfile(db, { display_name: displayName }), { success: 'Perfil salvo.' });
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(name);
      }}
    >
      {state.status === 'ready' && state.email ? (
        <Field label="E-mail da conta">
          <Input value={state.email} disabled readOnly />
        </Field>
      ) : null}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Field label="Nome de exibição" className="flex-1">
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Como você quer ser chamado(a)" />
        </Field>
        <Button type="submit" loading={save.isPending} disabled={name === (profile.data?.display_name ?? '')}>
          Salvar
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Anos letivos
// ---------------------------------------------------------------------------
function YearFormDialog({ open, onOpenChange, year }: { open: boolean; onOpenChange: (open: boolean) => void; year?: AcademicYear }) {
  const [seed, setSeed] = useState(true);
  const [activate, setActivate] = useState(true);
  const { register, handleSubmit, reset, formState } = useForm<AcademicYearInput, unknown, AcademicYearValues>({
    resolver: zodResolver(academicYearSchema),
  });
  useEffect(() => {
    if (open) {
      reset({ name: year?.name ?? '', start_date: year?.start_date ?? '', end_date: year?.end_date ?? '' });
      setSeed(true);
      setActivate(true);
    }
  }, [open, year, reset]);
  const save = useAction(
    async (db, values: AcademicYearValues) =>
      year ? updateAcademicYear(db, year.id, values) : (await createAcademicYear(db, values, { activate, seedOfficialSubjects: seed })).year,
    { success: year ? 'Ano letivo atualizado.' : 'Ano letivo criado.', onSuccess: () => onOpenChange(false) },
  );
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={year ? 'Editar ano letivo' : 'Novo ano letivo'}
      description={year ? undefined : 'Cada ano letivo tem suas próprias disciplinas, provas e materiais.'}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" type="submit" form="year-form" loading={save.isPending}>
            {year ? 'Salvar' : 'Criar ano letivo'}
          </Button>
        </>
      }
    >
      <form id="year-form" className="grid gap-4" onSubmit={handleSubmit((values) => save.mutate(values))} noValidate>
        <Field label="Nome" error={formState.errors.name?.message}>
          <Input autoFocus placeholder="Ex.: 2027" {...register('name')} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Início" optional error={formState.errors.start_date?.message}>
            <Input type="date" {...register('start_date')} />
          </Field>
          <Field label="Término" optional error={formState.errors.end_date?.message}>
            <Input type="date" {...register('end_date')} />
          </Field>
        </div>
        {!year ? (
          <div className="space-y-2 text-sm">
            <label className="flex items-center gap-2.5">
              <input type="checkbox" checked={activate} onChange={(e) => setActivate(e.target.checked)} className="size-4 accent-[var(--ce-accent)]" />
              Tornar este o ano letivo ativo
            </label>
            <label className="flex items-center gap-2.5">
              <input type="checkbox" checked={seed} onChange={(e) => setSeed(e.target.checked)} className="size-4 accent-[var(--ce-accent)]" />
              Cadastrar as 20 disciplinas oficiais
            </label>
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}

function YearsManager() {
  const { years, activeYear } = useWorkspace();
  const [dialog, setDialog] = useState<{ open: boolean; year?: AcademicYear }>({ open: false });
  const [deleting, setDeleting] = useState<AcademicYear | null>(null);
  const activate = useAction((db, id: string) => setActiveAcademicYear(db, id), { success: (y) => `Ano letivo "${y.name}" ativado.` });
  const seed = useAction((db, id: string) => seedOfficialSubjects(db, id), {
    success: (rows) => (rows.length ? `${rows.length} disciplinas oficiais cadastradas.` : 'Todas as disciplinas oficiais já estavam cadastradas.'),
  });
  const remove = useAction((db, id: string) => deleteAcademicYear(db, id), {
    success: 'Ano letivo excluído.',
    onSuccess: () => setDeleting(null),
  });

  return (
    <>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {years.map((year) => (
          <li key={year.id} className="flex items-center gap-3 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-medium text-fg">
                {year.name}
                {year.id === activeYear?.id ? (
                  <Badge tone="accent">
                    <Check aria-hidden /> Ativo
                  </Badge>
                ) : null}
              </p>
              <p className="mt-0.5 text-xs text-fg-subtle">
                {year.start_date || year.end_date
                  ? `${formatDate(year.start_date) || '…'} — ${formatDate(year.end_date) || '…'}`
                  : 'Período não informado'}
              </p>
            </div>
            {year.id !== activeYear?.id ? (
              <Button size="sm" onClick={() => activate.mutate(year.id)} loading={activate.isPending && activate.variables === year.id}>
                Ativar
              </Button>
            ) : null}
            <DropdownMenu>
              <DropdownMenuTrigger className="rounded-md p-1 text-fg-subtle hover:bg-surface-2 hover:text-fg" aria-label={`Ações do ano ${year.name}`}>
                <MoreHorizontal className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem icon={<Pencil />} onSelect={() => setDialog({ open: true, year })}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuItem icon={<Plus />} onSelect={() => seed.mutate(year.id)}>
                  Cadastrar disciplinas oficiais
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem icon={<Trash2 />} danger disabled={years.length === 1} onSelect={() => setDeleting(year)}>
                  Excluir ano letivo…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
        ))}
      </ul>
      <Button className="mt-3" onClick={() => setDialog({ open: true })}>
        <Plus /> Novo ano letivo
      </Button>
      <YearFormDialog open={dialog.open} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} year={dialog.year} />
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          title={`Excluir o ano letivo "${deleting.name}"?`}
          description="Todas as disciplinas, provas, conteúdos e materiais deste ano letivo serão apagados definitivamente. Faça um backup antes."
          confirmLabel="Excluir definitivamente"
          requireText={deleting.name}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting.id)}
        />
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Backup
// ---------------------------------------------------------------------------
function BackupTools() {
  const db = useBackend();
  const [exporting, setExporting] = useState<string | null>(null);
  const [pending, setPending] = useState<BackupBundle | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [wipeOpen, setWipeOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const doExport = async () => {
    setExporting('Preparando…');
    try {
      const { blob, backup } = await exportBackupArchive(db, (done, total) => setExporting(total ? `Arquivos ${done}/${total}` : 'Preparando…'));
      downloadBlob(blob, backupFileName());
      const total = Object.values(backup.counts).reduce((sum, n) => sum + (n ?? 0), 0);
      const missing = backup.missing_files?.length ?? 0;
      toast.success(`Backup exportado: ${total} registros e ${referencedFilePaths(backup).length - missing} arquivos.`);
      if (missing) toast.warning(`${missing} arquivo(s) não puderam ser lidos e ficaram fora do backup.`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setExporting(null);
    }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      setPending(await readBackupBundle(file));
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const runImport = useAction((backend, bundle: BackupBundle) => importBackup(backend, bundle), {
    onSuccess: (result) => {
      setPending(null);
      setReport(result);
      if (result.failed.length) toast.warning(`Importação concluída com ${result.failed.length} falha(s).`);
      else toast.success('Importação concluída.');
    },
  });

  const wipe = useAction(async (backend) => {
    if (backend instanceof LocalBackend) await backend.wipe();
  }, { success: 'Dados locais apagados.', onSuccess: () => setWipeOpen(false) });

  const summarize = (counts: Partial<Record<TableName, number>>) =>
    Object.entries(counts)
      .filter(([, n]) => n)
      .map(([table, n]) => `${n} ${FRIENDLY_TABLE_NAMES[table as TableName]}`)
      .join(' · ');

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-2/50 p-3 text-xs leading-relaxed text-fg-muted">
        {db.mode === 'local' ? (
          <>
            <HardDrive className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <p>
              <strong className="font-medium text-fg">Modo local.</strong> Os dados estão no banco do navegador (IndexedDB) deste
              dispositivo. Limpar os dados do navegador apaga tudo — exporte backups com frequência. Para usar a nuvem, configure o
              Supabase (veja <code className="font-mono">docs/CONFIGURACAO.md</code>) e importe o backup na conta nova.
            </p>
          </>
        ) : (
          <>
            <Cloud className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            <p>
              <strong className="font-medium text-fg">Nuvem (Supabase).</strong> Os dados ficam no PostgreSQL, protegidos por
              políticas de acesso por usuário. O backup é uma cópia extra sob o seu controle.
            </p>
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void doExport()} loading={Boolean(exporting)}>
          {exporting ? null : <Download />} {exporting ?? 'Exportar backup (.zip)'}
        </Button>
        <Button onClick={() => fileInput.current?.click()}>
          <Upload /> Importar backup
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".zip,application/zip,application/json,.json"
          className="hidden"
          aria-label="Arquivo de backup para importar"
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </div>
      <p className="text-[11px] leading-relaxed text-fg-subtle">
        O backup (.zip) inclui todos os registros e arquivos: PDFs, imagens e as fotos originais e tratadas do caderno. A importação
        nunca sobrescreve — registros que já existem são mantidos e apenas os ausentes são adicionados. Backups antigos (.json) também
        são aceitos.
      </p>

      {report ? (
        <div className="rounded-lg border border-border p-3 text-xs" role="status">
          <p className="font-medium text-fg">Resultado da importação</p>
          <p className="mt-1 text-fg-muted">Adicionados: {summarize(report.inserted) || 'nenhum registro'}</p>
          <p className="mt-0.5 text-fg-muted">Já existentes (mantidos): {summarize(report.skipped) || 'nenhum'}</p>
          <p className="mt-0.5 text-fg-muted">
            Arquivos enviados: {report.filesUploaded}
            {report.filesMissing ? ` · ${report.filesMissing} ausentes no backup` : ''}
          </p>
          {report.failed.length ? (
            <details className="mt-1 text-danger">
              <summary className="cursor-pointer">{report.failed.length} registro(s) não importado(s)</summary>
              <ul className="mt-1 list-disc pl-4 text-fg-muted">
                {report.failed.slice(0, 20).map((f) => (
                  <li key={`${f.table}-${f.id}`}>
                    {FRIENDLY_TABLE_NAMES[f.table]}: {f.message}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      {db.mode === 'local' ? (
        <div className="border-t border-border pt-4">
          <Button variant="danger-ghost" size="sm" onClick={() => setWipeOpen(true)}>
            <Trash2 /> Apagar todos os dados locais…
          </Button>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(pending)}
        onOpenChange={(open) => !open && setPending(null)}
        title="Importar este backup?"
        tone="primary"
        confirmLabel="Importar"
        loading={runImport.isPending}
        onConfirm={() => {
          if (pending) runImport.mutate(pending);
        }}
      >
        {pending ? (
          <div className="space-y-1 text-xs text-fg-muted">
            <p>
              Exportado em {formatDate(pending.backup.exported_at, "dd/MM/yyyy 'às' HH:mm")} (
              {pending.backup.source_mode === 'local' ? 'modo local' : 'nuvem'}).
            </p>
            <p>{summarize(pending.backup.counts) || 'Backup vazio.'}</p>
            <p>{pending.files.size ? `${pending.files.size} arquivos incluídos.` : 'Este backup não contém arquivos (somente dados).'}</p>
            <p className="pt-1 text-fg-subtle">Nada existente será sobrescrito.</p>
          </div>
        ) : null}
      </ConfirmDialog>

      <ConfirmDialog
        open={wipeOpen}
        onOpenChange={setWipeOpen}
        title="Apagar todos os dados locais?"
        description="Remove definitivamente todos os anos letivos, disciplinas, provas e arquivos deste navegador. Exporte um backup antes."
        confirmLabel="Apagar tudo"
        requireText="APAGAR TUDO"
        loading={wipe.isPending}
        onConfirm={() => wipe.mutate(undefined)}
      />
    </div>
  );
}

function StorageInfo() {
  const db = useBackend();
  const estimate = useQuery({
    queryKey: ['storage-estimate'],
    queryFn: () => navigator.storage?.estimate?.() ?? Promise.resolve(null),
    enabled: db.mode === 'local',
  });
  const mb = (n?: number) => (n === undefined ? '—' : `${(n / 1024 / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`);
  return (
    <div className="space-y-2 text-xs leading-relaxed text-fg-muted">
      {db.mode === 'local' ? (
        <p>
          Arquivos ficarão guardados no navegador. Espaço usado: <strong className="font-medium text-fg">{mb(estimate.data?.usage)}</strong>{' '}
          de aproximadamente {mb(estimate.data?.quota)} disponíveis.
        </p>
      ) : (
        <p className="flex gap-2">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          Arquivos ficam no bucket privado <code className="font-mono">materiais</code> do Supabase Storage, numa pasta exclusiva da sua
          conta, e são abertos por links temporários assinados.
        </p>
      )}
      <p className="text-fg-subtle">Limite de 50 MB por arquivo. Fotos do caderno guardam o original e a versão tratada.</p>
    </div>
  );
}

export function SettingsPage() {
  const { preference, setPreference } = useTheme();
  const location = useLocation();

  useEffect(() => {
    if (!location.hash) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [location.hash]);

  return (
    <>
      <PageHeader title="Configurações" description="Aparência, perfil, anos letivos, dados e integrações." />
      <div className="space-y-4">
        <Section id="aparencia" icon={Palette} title="Aparência" description="O tema escuro é o padrão.">
          <Segmented<ThemePreference>
            label="Tema"
            value={preference}
            onChange={setPreference}
            options={[
              { value: 'dark', label: 'Escuro' },
              { value: 'light', label: 'Claro' },
              { value: 'system', label: 'Seguir o sistema' },
            ]}
          />
        </Section>

        <Section id="perfil" icon={User} title="Perfil">
          <ProfileForm />
        </Section>

        <Section id="ano-letivo" icon={Database} title="Anos letivos" description="Organize períodos diferentes sem misturar disciplinas e provas.">
          <YearsManager />
        </Section>

        <Section id="dados" icon={Download} title="Dados e backup" description="Exportação, importação e segurança dos seus dados.">
          <BackupTools />
        </Section>

        <Section id="arquivos" icon={FolderOpen} title="Gerenciamento de arquivos">
          <StorageInfo />
        </Section>

        <Section id="ia" icon={Bot} title="Inteligência artificial" description="Integração com o Claude (Anthropic).">
          <div className="space-y-2 text-xs leading-relaxed text-fg-muted">
            <Badge tone="neutral">Não configurada</Badge>
            <p>
              A leitura de documentos e cadernos, a criação de resumos, flashcards e simulados com IA chegam na Fase 7. A chave da API
              ficará <strong className="font-medium text-fg">somente no servidor</strong> (variável de ambiente da Netlify), nunca no
              navegador, com registro de cada operação e controle de consumo.
            </p>
            <p className="text-fg-subtle">Antes disso, a Fase 4 trará o modo manual: exportar materiais, copiar prompts e importar resumos.</p>
          </div>
        </Section>

        <Section id="notificacoes" icon={Bell} title="Notificações">
          <p className="text-xs leading-relaxed text-fg-muted">Lembretes de provas e de sessões de estudo chegam com o Calendário, na Fase 6.</p>
        </Section>
      </div>
    </>
  );
}
