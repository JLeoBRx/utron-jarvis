import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { DEFAULT_EDITS, type PageEdits, type ScanPageUpload } from '@/data/services/scans';
import { errorMessage } from '@/lib/errors';
import { checkUpload, detectFileType, SCANNER_IMAGE_TYPES } from '@/lib/files';
import { newId } from '@/lib/ids';
import {
  clearDraft,
  loadDraft,
  removeDraftPage,
  saveDraftOrder,
  saveDraftPage,
  updateDraftPage,
  type DraftMeta,
  type DraftPage,
} from './draftStore';
import { blobToRaster, processInBackground, rasterToBlob } from './imaging/browser';
import { detectDocument } from './imaging/detect';
import { PROCESSED_MAX_SIDE } from './imaging/pipeline';
import type { RasterImage } from './imaging/raster';

/** Resolução da imagem-base usada nas prévias e no editor (rápida no celular). */
export const EDITOR_SOURCE_MAX = 1400;
/** Resolução de leitura do original para o processamento final. */
const FINAL_SOURCE_MAX = 3200;
const PREVIEW_OUTPUT_MAX = 1000;
/** Só aplica o recorte automático quando a detecção é confiável. */
const AUTO_CROP_CONFIDENCE = 0.75;

export interface ScannerPageState extends DraftPage {
  status: 'processando' | 'pronto' | 'erro';
  error?: string;
  previewUrl?: string;
  previewWidth?: number;
  previewHeight?: number;
}

export interface IncomingImage {
  blob: Blob;
  name: string;
  source: 'camera' | 'galeria';
}

