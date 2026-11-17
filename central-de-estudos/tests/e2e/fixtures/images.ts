/**
 * Imagens sintéticas para os testes (geradas em código — nenhuma foto real):
 * uma "foto de caderno" com a folha inclinada sobre a mesa, pautas e sombra.
 */
import { deflateSync } from 'node:zlib';
import { writeFileSync } from 'node:fs';
import { strToU8, zipSync } from 'fflate';

const CRC_TABLE = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Uint8Array): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), Buffer.from(data)]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

/** Codifica RGB (3 bytes/pixel) em PNG. */
export function encodePng(width: number, height: number, rgb: Uint8Array): Buffer {
  const raw = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 3 + 1)] = 0;
    Buffer.from(rgb.buffer, rgb.byteOffset + y * width * 3, width * 3).copy(raw, y * (width * 3 + 1) + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', new Uint8Array()),
  ]);
}

interface Pt {
  x: number;
  y: number;
}

/** Ponto dentro do quadrilátero → coordenadas (u, v) da folha, por bilinear inverso aproximado. */
function inside(p: Pt, q: [Pt, Pt, Pt, Pt]): { u: number; v: number } | null {
  // aproximação: resolve por busca em grade fina (suficiente para fixtures)
  const cross = (a: Pt, b: Pt, c: Pt) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  for (let i = 0; i < 4; i++) if (cross(q[i]!, q[(i + 1) % 4]!, p) < 0) return null;
  const top = { x: q[1].x - q[0].x, y: q[1].y - q[0].y };
  const left = { x: q[3].x - q[0].x, y: q[3].y - q[0].y };
  const det = top.x * left.y - top.y * left.x;
  const dx = p.x - q[0].x;
  const dy = p.y - q[0].y;
  return { u: (dx * left.y - dy * left.x) / det, v: (top.x * dy - top.y * dx) / det };
}

/** Foto sintética de uma página de caderno (RGB). `variant` muda o "texto". */
export function notebookPhotoRgb(width: number, height: number, variant = 0): Uint8Array {
  const rgb = new Uint8Array(width * height * 3);
  const q: [Pt, Pt, Pt, Pt] = [
    { x: width * 0.2, y: height * 0.1 },
    { x: width * 0.8, y: height * 0.07 },
    { x: width * 0.83, y: height * 0.92 },
    { x: width * 0.17, y: height * 0.94 },
  ];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 3;
      const t = inside({ x, y }, q);
      if (!t) {
        // mesa de madeira escura
        const wood = 60 + 12 * Math.sin(x / 9 + y / 40);
        rgb[i] = wood + 15;
        rgb[i + 1] = wood;
        rgb[i + 2] = wood - 15;
        continue;
      }
      const shade = 0.62 + 0.38 * Math.min(1, t.u * 1.4); // sombra à esquerda
      let r = 240;
      let g = 238;
      let b = 230;
      const line = (t.v * 24) % 1;
      if (line < 0.05 && t.v > 0.08) {
        r = 170;
        g = 195;
        b = 235; // pauta azul
      }
      const row = Math.floor(t.v * 24);
      const word = Math.floor(t.u * 14 + variant * 3 + row * 5) % 4;
      if (row >= 2 && row < 22 && line > 0.25 && line < 0.75 && t.u > 0.1 && t.u < 0.88 && word !== 0) {
        r = 30;
        g = 40;
        b = 110; // "escrita" em caneta azul
      }
      if (row === 1 && t.u > 0.12 && t.u < 0.5 && line > 0.2 && line < 0.8) {
        r = 200;
        g = 30;
        b = 40; // título em vermelho
      }
      rgb[i] = r * shade;
      rgb[i + 1] = g * shade;
      rgb[i + 2] = b * shade;
    }
  }
  return rgb;
}

export function notebookPng(width = 900, height = 1200, variant = 0): Buffer {
  return encodePng(width, height, notebookPhotoRgb(width, height, variant));
}

/** Vídeo Y4M (YUV 4:2:0) para a câmera falsa do Chromium. */
export function writeNotebookY4m(path: string, width = 640, height = 480, frames = 10): void {
  const rgb = notebookPhotoRgb(width, height, 1);
  const ySize = width * height;
  const cSize = (width / 2) * (height / 2);
  const frame = Buffer.alloc(ySize + 2 * cSize);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 3;
      const [r, g, b] = [rgb[i]!, rgb[i + 1]!, rgb[i + 2]!];
      // "C420jpeg" = YCbCr de faixa completa (JPEG/JFIF)
      frame[y * width + x] = Math.max(0, Math.min(255, 0.299 * r + 0.587 * g + 0.114 * b));
      if (y % 2 === 0 && x % 2 === 0) {
        const ci = (y / 2) * (width / 2) + x / 2;
        frame[ySize + ci] = Math.max(0, Math.min(255, 128 - 0.168736 * r - 0.331264 * g + 0.5 * b));
        frame[ySize + cSize + ci] = Math.max(0, Math.min(255, 128 + 0.5 * r - 0.418688 * g - 0.081312 * b));
      }
    }
  }
  const parts: Buffer[] = [Buffer.from(`YUV4MPEG2 W${width} H${height} F30:1 Ip A1:1 C420jpeg\n`, 'ascii')];
  for (let f = 0; f < frames; f++) parts.push(Buffer.from('FRAME\n', 'ascii'), frame);
  writeFileSync(path, Buffer.concat(parts));
}

/** PDF mínimo válido com uma página e um texto. */
export function minimalPdf(text = 'Central de Estudos - teste'): Buffer {
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    '',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  const stream = `BT /F1 14 Tf 20 100 Td (${text}) Tj ET`;
  objects[3] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) pdf += `${String(off).padStart(10, '0')} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, 'latin1');
}

/** DOCX mínimo válido (Word) com um parágrafo. */
export function minimalDocx(text = 'Resumo de Física: velocidade média'): Buffer {
  const files = {
    '[Content_Types].xml': strToU8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
    ),
    '_rels/.rels': strToU8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
    ),
    'word/_rels/document.xml.rels': strToU8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>',
    ),
    'word/document.xml': strToU8(
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>${text}</w:t></w:r></w:p></w:body></w:document>`,
    ),
  };
  return Buffer.from(zipSync(files));
}
