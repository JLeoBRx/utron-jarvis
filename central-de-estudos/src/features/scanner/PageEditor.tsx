import * as RadixDialog from '@radix-ui/react-dialog';
import { Crop, Maximize, RotateCcw, RotateCw, ScanLine, Sparkles, Undo2, X } from 'lucide-react';
import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Segmented, Spinner } from '@/components/ui/misc';
import { DEFAULT_EDITS, type PageEdits } from '@/data/services/scans';
import { cn } from '@/lib/utils';
import { processInBackground, rasterToBlob } from './imaging/browser';
import { detectDocument } from './imaging/detect';
import { clamp01, FULL_QUAD, isConvexQuad, rotateQuad, type Quad } from './imaging/geometry';
import { rotateRaster, type RasterImage } from './imaging/raster';

const ENHANCE_OPTIONS: { value: PageEdits['enhance']; label: string }[] = [
  { value: 'original', label: 'Original' },
  { value: 'realce', label: 'Realçar' },
  { value: 'documento', label: 'Documento' },
  { value: 'pb', label: 'P&B' },
];

/** Quadrilátero com 4 alças arrastáveis (mouse, toque ou caneta; setas do teclado). */
function CropOverlay({ quad, onChange }: { quad: Quad; onChange: (quad: Quad) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const dragging = useRef<number | null>(null);

  const moveTo = (index: number, event: PointerEvent) => {
    const rect = box.current!.getBoundingClientRect();
    const next = [...quad] as Quad;
    next[index] = { x: clamp01((event.clientX - rect.left) / rect.width), y: clamp01((event.clientY - rect.top) / rect.height) };
    if (isConvexQuad(next)) onChange(next);
  };

  const points = quad.map((p) => `${p.x * 100},${p.y * 100}`);
  const labels = ['superior esquerdo', 'superior direito', 'inferior direito', 'inferior esquerdo'];
  return (
    <div ref={box} className="absolute inset-0 touch-none" data-testid="crop-overlay">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        <path d={`M0,0 H100 V100 H0 Z M${points.join(' L')} Z`} fill="rgb(0 0 0 / 0.45)" fillRule="evenodd" />
        <polygon points={points.join(' ')} fill="none" stroke="var(--ce-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      {quad.map((p, i) => (
        <button
          key={i}
          type="button"
          role="slider"
          aria-label={`Canto ${labels[i]}`}
          aria-valuetext={`${Math.round(p.x * 100)}%, ${Math.round(p.y * 100)}%`}
          className="absolute flex size-11 -translate-x-1/2 -translate-y-1/2 cursor-grab items-center justify-center active:cursor-grabbing"
          style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
          onPointerDown={(event) => {
            dragging.current = i;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => dragging.current === i && moveTo(i, event)}
          onPointerUp={() => (dragging.current = null)}
          onPointerCancel={() => (dragging.current = null)}
          onKeyDown={(event) => {
            const step = event.shiftKey ? 0.05 : 0.01;
            const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
            if (!delta) return;
            event.preventDefault();
            const next = [...quad] as Quad;
            next[i] = { x: clamp01(p.x + delta[0]!), y: clamp01(p.y + delta[1]!) };
            if (isConvexQuad(next)) onChange(next);
          }}
        >
          <span className="size-5 rounded-full border-2 border-accent bg-white shadow-pop" />
        </button>
      ))}
    </div>
  );
}

interface PageEditorProps {
  open: boolean;
  pageNumber: number;
  total: number;
  initialEdits: PageEdits;
  loadSource: () => Promise<RasterImage>;
  onCancel: () => void;
  onSave: (edits: PageEdits) => void;
}

