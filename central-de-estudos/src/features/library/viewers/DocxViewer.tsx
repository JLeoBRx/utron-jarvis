import { useEffect, useRef, useState } from 'react';
import { Spinner } from '@/components/ui/misc';

export default function DocxViewer({ blob }: { blob: Blob }) {
  const body = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    void import('docx-preview')
      .then(({ renderAsync }) => {
        if (!body.current) return;
        body.current.innerHTML = '';
        return renderAsync(blob, body.current, undefined, { inWrapper: true, breakPages: true, ignoreLastRenderedPageBreak: true });
      })
      .then(() => !cancelled && setStatus('ready'))
      .catch(() => !cancelled && setStatus('error'));
    return () => {
      cancelled = true;
    };
  }, [blob]);

  return (
    <div data-testid="docx-viewer">
      {status === 'loading' ? (
        <div className="flex justify-center p-10">
          <Spinner label="Carregando documento…" />
        </div>
      ) : null}
      {status === 'error' ? (
        <p className="p-6 text-center text-sm text-fg-muted">Não foi possível exibir este documento aqui. Use “Baixar” para abri-lo no seu aparelho.</p>
      ) : null}
      <div ref={body} className="overflow-x-auto rounded-lg bg-surface-3 [&_.docx-wrapper]:bg-transparent [&_.docx-wrapper]:p-3 [&_section.docx]:mb-3 [&_section.docx]:shadow-card" />
    </div>
  );
}
