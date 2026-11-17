/**
 * Tipos de arquivo aceitos, validação de upload e utilitários de nomes.
 * O bucket "materiais" do Supabase aplica os mesmos limites no servidor.
 */

export const MAX_FILE_BYTES = 50 * 1024 * 1024; // 50 MB (igual ao bucket)

export type FileKind = 'pdf' | 'docx' | 'pptx' | 'txt' | 'imagem';

export interface FileTypeInfo {
  kind: FileKind;
  mime: string;
  extensions: string[];
  label: string;
}

/** Tipos aceitos na Biblioteca. */
export const LIBRARY_FILE_TYPES: FileTypeInfo[] = [
  { kind: 'pdf', mime: 'application/pdf', extensions: ['pdf'], label: 'PDF' },
  {
    kind: 'docx',
    mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    extensions: ['docx'],
    label: 'Word (DOCX)',
  },
  {
    kind: 'pptx',
    mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    extensions: ['pptx'],
    label: 'PowerPoint (PPTX)',
  },
  { kind: 'txt', mime: 'text/plain', extensions: ['txt'], label: 'Texto (TXT)' },
  { kind: 'imagem', mime: 'image/png', extensions: ['png'], label: 'Imagem PNG' },
  { kind: 'imagem', mime: 'image/jpeg', extensions: ['jpg', 'jpeg'], label: 'Imagem JPEG' },
  { kind: 'imagem', mime: 'image/webp', extensions: ['webp'], label: 'Imagem WEBP' },
];

/** Fotos aceitas pelo scanner (inclui HEIC/HEIF de iPhone, preservadas como original). */
export const SCANNER_IMAGE_TYPES: FileTypeInfo[] = [
  ...LIBRARY_FILE_TYPES.filter((t) => t.kind === 'imagem'),
  { kind: 'imagem', mime: 'image/heic', extensions: ['heic'], label: 'Imagem HEIC' },
  { kind: 'imagem', mime: 'image/heif', extensions: ['heif'], label: 'Imagem HEIF' },
];

/** Valor do atributo `accept` do seletor de arquivos da Biblioteca. */
export const LIBRARY_ACCEPT = [
  ...new Set(LIBRARY_FILE_TYPES.flatMap((t) => [t.mime, ...t.extensions.map((e) => `.${e}`)])),
].join(',');

export function fileExtension(name: string): string {
  const match = /\.([a-z0-9]+)$/i.exec(name.trim());
  return match ? match[1]!.toLowerCase() : '';
}

/**
 * Identifica o tipo pelo nome (extensão) e, na falta, pelo MIME informado pelo
 * navegador — alguns celulares enviam DOCX/PPTX sem MIME ou como octet-stream.
 */
export function detectFileType(
  file: { name: string; type?: string },
  allowed: FileTypeInfo[] = LIBRARY_FILE_TYPES,
): FileTypeInfo | null {
  const ext = fileExtension(file.name);
  const byExt = allowed.find((t) => t.extensions.includes(ext));
  if (byExt) return byExt;
  const mime = (file.type ?? '').toLowerCase();
  if (mime && mime !== 'application/octet-stream') return allowed.find((t) => t.mime === mime) ?? null;
  return null;
}

export type UploadCheck = { ok: true; type: FileTypeInfo } | { ok: false; reason: string };

export function checkUpload(
  file: { name: string; type?: string; size: number },
  allowed: FileTypeInfo[] = LIBRARY_FILE_TYPES,
): UploadCheck {
  const type = detectFileType(file, allowed);
  if (!type) {
    const names = [...new Set(allowed.flatMap((t) => t.extensions.map((e) => e.toUpperCase())))].join(', ');
    return { ok: false, reason: `Formato não aceito. Envie: ${names}.` };
  }
  if (file.size === 0) return { ok: false, reason: 'O arquivo está vazio.' };
  if (file.size > MAX_FILE_BYTES) return { ok: false, reason: `O arquivo tem ${formatBytes(file.size)}; o limite é 50 MB.` };
  return { ok: true, type };
}

/**
 * Nome seguro para o caminho no Storage: sem acentos, espaços ou símbolos.
 * O nome original continua salvo em `file_name` para exibição e download.
 */
export function storageSafeName(name: string): string {
  const ext = fileExtension(name);
  const base = (ext ? name.slice(0, -(ext.length + 1)) : name)
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '')
    .slice(0, 80);
  return `${base || 'arquivo'}${ext ? `.${ext}` : ''}`;
}

/** Título sugerido a partir do nome do arquivo. */
export function titleFromFileName(name: string): string {
  const ext = fileExtension(name);
  const base = ext ? name.slice(0, -(ext.length + 1)) : name;
  const title = base.replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim();
  return (title || 'Material sem nome').slice(0, 200);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: value < 10 ? 1 : 0 })} ${units[unit]}`;
}

export function extensionForMime(mime: string): string {
  const map: Record<string, string> = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/heic': 'heic',
    'image/heif': 'heif',
  };
  return map[mime] ?? 'bin';
}

/** Vídeo do YouTube → endereço de incorporação sem cookies (ou null). */
export function youtubeEmbedUrl(url: string): string | null {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\.|^m\./, '');
    let id: string | null = null;
    if (host === 'youtu.be') id = u.pathname.slice(1).split('/')[0] ?? null;
    else if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
      if (u.pathname === '/watch') id = u.searchParams.get('v');
      else if (/^\/(embed|shorts|live)\//.test(u.pathname)) id = u.pathname.split('/')[2] ?? null;
    }
    return id && /^[\w-]{6,20}$/.test(id) ? `https://www.youtube-nocookie.com/embed/${id}` : null;
  } catch {
    return null;
  }
}
