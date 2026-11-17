/**
 * Ponte entre o navegador e o processamento: decodificar fotos (respeitando a
 * orientação EXIF), converter para RasterImage, processar no Web Worker e
 * codificar em JPEG.
 */
import { AppError } from '@/lib/errors';
import type { PageEdits } from '@/data/services/scans';
import { processPage } from './pipeline';
import type { RasterImage } from './raster';

type Drawable = ImageBitmap | HTMLImageElement;

export async function decodeImage(blob: Blob): Promise<Drawable> {
  try {
    return await createImageBitmap(blob, { imageOrientation: 'from-image' });
  } catch {
    const url = URL.createObjectURL(blob);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } catch {
      throw new AppError(
        'validation',
        'Não foi possível abrir esta imagem neste navegador. Se for uma foto HEIC do iPhone, escolha “Mais compatível” nas configurações da câmera ou envie em JPEG.',
      );
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

function sizeOf(source: Drawable): { width: number; height: number } {
  return 'naturalWidth' in source ? { width: source.naturalWidth, height: source.naturalHeight } : { width: source.width, height: source.height };
}

/** Desenha a imagem em RasterImage limitada a `maxSide` (o redimensionamento do canvas é rápido). */
export function toRaster(source: Drawable, maxSide: number): RasterImage {
  const { width, height } = sizeOf(source);
  const scale = Math.min(1, maxSide / Math.max(width, height));
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) throw new AppError('unknown', 'Seu navegador não permite processar imagens.');
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(source, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  return { width: w, height: h, data };
}

export async function blobToRaster(blob: Blob, maxSide: number): Promise<RasterImage> {
  const image = await decodeImage(blob);
  try {
    return toRaster(image, maxSide);
  } finally {
    if ('close' in image) image.close();
  }
}

export function rasterToBlob(img: RasterImage, type = 'image/jpeg', quality = 0.88): Promise<Blob> {
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new AppError('unknown', 'Seu navegador não permite processar imagens.');
  ctx.putImageData(new ImageData(new Uint8ClampedArray(img.data), img.width, img.height), 0, 0);
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new AppError('unknown', 'Falha ao gerar a imagem.'))), type, quality),
  );
}

// ---------------------------------------------------------------------------
// Web Worker (com alternativa na thread principal)
// ---------------------------------------------------------------------------
let worker: Worker | null | undefined;
let nextId = 1;
const pending = new Map<number, { resolve: (img: RasterImage) => void; reject: (error: Error) => void }>();

function getWorker(): Worker | null {
  if (worker !== undefined) return worker;
  try {
    worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (event: MessageEvent) => {
      const msg = event.data as { id: number; ok: boolean; width: number; height: number; buffer: ArrayBuffer; message?: string };
      const entry = pending.get(msg.id);
      if (!entry) return;
      pending.delete(msg.id);
      if (msg.ok) entry.resolve({ width: msg.width, height: msg.height, data: new Uint8ClampedArray(msg.buffer) });
      else entry.reject(new AppError('unknown', `Falha ao processar a imagem: ${msg.message}`));
    };
    worker.onerror = () => {
      for (const entry of pending.values()) entry.reject(new AppError('unknown', 'Falha no processamento de imagem.'));
      pending.clear();
      worker = null;
    };
  } catch {
    worker = null;
  }
  return worker;
}

export function processInBackground(source: RasterImage, edits: PageEdits, maxSide: number): Promise<RasterImage> {
  const w = getWorker();
  if (!w) return Promise.resolve(processPage(source, edits, maxSide));
  const id = nextId++;
  const copy = source.data.slice();
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    w.postMessage({ id, width: source.width, height: source.height, buffer: copy.buffer, edits, maxSide }, [copy.buffer]);
  });
}
