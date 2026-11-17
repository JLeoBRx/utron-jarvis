import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, FilePlus2, Loader2, UploadCloud, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Dialog } from '@/components/ui/Dialog';
import { Field } from '@/components/ui/Field';
import { Input, Select, Textarea } from '@/components/ui/Input';
import { useBackend } from '@/data/DataContext';
import { scopeKey, useAction, useYearData } from '@/data/hooks';
import { linkSchema, materialMetaSchema } from '@/data/schemas';
import {
  collectMaterialFilePaths,
  createLinkMaterial,
  deleteMaterial,
  toUploadSource,
  updateMaterialMeta,
  uploadMaterialFile,
} from '@/data/services/materials';
import type { Material, MaterialCategory } from '@/data/types';
import { errorMessage } from '@/lib/errors';
import { checkUpload, formatBytes, LIBRARY_ACCEPT, titleFromFileName } from '@/lib/files';
import { CATEGORY_LABELS, MATERIAL_CATEGORY_LABELS } from '@/lib/labels';
import { cn, pluralize } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';

export const CATEGORY_OPTIONS = Object.entries(MATERIAL_CATEGORY_LABELS) as [MaterialCategory, string][];

// ---------------------------------------------------------------------------
// Disciplina → prova (a prova depende da disciplina: nunca mistura avaliações)
// ---------------------------------------------------------------------------
export interface Placement {
  subject_id: string;
  exam_id: string;
}

