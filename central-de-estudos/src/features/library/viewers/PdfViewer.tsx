import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useEffect, useRef, useState } from 'react';
import { Spinner } from '@/components/ui/misc';

/** Uma página: só é desenhada quando aparece na tela (PDFs grandes não travam o celular). */
function PdfPage({ doc, number }: { doc: PDFDocumentProxy; number: number }) {
  const holder = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [ratio, setRatio] = useState(1.414);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: '600px 0px' });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let task: { cancel: () => void; promise: Promise<void> } | null = null;
    void doc.getPage(number).then((page) => {
      if (cancelled || !canvas.current || !holder.current) return;
      const base = page.getViewport({ scale: 1 });
      setRatio(base.height / base.width);
      const cssWidth = holder.current.clientWidth || base.width;
      const scale = (cssWidth / base.width) * Math.min(2, window.devicePixelRatio || 1);
      const viewport = page.getViewport({ scale });
      canvas.current.width = Math.floor(viewport.width);
      canvas.current.height = Math.floor(viewport.height);
      task = page.render({ canvas: canvas.current, viewport });
      task.promise.catch(() => undefined);
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [visible, doc, number]);

  return (
    <div ref={holder} className="relative w-full overflow-hidden rounded-md bg-white shadow-card" style={{ aspectRatio: `1 / ${ratio}` }}>
      <canvas ref={canvas} className="block h-full w-full" aria-label={`Página ${number}`} />
      <span className="absolute right-2 bottom-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white tabular">{number}</span>
    </div>
  );
}

export default function PdfViewer({ blob }: { blob: Blob }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let task: { destroy: () => Promise<void> } | null = null;
    (async () => {
      const [pdfjs, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')]);
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
      const loading = pdfjs.getDocument({ data: new Uint8Array(await blob.arrayBuffer()) });
      task = loading;
      const loaded = await loading.promise;
      if (!cancelled) setDoc(loaded);
    })().catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [blob]);

  if (error) return <p className="p-6 text-center text-sm text-danger">Não foi possível exibir o PDF: {error}</p>;
  if (!doc) return <div className="flex justify-center p-10"><Spinner label="Carregando PDF…" /></div>;
  return (
    <div className="space-y-3" data-testid="pdf-viewer">
      <p className="text-xs text-fg-subtle">{doc.numPages === 1 ? '1 página' : `${doc.numPages} páginas`}</p>
      {Array.from({ length: doc.numPages }, (_, i) => (
        <PdfPage key={i} doc={doc} number={i + 1} />
      ))}
    </div>
  );
}
