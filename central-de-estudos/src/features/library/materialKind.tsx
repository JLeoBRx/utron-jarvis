import { File, FileImage, FileText, FileType2, Link2, MonitorPlay, NotebookPen, Presentation, type LucideIcon } from 'lucide-react';
import type { Material } from '@/data/types';
import { detectFileType, youtubeEmbedUrl } from '@/lib/files';
import { cn } from '@/lib/utils';

export type MaterialVisualKind = 'pdf' | 'docx' | 'pptx' | 'txt' | 'imagem' | 'link' | 'video' | 'caderno' | 'outro';

export function visualKind(material: Pick<Material, 'kind' | 'file_name' | 'mime_type' | 'url'>): MaterialVisualKind {
  if (material.kind === 'digitalizacao') return 'caderno';
  if (material.kind === 'link') return material.url && youtubeEmbedUrl(material.url) ? 'video' : 'link';
  const type = detectFileType({ name: material.file_name ?? '', type: material.mime_type ?? '' });
  return type?.kind ?? 'outro';
}

export const KIND_INFO: Record<MaterialVisualKind, { label: string; icon: LucideIcon; tone: string }> = {
  pdf: { label: 'PDF', icon: FileText, tone: 'text-[#e5484d] bg-[#e5484d]/10' },
  docx: { label: 'Word', icon: FileType2, tone: 'text-[#3e7bfa] bg-[#3e7bfa]/10' },
  pptx: { label: 'PowerPoint', icon: Presentation, tone: 'text-[#f76b15] bg-[#f76b15]/10' },
  txt: { label: 'Texto', icon: FileText, tone: 'text-fg-muted bg-surface-3' },
  imagem: { label: 'Imagem', icon: FileImage, tone: 'text-[#30a46c] bg-[#30a46c]/10' },
  link: { label: 'Link', icon: Link2, tone: 'text-[#0d9ad1] bg-[#0d9ad1]/10' },
  video: { label: 'Vídeo', icon: MonitorPlay, tone: 'text-[#e5484d] bg-[#e5484d]/10' },
  caderno: { label: 'Caderno', icon: NotebookPen, tone: 'text-accent-text bg-accent-soft' },
  outro: { label: 'Arquivo', icon: File, tone: 'text-fg-muted bg-surface-3' },
};

export function MaterialIcon({ material, size = 'md' }: { material: Pick<Material, 'kind' | 'file_name' | 'mime_type' | 'url'>; size?: 'sm' | 'md' | 'lg' }) {
  const info = KIND_INFO[visualKind(material)];
  const Icon = info.icon;
  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center rounded-lg',
        info.tone,
        size === 'sm' ? 'size-7 [&_svg]:size-3.5' : size === 'lg' ? 'size-11 [&_svg]:size-5' : 'size-9 [&_svg]:size-4',
      )}
      aria-hidden
    >
      <Icon />
    </span>
  );
}