export function useScannerPages(owner: string) {
  const [pages, setPages] = useState<ScannerPageState[]>([]);
  // Fonte de verdade síncrona (o estado do React é atualizado a partir dela).
  const pagesRef = useRef<ScannerPageState[]>([]);
  const commit = useCallback((fn: (current: ScannerPageState[]) => ScannerPageState[]) => {
    pagesRef.current = fn(pagesRef.current);
    setPages(pagesRef.current);
  }, []);
  const [loaded, setLoaded] = useState(false);
  const [restoredCount, setRestoredCount] = useState(0);
  const [draftMeta, setDraftMeta] = useState<DraftMeta | null>(null);
  const rasters = useRef(new Map<string, RasterImage>());
  const urls = useRef(new Set<string>());

  const sourceRaster = useCallback(async (page: Pick<DraftPage, 'id' | 'original'>): Promise<RasterImage> => {
    const cached = rasters.current.get(page.id);
    if (cached) return cached;
    const raster = await blobToRaster(page.original, EDITOR_SOURCE_MAX);
    rasters.current.set(page.id, raster);
    return raster;
  }, []);

  const renderPreview = useCallback(
    async (page: DraftPage) => {
      try {
        const raster = await sourceRaster(page);
        const out = await processInBackground(raster, page.edits, PREVIEW_OUTPUT_MAX);
        const blob = await rasterToBlob(out, 'image/jpeg', 0.82);
        const url = URL.createObjectURL(blob);
        urls.current.add(url);
        commit((current) =>
          current.map((p) => {
            if (p.id !== page.id) return p;
            if (p.previewUrl) {
              URL.revokeObjectURL(p.previewUrl);
              urls.current.delete(p.previewUrl);
            }
            return { ...p, status: 'pronto', error: undefined, previewUrl: url, previewWidth: out.width, previewHeight: out.height };
          }),
        );
      } catch (error) {
        commit((current) => current.map((p) => (p.id === page.id ? { ...p, status: 'erro', error: errorMessage(error) } : p)));
      }
    },
    [commit, sourceRaster],
  );

  // Recupera o rascunho salvo no aparelho.
  useEffect(() => {
    let cancelled = false;
    void loadDraft(owner).then(({ pages: draft, meta }) => {
      if (cancelled) return;
      setDraftMeta(meta);
      commit(() => draft.map((p) => ({ ...p, status: 'processando' })));
      setRestoredCount(draft.length);
      setLoaded(true);
      for (const page of draft) void renderPreview(page);
    });
    return () => {
      cancelled = true;
    };
  }, [owner, renderPreview, commit]);

  // Libera a memória das prévias ao sair.
  useEffect(
    () => () => {
      for (const url of urls.current) URL.revokeObjectURL(url);
    },
    [],
  );

  const addImages = useCallback(
    async (images: IncomingImage[]) => {
      for (const image of images) {
        const check = checkUpload({ name: image.name, type: image.blob.type, size: image.blob.size }, SCANNER_IMAGE_TYPES);
        if (!check.ok) {
          toast.error(`${image.name}: ${check.reason}`);
          continue;
        }
        const mime = image.blob.type || detectFileType({ name: image.name }, SCANNER_IMAGE_TYPES)?.mime || 'image/jpeg';
        const page: DraftPage = {
          id: newId(),
          original: image.blob,
          originalMime: mime,
          originalName: image.name,
          source: image.source,
          edits: { ...DEFAULT_EDITS },
        };
        // posição crescente; reordenações reescrevem 0, 1, 2…
        const position = Date.now() * 100 + (pagesRef.current.length % 100);
        commit((current) => [...current, { ...page, status: 'processando' }]);
        try {
          const raster = await sourceRaster(page);
          const detection = detectDocument(raster);
          if (detection && detection.confidence >= AUTO_CROP_CONFIDENCE) page.edits = { ...page.edits, quad: detection.quad };
          commit((current) => current.map((p) => (p.id === page.id ? { ...p, edits: page.edits } : p)));
        } catch (error) {
          commit((current) => current.map((p) => (p.id === page.id ? { ...p, status: 'erro', error: errorMessage(error) } : p)));
        }
        await saveDraftPage(owner, page, position).catch(() => undefined);
        await renderPreview(page);
      }
    },
    [owner, renderPreview, sourceRaster, commit],
  );

  const updateEdits = useCallback(
    (id: string, edits: PageEdits) => {
      commit((current) => current.map((p) => (p.id === id ? { ...p, edits, status: 'processando' } : p)));
      const target = pagesRef.current.find((p) => p.id === id);
      void updateDraftPage(id, { edits }).catch(() => undefined);
      if (target) void renderPreview(target);
    },
    [renderPreview, commit],
  );

  const remove = useCallback((id: string) => {
    commit((current) => {
      const page = current.find((p) => p.id === id);
      if (page?.previewUrl) URL.revokeObjectURL(page.previewUrl);
      const next = current.filter((p) => p.id !== id);
      void saveDraftOrder(next.map((p) => p.id)).catch(() => undefined);
      return next;
    });
    rasters.current.delete(id);
    void removeDraftPage(id).catch(() => undefined);
  }, [commit]);

  const move = useCallback((id: string, direction: -1 | 1) => {
    commit((current) => {
      const index = current.findIndex((p) => p.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target]!, next[index]!];
      void saveDraftOrder(next.map((p) => p.id)).catch(() => undefined);
      return next;
    });
  }, [commit]);

  const reset = useCallback(async () => {
    for (const url of urls.current) URL.revokeObjectURL(url);
    urls.current.clear();
    rasters.current.clear();
    commit(() => []);
    setRestoredCount(0);
    await clearDraft(owner).catch(() => undefined);
  }, [owner, commit]);

  /** Gera as versões finais (alta resolução) para salvar. O original segue intocado. */
  const buildUploads = useCallback(async (onProgress?: (done: number, total: number) => void): Promise<ScanPageUpload[]> => {
    const pages = pagesRef.current;
    const result: ScanPageUpload[] = [];
    for (const [index, page] of pages.entries()) {
      onProgress?.(index, pages.length);
      const raster = await blobToRaster(page.original, FINAL_SOURCE_MAX);
      const out = await processInBackground(raster, page.edits, PROCESSED_MAX_SIDE);
      const processed = await rasterToBlob(out, 'image/jpeg', 0.88);
      result.push({
        id: page.id,
        source: page.source,
        original: page.original,
        originalName: page.originalName,
        originalMime: page.originalMime,
        processed,
        width: out.width,
        height: out.height,
        edits: page.edits,
      });
    }
    onProgress?.(pages.length, pages.length);
    return result;
  }, []);

  return { pages, loaded, restoredCount, draftMeta, addImages, updateEdits, remove, move, reset, sourceRaster, buildUploads };
}
