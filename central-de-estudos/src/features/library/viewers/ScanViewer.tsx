import { Bot, ClipboardCopy, Download, ImageOff } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { strToU8, zipSync, type Zippable } from 'fflate';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorState, Segmented, Skeleton } from '@/components/ui/misc';
import { useBackend } from '@/data/DataContext';
import { useScan, useStoredFile, useYearData } from '@/data/hooks';
import { manualReadingPrompt } from '@/data/ai/scanReading';
import type { Material, NotebookScanPage } from '@/data/types';
import { errorMessage } from '@/lib/errors';
import { extensionForMime, formatBytes } from '@/lib/files';
import { downloadBlob } from '@/lib/utils';

const SCAN_STATUS: Record<string, string> = {
  capturado: 'Aguardando leitura por IA',
  processando: 'Em leitura',
  aguardando_revisao: 'Aguardando sua conferência',
  revisado: 'Conferido',
  concluido: 'Concluído',
  erro: 'Erro na leitura',
};

function PageImage({ page, variant, total }: { page: NotebookScanPage; variant: 'tratada' | 'original'; total: number }) {
  const path = variant === 'tratada' ? (page.processed_path ?? page.original_path) : page.original_path;
  const file = useStoredFile(path);
  return (
    <figure className="overflow-hidden rounded-xl border border-border bg-surface-2" data-testid="scan-page">
      {file.isLoading ? (
        <Skeleton className="aspect-[3/4] w-full rounded-none" />
      ) : file.url ? (
        <a href={file.url} target="_blank" rel="noreferrer">
          <img src={file.url} alt={`Página ${page.position + 1} (${variant})`} className="mx-auto max-h-[80vh] w-full object-contain" />
        </a>
      ) : (
        <div className="flex aspect-[3/4] flex-col items-center justify-center gap-2 text-xs text-fg-subtle">
          <ImageOff className="size-5" aria-hidden />
          {variant === 'original' && page.original_mime_type?.includes('hei') ? 'Original em HEIC (baixe para ver)' : 'Imagem indisponível'}
        </div>
      )}
      <figcaption className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2 text-[11px] text-fg-subtle">
        <span className="font-medium text-fg-muted">
          Página {page.position + 1} de {total}
        </span>
        <span>
          {page.source === 'camera' ? 'Câmera' : 'Galeria'}
          {variant === 'tratada' && page.width ? ` · ${page.width}×${page.height}px` : ''}
          {variant === 'original' ? ` · ${formatBytes(page.original_size_bytes)}` : ` · ${formatBytes(page.processed_size_bytes)}`}
        </span>
      </figcaption>
    </figure>
  );
}

export function ScanViewer({ material }: { material: Material }) {
  const db = useBackend();
  const { subjectById, exams } = useYearData();
  const scan = useScan(material.scan_id);
  const [variant, setVariant] = useState<'tratada' | 'original'>('tratada');
  const [zipping, setZipping] = useState(false);

  if (scan.isLoading) return <Skeleton className="h-96 w-full rounded-xl" />;
  if (scan.error || !scan.data?.scan) return <ErrorState error={scan.error ?? new Error('Digitalização não encontrada.')} onRetry={() => void scan.refetch()} />;
  const { scan: info, pages } = scan.data;

  const downloadPages = async () => {
    setZipping(true);
    try {
      const entries: Zippable = {};
      for (const [i, page] of pages.entries()) {
        const path = variant === 'tratada' ? (page.processed_path ?? page.original_path) : page.original_path;
        const blob = await db.storage.download(path);
        const ext = variant === 'tratada' ? 'jpg' : extensionForMime(page.original_mime_type ?? 'image/jpeg');
        entries[`pagina-${String(i + 1).padStart(2, '0')}.${ext}`] = [new Uint8Array(await blob.arrayBuffer()), { level: 0 }];
      }
      entries['LEIA-ME.txt'] = strToU8(`${material.title}\n${pages.length} páginas (${variant === 'tratada' ? 'versões tratadas' : 'fotos originais'}).\n`);
      const zipped = zipSync(entries);
      downloadBlob(new Blob([zipped as Uint8Array<ArrayBuffer>], { type: 'application/zip' }), `${material.title.replace(/[^\w\- ]+/g, '').trim() || 'caderno'}.zip`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setZipping(false);
    }
  };

  const copyPrompt = async () => {
    const text = manualReadingPrompt({
      subjectName: subjectById.get(material.subject_id)?.name ?? '',
      examTitle: exams.find((e) => e.id === material.exam_id)?.title ?? null,
      topic: info.topic_label,
      pageCount: pages.length,
    });
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Instruções copiadas. Cole no Claude junto com as páginas baixadas.');
    } catch {
      toast.error('Não foi possível copiar automaticamente neste navegador.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-surface-2/50 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Bot className="size-4 text-fg-subtle" aria-hidden />
          <span className="text-sm font-medium text-fg">Leitura por IA</span>
          <Badge tone="neutral">{SCAN_STATUS[info.status] ?? info.status}</Badge>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-fg-muted">
          As fotos estão organizadas e prontas para leitura. O reconhecimento automático da escrita e a geração do resumo chegam
          na Fase 7. Enquanto isso, você pode usar o <strong className="font-medium text-fg">modo manual</strong>: baixe as páginas,
          copie as instruções e envie tudo ao Claude.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void downloadPages()} loading={zipping}>
            <Download /> Baixar páginas (.zip)
          </Button>
          <Button size="sm" onClick={() => void copyPrompt()}>
            <ClipboardCopy /> Copiar instruções de leitura
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-fg-subtle">{pages.length === 1 ? '1 página' : `${pages.length} páginas`}, na ordem do caderno</p>
        <Segmented
          label="Versão das páginas"
          value={variant}
          onChange={setVariant}
          options={[
            { value: 'tratada', label: 'Tratada' },
            { value: 'original', label: 'Original' },
          ]}
        />
      </div>
      <div className="grid gap-4">
        {pages.map((page) => (
          <PageImage key={`${page.id}-${variant}`} page={page} variant={variant} total={pages.length} />
        ))}
      </div>
    </div>
  );
}