export function PageEditor({ open, pageNumber, total, initialEdits, loadSource, onCancel, onSave }: PageEditorProps) {
  const [edits, setEdits] = useState<PageEdits>(initialEdits);
  const [view, setView] = useState<'recorte' | 'resultado'>('resultado');
  const [source, setSource] = useState<RasterImage | null>(null);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  // Montado uma vez por página (key = id da página): carrega a imagem-base.
  const loader = useRef(loadSource);
  useEffect(() => {
    void loader.current().then(setSource).catch(() => toast.error('Não foi possível abrir esta página.'));
  }, []);

  // Imagem-base (girada) para posicionar o recorte.
  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    let url: string | null = null;
    void rasterToBlob(rotateRaster(source, edits.rotation), 'image/jpeg', 0.85).then((blob) => {
      if (cancelled) return;
      url = URL.createObjectURL(blob);
      setBaseUrl(url);
    });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [source, edits.rotation]);

  // Resultado (com espera curta para não reprocessar a cada movimento).
  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    let url: string | null = null;
    setProcessing(true);
    const timer = window.setTimeout(() => {
      void processInBackground(source, edits, 1200)
        .then((out) => rasterToBlob(out, 'image/jpeg', 0.85))
        .then((blob) => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setResultUrl(url);
          setProcessing(false);
        })
        .catch(() => !cancelled && setProcessing(false));
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (url) URL.revokeObjectURL(url);
    };
  }, [source, edits]);

  const rotate = (direction: 'esquerda' | 'direita') => {
    const delta = direction === 'direita' ? 90 : 270;
    setEdits((e) => ({
      ...e,
      rotation: (((e.rotation + delta) % 360) as PageEdits['rotation']),
      quad: e.quad ? rotateQuad(e.quad, delta) : null,
    }));
  };

  const detect = () => {
    if (!source) return;
    const found = detectDocument(rotateRaster(source, edits.rotation));
    if (found && found.confidence >= 0.5) {
      setEdits((e) => ({ ...e, quad: found.quad }));
      setView('recorte');
      toast.success('Página detectada. Ajuste os cantos se precisar.');
    } else {
      toast.message('Não foi possível detectar as bordas com segurança. Arraste os cantos manualmente.');
      setEdits((e) => ({ ...e, quad: e.quad ?? FULL_QUAD }));
      setView('recorte');
    }
  };

  const quad = edits.quad ?? FULL_QUAD;

  return (
    <RadixDialog.Root open={open} onOpenChange={(o) => !o && onCancel()}>
      <RadixDialog.Portal>
        <RadixDialog.Content className="fixed inset-0 z-50 flex flex-col bg-bg outline-none" aria-describedby={undefined}>
          <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2.5 pt-[max(env(safe-area-inset-top),0.625rem)] sm:px-5">
            <button type="button" onClick={onCancel} className="rounded-lg p-1.5 text-fg-muted hover:bg-surface-2 hover:text-fg" aria-label="Cancelar edição">
              <X className="size-5" />
            </button>
            <RadixDialog.Title className="text-sm font-semibold">
              Editar página {pageNumber} de {total}
            </RadixDialog.Title>
            <Button variant="primary" size="sm" onClick={() => onSave(edits)}>
              Aplicar
            </Button>
          </div>

          <div className="flex justify-center border-b border-border px-3 py-2">
            <Segmented
              label="Visualização"
              value={view}
              onChange={setView}
              options={[
                { value: 'recorte', label: 'Recorte' },
                { value: 'resultado', label: 'Resultado' },
              ]}
            />
          </div>

          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-surface-2 p-4">
            {!source ? (
              <Spinner label="Abrindo página…" />
            ) : view === 'recorte' ? (
              baseUrl ? (
                <div className="relative inline-block max-h-full max-w-full">
                  <img src={baseUrl} alt="Página para recortar" className="block max-h-[calc(100dvh-300px)] max-w-full select-none" draggable={false} />
                  <CropOverlay quad={quad} onChange={(q) => setEdits((e) => ({ ...e, quad: q }))} />
                </div>
              ) : (
                <Spinner />
              )
            ) : resultUrl ? (
              <img
                src={resultUrl}
                alt="Resultado da página"
                className={cn('block max-h-[calc(100dvh-300px)] max-w-full shadow-pop transition-opacity', processing && 'opacity-70')}
                data-testid="editor-result"
              />
            ) : (
              <Spinner />
            )}
            {processing && view === 'resultado' && resultUrl ? (
              <span className="absolute top-3 right-3 rounded-md bg-elevated/90 px-2 py-1 text-[11px] text-fg-muted shadow-card">Processando…</span>
            ) : null}
          </div>

          <div className="space-y-3 border-t border-border px-3 pt-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] sm:px-5">
            <div className="flex flex-wrap items-center justify-center gap-1.5">
              <Button size="sm" variant="ghost" onClick={() => rotate('esquerda')} aria-label="Girar para a esquerda">
                <RotateCcw /> <span className="hidden sm:inline">Girar</span>
              </Button>
              <Button size="sm" variant="ghost" onClick={() => rotate('direita')} aria-label="Girar para a direita">
                <RotateCw /> <span className="hidden sm:inline">Girar</span>
              </Button>
              <Button size="sm" variant="ghost" onClick={detect} disabled={!source}>
                <ScanLine /> Detectar página
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEdits((e) => ({ ...e, quad: e.quad ?? FULL_QUAD }));
                  setView('recorte');
                }}
              >
                <Crop /> Recortar
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEdits((e) => ({ ...e, quad: null }))} disabled={!edits.quad}>
                <Maximize /> Página inteira
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEdits({ ...DEFAULT_EDITS })}>
                <Undo2 /> Restaurar
              </Button>
            </div>
            <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-fg-subtle" aria-hidden />
                <Segmented label="Iluminação" value={edits.enhance} onChange={(v) => setEdits((e) => ({ ...e, enhance: v }))} options={ENHANCE_OPTIONS} />
              </div>
              <label className="flex items-center gap-2 text-xs text-fg-muted">
                Brilho
                <input
                  type="range"
                  min={-50}
                  max={50}
                  value={edits.brightness}
                  onChange={(e) => setEdits((s) => ({ ...s, brightness: Number(e.target.value) }))}
                  className="w-28 accent-[var(--ce-accent)]"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-fg-muted">
                Contraste
                <input
                  type="range"
                  min={-50}
                  max={50}
                  value={edits.contrast}
                  onChange={(e) => setEdits((s) => ({ ...s, contrast: Number(e.target.value) }))}
                  className="w-28 accent-[var(--ce-accent)]"
                />
              </label>
            </div>
            <p className="text-center text-[11px] text-fg-subtle">A foto original é sempre preservada; estes ajustes geram a versão tratada.</p>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
