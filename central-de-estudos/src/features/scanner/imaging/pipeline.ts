import type { PageEdits } from '@/data/services/scans';
import { autoLevels, brightnessContrast, removeShadows, toBlackAndWhite } from './enhance';
import { cropToQuad, resizeRaster, rotateRaster, type RasterImage } from './raster';

/** Tamanho final das páginas tratadas: legível para leitura humana e por IA. */
export const PROCESSED_MAX_SIDE = 2400;
/** Tamanho das prévias durante a edição (rápido). */
export const PREVIEW_MAX_SIDE = 960;

/**
 * Aplica as edições na ordem: girar → recortar/corrigir perspectiva →
 * iluminação → brilho/contraste. Nunca altera a imagem de entrada.
 */
export function processPage(source: RasterImage, edits: PageEdits, maxSide: number): RasterImage {
  let img = rotateRaster(source, edits.rotation);
  img = edits.quad ? cropToQuad(img, edits.quad, maxSide) : resizeRaster(img, maxSide);
  switch (edits.enhance) {
    case 'realce':
      img = autoLevels(img);
      break;
    case 'documento':
      img = removeShadows(img);
      break;
    case 'pb':
      img = toBlackAndWhite(img);
      break;
    default:
      break;
  }
  return brightnessContrast(img, edits.brightness, edits.contrast);
}