export function SubjectExamFields({
  value,
  onChange,
  errors,
  lockSubject,
}: {
  value: Placement;
  onChange: (value: Placement) => void;
  errors?: { subject_id?: string; exam_id?: string };
  lockSubject?: boolean;
}) {
  const { subjects, exams } = useYearData();
  const available = subjects.filter((s) => !s.archived_at || s.id === value.subject_id);
  const subjectExams = exams.filter((e) => e.subject_id === value.subject_id);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Disciplina" error={errors?.subject_id} hint={lockSubject ? 'Cadernos digitalizados não mudam de disciplina.' : undefined}>
        <Select
          value={value.subject_id}
          disabled={lockSubject}
          onChange={(e) => onChange({ subject_id: e.target.value, exam_id: '' })}
        >
          <option value="">Selecione…</option>
          {(['formacao_geral', 'formacao_tecnica'] as const).map((category) => (
            <optgroup key={category} label={CATEGORY_LABELS[category]}>
              {available
                .filter((s) => s.category === category)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </optgroup>
          ))}
        </Select>
      </Field>
      <Field
        label="Prova relacionada"
        optional
        error={errors?.exam_id}
        hint={value.subject_id && !subjectExams.length ? 'Esta disciplina ainda não tem provas.' : undefined}
      >
        <Select value={value.exam_id} disabled={!value.subject_id} onChange={(e) => onChange({ ...value, exam_id: e.target.value })}>
          <option value="">Material geral da disciplina</option>
          {subjectExams.map((exam) => (
            <option key={exam.id} value={exam.id}>
              {exam.title}
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );
}

function fieldErrors(error: unknown): Record<string, string> {
  const issues = (error as { issues?: { path: (string | number)[]; message: string }[] }).issues ?? [];
  const out: Record<string, string> = {};
  for (const issue of issues) {
    const key = String(issue.path[0] ?? '');
    out[key] ??= issue.message;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Envio de arquivos
// ---------------------------------------------------------------------------
type ItemStatus = 'pronto' | 'enviando' | 'enviado' | 'erro' | 'invalido';
interface UploadItem {
  key: string;
  file: File;
  title: string;
  status: ItemStatus;
  message?: string;
}

let itemCounter = 0;
function toItem(file: File): UploadItem {
  const check = checkUpload(file);
  return {
    key: `${Date.now()}-${itemCounter++}`,
    file,
    title: titleFromFileName(file.name),
    status: check.ok ? 'pronto' : 'invalido',
    message: check.ok ? undefined : check.reason,
  };
}

export function UploadDialog({
  open,
  onOpenChange,
  defaultSubjectId,
  defaultExamId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSubjectId?: string;
  defaultExamId?: string;
}) {
  const db = useBackend();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [placement, setPlacement] = useState<Placement>({ subject_id: '', exam_id: '' });
  const [category, setCategory] = useState<MaterialCategory>('slides');
  const [origin, setOrigin] = useState('');
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setItems([]);
    setPlacement({ subject_id: defaultSubjectId ?? '', exam_id: defaultExamId ?? '' });
    setCategory('slides');
    setOrigin('');
    setDescription('');
    setErrors({});
  }, [open, defaultSubjectId, defaultExamId]);

  const addFiles = (list: FileList | File[] | null) => {
    if (!list?.length) return;
    setItems((current) => [...current, ...Array.from(list).map(toItem)]);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  };

  const pendingItems = items.filter((i) => i.status === 'pronto' || i.status === 'erro');
  const sent = items.filter((i) => i.status === 'enviado').length;

  const submit = async () => {
    const base = { ...placement, category, origin, description, title: 'x' };
    const parsed = materialMetaSchema.safeParse(base);
    if (!parsed.success) {
      setErrors(fieldErrors(parsed.error));
      return;
    }
    setErrors({});
    setBusy(true);
    let ok = 0;
    for (const item of pendingItems) {
      setItems((cur) => cur.map((i) => (i.key === item.key ? { ...i, status: 'enviando', message: undefined } : i)));
      try {
        await uploadMaterialFile(db, { ...base, title: item.title.trim() || titleFromFileName(item.file.name) }, toUploadSource(item.file));
        ok++;
        setItems((cur) => cur.map((i) => (i.key === item.key ? { ...i, status: 'enviado' } : i)));
      } catch (error) {
        setItems((cur) => cur.map((i) => (i.key === item.key ? { ...i, status: 'erro', message: errorMessage(error) } : i)));
      }
    }
    setBusy(false);
    await queryClient.invalidateQueries({ queryKey: scopeKey(db) });
    const failed = pendingItems.length - ok;
    if (ok) toast.success(`${pluralize(ok, 'material enviado', 'materiais enviados')}.`);
    if (!failed) onOpenChange(false);
    else toast.error(`${pluralize(failed, 'arquivo não foi enviado', 'arquivos não foram enviados')}. Veja os detalhes e tente novamente.`);
  };

  const statusIcon = (status: ItemStatus) => {
    if (status === 'enviando') return <Loader2 className="size-4 animate-spin text-accent-text" aria-label="Enviando" />;
    if (status === 'enviado') return <CheckCircle2 className="size-4 text-success" aria-label="Enviado" />;
    if (status === 'erro' || status === 'invalido') return <AlertCircle className="size-4 text-danger" aria-label="Erro" />;
    return null;
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !busy && onOpenChange(next)}
      title="Enviar materiais"
      description="PDF, Word (DOCX), PowerPoint (PPTX), TXT ou imagens (PNG, JPG, WEBP) — até 50 MB cada."
      size="lg"
      modalLocked={items.length > 0}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {sent && !pendingItems.length ? 'Fechar' : 'Cancelar'}
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} disabled={!pendingItems.length}>
            {pendingItems.length > 1 ? `Enviar ${pendingItems.length} arquivos` : 'Enviar'}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center transition-colors',
            dragging ? 'border-accent bg-accent-soft' : 'border-border-strong bg-surface-2/40',
          )}
        >
          <UploadCloud className="size-6 text-fg-subtle" aria-hidden />
          <p className="text-sm text-fg">Arraste os arquivos para cá</p>
          <Button size="sm" onClick={() => input.current?.click()} disabled={busy}>
            <FilePlus2 /> Escolher arquivos
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept={LIBRARY_ACCEPT}
            className="hidden"
            aria-label="Arquivos para enviar"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = '';
            }}
          />
        </div>

        {items.length ? (
          <ul className="divide-y divide-border rounded-xl border border-border" aria-label="Arquivos selecionados">
            {items.map((item) => (
              <li key={item.key} className="flex items-start gap-3 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <Input
                    value={item.title}
                    aria-label={`Nome do material ${item.file.name}`}
                    disabled={item.status === 'enviando' || item.status === 'enviado' || item.status === 'invalido'}
                    onChange={(e) => setItems((cur) => cur.map((i) => (i.key === item.key ? { ...i, title: e.target.value } : i)))}
                    className="h-8 text-[13px]"
                    maxLength={200}
                  />
                  <p className="mt-1 truncate text-[11px] text-fg-subtle">
                    {item.file.name} · {formatBytes(item.file.size)}
                  </p>
                  {item.message ? <p className="mt-0.5 text-[11px] text-danger">{item.message}</p> : null}
                </div>
                <div className="mt-2 flex items-center gap-1">
                  {statusIcon(item.status)}
                  {item.status !== 'enviando' && item.status !== 'enviado' ? (
                    <button
                      type="button"
                      onClick={() => setItems((cur) => cur.filter((i) => i.key !== item.key))}
                      className="rounded p-0.5 text-fg-subtle hover:text-fg"
                      aria-label={`Remover ${item.file.name} da lista`}
                    >
                      <X className="size-4" />
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        <SubjectExamFields value={placement} onChange={setPlacement} errors={errors} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Categoria">
            <Select value={category} onChange={(e) => setCategory(e.target.value as MaterialCategory)}>
              {CATEGORY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Origem" optional hint="Ex.: professor, livro, site, colega." error={errors.origin}>
            <Input value={origin} onChange={(e) => setOrigin(e.target.value)} maxLength={200} />
          </Field>
        </div>
        <Field label="Descrição" optional error={errors.description}>
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
        </Field>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Link
// ---------------------------------------------------------------------------
export function LinkDialog({
  open,
  onOpenChange,
  defaultSubjectId,
  defaultExamId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSubjectId?: string;
  defaultExamId?: string;
}) {
  const [placement, setPlacement] = useState<Placement>({ subject_id: '', exam_id: '' });
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<MaterialCategory>('complementares');
  const [origin, setOrigin] = useState('');
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setPlacement({ subject_id: defaultSubjectId ?? '', exam_id: defaultExamId ?? '' });
    setUrl('');
    setTitle('');
    setCategory('complementares');
    setOrigin('');
    setDescription('');
    setErrors({});
  }, [open, defaultSubjectId, defaultExamId]);

  const save = useAction((db, values: Parameters<typeof createLinkMaterial>[1]) => createLinkMaterial(db, values), {
    success: 'Link adicionado à biblioteca.',
    onSuccess: () => onOpenChange(false),
  });

  const submit = () => {
    const values = { ...placement, url, title, category, origin, description };
    const parsed = linkSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrors(parsed.error));
      return;
    }
    setErrors({});
    save.mutate(values);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Adicionar link"
      description="Vídeo-aulas, sites, simuladores e outros materiais on-line."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={submit} loading={save.isPending}>
            Adicionar link
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Endereço (URL)" error={errors.url}>
          <Input type="url" inputMode="url" autoFocus placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
        </Field>
        <Field label="Nome" error={errors.title}>
          <Input placeholder="Ex.: Vídeo-aula sobre velocidade média" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </Field>
        <SubjectExamFields value={placement} onChange={setPlacement} errors={errors} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Categoria">
            <Select value={category} onChange={(e) => setCategory(e.target.value as MaterialCategory)}>
              {CATEGORY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Origem" optional>
            <Input value={origin} onChange={(e) => setOrigin(e.target.value)} maxLength={200} />
          </Field>
        </div>
        <Field label="Descrição" optional>
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
        </Field>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Edição dos dados do material
// ---------------------------------------------------------------------------
export function MaterialMetaDialog({ material, open, onOpenChange }: { material: Material; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [placement, setPlacement] = useState<Placement>({ subject_id: material.subject_id, exam_id: material.exam_id ?? '' });
  const [title, setTitle] = useState(material.title);
  const [category, setCategory] = useState<MaterialCategory>(material.category);
  const [origin, setOrigin] = useState(material.origin ?? '');
  const [description, setDescription] = useState(material.description ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setPlacement({ subject_id: material.subject_id, exam_id: material.exam_id ?? '' });
    setTitle(material.title);
    setCategory(material.category);
    setOrigin(material.origin ?? '');
    setDescription(material.description ?? '');
    setErrors({});
  }, [open, material]);

  const save = useAction((db, values: Parameters<typeof updateMaterialMeta>[2]) => updateMaterialMeta(db, material, values), {
    success: 'Material atualizado.',
    onSuccess: () => onOpenChange(false),
  });

  const submit = () => {
    const values = { ...placement, title, category, origin, description };
    const parsed = materialMetaSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrors(parsed.error));
      return;
    }
    setErrors({});
    save.mutate(values);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Editar material"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={submit} loading={save.isPending}>
            Salvar
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Nome" error={errors.title}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </Field>
        <SubjectExamFields value={placement} onChange={setPlacement} errors={errors} lockSubject={material.kind === 'digitalizacao'} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Categoria">
            <Select value={category} onChange={(e) => setCategory(e.target.value as MaterialCategory)}>
              {CATEGORY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Origem" optional>
            <Input value={origin} onChange={(e) => setOrigin(e.target.value)} maxLength={200} />
          </Field>
        </div>
        <Field label="Descrição" optional>
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
        </Field>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Exclusão
// ---------------------------------------------------------------------------
export function DeleteMaterialDialog({
  material,
  open,
  onOpenChange,
  onDeleted,
}: {
  material: Material;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const db = useBackend();
  const files = useQuery({
    queryKey: [...scopeKey(db), 'material-files', material.id],
    queryFn: () => collectMaterialFilePaths(db, material),
    enabled: open,
    staleTime: 0,
  });
  const remove = useAction((backend) => deleteMaterial(backend, material), {
    success: 'Material excluído.',
    onSuccess: () => {
      onOpenChange(false);
      onDeleted?.();
    },
  });
  const count = files.data?.length ?? 0;
  const detail = useMemo(() => {
    if (material.kind === 'link') return 'O link será removido da biblioteca.';
    if (material.kind === 'digitalizacao') return `As fotografias deste caderno (${pluralize(count, 'arquivo', 'arquivos')}, originais e tratadas) serão apagadas definitivamente.`;
    return count > 1
      ? `O arquivo atual e ${pluralize(count - 1, 'versão anterior', 'versões anteriores')} serão apagados definitivamente.`
      : 'O arquivo será apagado definitivamente.';
  }, [material.kind, count]);

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Excluir "${material.title}"?`}
      description="Esta ação não pode ser desfeita."
      confirmLabel="Excluir definitivamente"
      loading={remove.isPending}
      onConfirm={() => remove.mutate(undefined)}
    >
      <p className="rounded-lg border border-danger/25 bg-danger-soft p-3 text-xs text-fg-muted">{detail}</p>
    </ConfirmDialog>
  );
}
