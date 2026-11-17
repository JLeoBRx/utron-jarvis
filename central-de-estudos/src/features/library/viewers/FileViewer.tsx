import { FileWarning, Presentation } from 'lucide-react';
import { lazy, Suspense, useEffect, useState } from 'react';
import { ErrorState, Spinner } from '@/components/ui/misc';
import { useStoredFile } from '@/data/hooks';
import type { Material } from '@/data/types';
import { visualKind } from '../materialKind';

const PdfViewer = lazy(() => import('./PdfViewer'));
const DocxViewer = lazy(() => import('./DocxViewer'));

function TextContent({ blob }: { blob: Blob }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    void blob.text().then(setText);
  }, [blob]);
  return (
    <pre className="max-h-[75vh] overflow-auto rounded-lg bg-surface-2 p-4 font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-fg">
      {text ?? '…'}
    </pre>
  );
}

/** Mostra o conteúdo do arquivo atual de um material. */
export function FileViewer({ material }: { material: Material }) {
  const file = useStoredFile(material.storage_path);
  const kind = visualKind(material);

  if (file.isLoading) {
    return (
      <div className="flex justify-center p-10">
        <Spinner label="Carregando arquivo…" />
      </div>
    );
  }
  if (file.error || !file.data) {
    return <ErrorState error={file.error ?? new Error('Arquivo não encontrado no armazenamento.')} onRetry={() => void file.refetch()} />;
  }

  const fallback = (
    <div className="flex justify-center p-10">
      <Spinner />
    </div>
  );

  switch (kind) {
    case 'pdf':
      return (
        <Suspense fallback={fallback}>
          <PdfViewer blob={file.data} />
        </Suspense>
      );
    case 'docx':
      return (
        <Suspense fallback={fallback}>
          <DocxViewer blob={file.data} />
        </Suspense>
      );
    case 'imagem':
      return (
        <a href={file.url ?? undefined} target="_blank" rel="noreferrer" className="block">
          <img src={file.url ?? undefined} alt={material.title} className="mx-auto max-h-[75vh] rounded-lg object-contain" />
        </a>
      );
    case 'txt':
      return <TextContent blob={file.data} />;
    case 'pptx':
      return (
        <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <Presentation className="size-8 text-fg-subtle" aria-hidden />
          <p className="max-w-sm text-sm text-fg-muted">
            Apresentações do PowerPoint não podem ser exibidas com segurança dentro do navegador. Use <strong className="text-fg">Baixar</strong>{' '}
            para abrir no seu aparelho — o arquivo continua guardado aqui.
          </p>
        </div>
      );
    default:
      return (
        <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <FileWarning className="size-8 text-fg-subtle" aria-hidden />
          <p className="text-sm text-fg-muted">Pré-visualização indisponível para este tipo de arquivo.</p>
        </div>
      );
  }
}
