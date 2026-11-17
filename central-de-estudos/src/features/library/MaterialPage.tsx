import { Download, ExternalLink, History, MoreHorizontal, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { SubjectTag } from '@/components/domain/SubjectTag';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/DropdownMenu';
import { ErrorState, Skeleton } from '@/components/ui/misc';
import { useBackend } from '@/data/DataContext';
import { useAction, useMaterial, useMaterialVersions, useYearData } from '@/data/hooks';
import { replaceMaterialFile, toUploadSource } from '@/data/services/materials';
import type { Material, MaterialVersion } from '@/data/types';
import { subjectColorStyle } from '@/lib/colors';
import { formatDate } from '@/lib/dates';
import { errorMessage } from '@/lib/errors';
import { checkUpload, formatBytes, LIBRARY_ACCEPT } from '@/lib/files';
import { MATERIAL_CATEGORY_LABELS } from '@/lib/labels';
import { downloadBlob } from '@/lib/utils';
import { NotFoundPage } from '../modules/NotFoundPage';
import { DeleteMaterialDialog, MaterialMetaDialog } from './MaterialDialogs';
import { KIND_INFO, MaterialIcon, visualKind } from './materialKind';
import { FileViewer } from './viewers/FileViewer';
import { LinkViewer } from './viewers/LinkViewer';
import { ScanViewer } from './viewers/ScanViewer';

function useFileDownload() {
  const db = useBackend();
  const [busy, setBusy] = useState<string | null>(null);
  const download = async (path: string, name: string) => {
    setBusy(path);
    try {
      downloadBlob(await db.storage.download(path), name);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };
  const open = async (path: string) => {
    // Abre a aba já, para não ser bloqueada como pop-up; depois carrega a URL.
    const tab = window.open('', '_blank');
    try {
      const url = await db.storage.getUrl(path, 600);
      if (tab) tab.location.href = url;
      else window.location.href = url;
    } catch (error) {
      tab?.close();
      toast.error(errorMessage(error));
    }
  };
  return { download, open, busy };
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 break-words text-fg-muted">{children}</dd>
    </div>
  );
}

function VersionsCard({ material, versions }: { material: Material; versions: MaterialVersion[] }) {
  const { download, busy } = useFileDownload();
  return (
    <Card>
      <CardHeader title="Versões anteriores" icon={<History />} description="Arquivos substituídos ficam preservados." />
      {versions.length ? (
        <ul className="divide-y divide-border border-t border-border" aria-label="Versões anteriores">
          {versions.map((v) => (
            <li key={v.id} className="flex items-center gap-3 px-4 py-2.5 text-xs sm:px-5">
              <Badge tone="outline">v{v.version_number}</Badge>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-fg">{v.file_name}</span>
                <span className="text-fg-subtle">
                  {formatBytes(v.size_bytes)} · substituída em {formatDate(v.replaced_at, "dd/MM/yyyy 'às' HH:mm")}
                </span>
              </span>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={`Baixar versão ${v.version_number}`}
                loading={busy === v.storage_path}
                onClick={() => void download(v.storage_path, v.file_name)}
              >
                {busy === v.storage_path ? null : <Download />}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 pb-4 text-xs text-fg-subtle sm:px-5">Este é o arquivo original (versão {material.version}).</p>
      )}
    </Card>
  );
}

export function MaterialPage() {
  const { materialId } = useParams();
  const navigate = useNavigate();
  const material = useMaterial(materialId);
  const versions = useMaterialVersions(material.data?.kind === 'arquivo' ? materialId : undefined);
  const { subjectById, exams } = useYearData();
  const { download, open, busy } = useFileDownload();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [replacement, setReplacement] = useState<File | null>(null);
  const replaceInput = useRef<HTMLInputElement>(null);

  const replace = useAction((db, args: { material: Material; file: File }) => replaceMaterialFile(db, args.material, toUploadSource(args.file)), {
    success: (m) => `Arquivo substituído. A versão anterior foi preservada (agora na versão ${m.version}).`,
    onSuccess: () => setReplacement(null),
  });

  if (material.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (material.error) return <ErrorState error={material.error} onRetry={() => void material.refetch()} />;
  const m = material.data;
  if (!m) return <NotFoundPage message="Este material não existe ou foi excluído." />;

  const subject = subjectById.get(m.subject_id);
  const exam = exams.find((e) => e.id === m.exam_id);
  const kind = KIND_INFO[visualKind(m)];

  const onReplacementChosen = (file: File | undefined) => {
    if (replaceInput.current) replaceInput.current.value = '';
    if (!file) return;
    const check = checkUpload(file);
    if (!check.ok) {
      toast.error(check.reason);
      return;
    }
    setReplacement(file);
  };

  return (
    <div style={subjectColorStyle(subject?.color)} className="sc">
      <PageHeader
        breadcrumbs={[
          { label: 'Biblioteca', to: '/biblioteca' },
          ...(subject ? [{ label: subject.name, to: `/biblioteca?disciplina=${subject.id}` }] : []),
          { label: m.title },
        ]}
        eyebrow={
          <div className="flex flex-wrap items-center gap-2">
            <SubjectTag subject={subject} link />
            {exam ? (
              <Link to={`/provas/${exam.id}/materiais`} className="text-xs text-fg-muted hover:text-fg">
                · {exam.title}
              </Link>
            ) : (
              <span className="text-xs text-fg-subtle">· Material geral da disciplina</span>
            )}
            <Badge tone="neutral">{MATERIAL_CATEGORY_LABELS[m.category]}</Badge>
          </div>
        }
        title={
          <span className="flex items-center gap-3">
            <MaterialIcon material={m} size="lg" />
            <span className="min-w-0 break-words">{m.title}</span>
          </span>
        }
        actions={
          <>
            {m.kind === 'arquivo' && m.storage_path ? (
              <>
                <Button onClick={() => void open(m.storage_path!)}>
                  <ExternalLink /> Abrir
                </Button>
                <Button onClick={() => void download(m.storage_path!, m.file_name ?? m.title)} loading={busy === m.storage_path}>
                  {busy === m.storage_path ? null : <Download />} Baixar
                </Button>
              </>
            ) : null}
            <Button onClick={() => setEditing(true)}>
              <Pencil /> Editar
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                className="inline-flex size-8.5 items-center justify-center rounded-lg border border-border bg-surface-2 text-fg-muted hover:text-fg"
                aria-label="Mais ações"
              >
                <MoreHorizontal className="size-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {m.kind === 'arquivo' ? (
                  <DropdownMenuItem icon={<RefreshCw />} onSelect={() => replaceInput.current?.click()}>
                    Substituir arquivo…
                  </DropdownMenuItem>
                ) : null}
                {m.kind === 'arquivo' ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem icon={<Trash2 />} danger onSelect={() => setDeleting(true)}>
                  Excluir material…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <input
              ref={replaceInput}
              type="file"
              accept={LIBRARY_ACCEPT}
              className="hidden"
              aria-label="Novo arquivo para substituir"
              onChange={(e) => onReplacementChosen(e.target.files?.[0])}
            />
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="min-w-0 animate-rise p-3 sm:p-4">
          {m.kind === 'digitalizacao' ? <ScanViewer material={m} /> : m.kind === 'link' ? <LinkViewer material={m} /> : <FileViewer key={m.storage_path} material={m} />}
        </Card>

        <div className="flex flex-col gap-6">
          <Card className="animate-rise">
            <CardHeader title="Detalhes" />
            <dl className="space-y-3 px-4 pb-4 text-xs sm:px-5">
              <Detail label="Tipo">{kind.label}</Detail>
              {m.file_name ? <Detail label="Arquivo">{m.file_name}</Detail> : null}
              {m.kind !== 'link' ? <Detail label="Tamanho">{formatBytes(m.size_bytes)}</Detail> : null}
              <Detail label="Enviado em">{formatDate(m.created_at, "dd/MM/yyyy 'às' HH:mm")}</Detail>
              {m.replaced_at ? <Detail label="Última substituição">{formatDate(m.replaced_at, "dd/MM/yyyy 'às' HH:mm")}</Detail> : null}
              {m.kind === 'arquivo' ? <Detail label="Versão">{m.version}</Detail> : null}
              <Detail label="Origem">{m.origin ?? <span className="text-fg-subtle">Não informada</span>}</Detail>
              {m.description ? <Detail label="Descrição"><span className="whitespace-pre-line">{m.description}</span></Detail> : null}
            </dl>
          </Card>
          {m.kind === 'arquivo' ? <VersionsCard material={m} versions={versions.data ?? []} /> : null}
        </div>
      </div>

      <MaterialMetaDialog material={m} open={editing} onOpenChange={setEditing} />
      <DeleteMaterialDialog material={m} open={deleting} onOpenChange={setDeleting} onDeleted={() => navigate('/biblioteca', { replace: true })} />
      <ConfirmDialog
        open={Boolean(replacement)}
        onOpenChange={(o) => !o && setReplacement(null)}
        title="Substituir o arquivo?"
        tone="primary"
        confirmLabel="Substituir"
        loading={replace.isPending}
        onConfirm={() => {
          if (replacement) replace.mutate({ material: m, file: replacement });
        }}
      >
        <div className="space-y-2 text-xs text-fg-muted">
          <p>
            Novo arquivo: <strong className="text-fg">{replacement?.name}</strong> ({formatBytes(replacement?.size)})
          </p>
          <p className="rounded-lg bg-surface-2 p-2.5">
            O arquivo atual (<strong className="text-fg">{m.file_name}</strong>, versão {m.version}) <strong className="text-fg">não será apagado</strong>: ele
            continuará disponível em “Versões anteriores”.
          </p>
        </div>
      </ConfirmDialog>
    </div>
  );
}
