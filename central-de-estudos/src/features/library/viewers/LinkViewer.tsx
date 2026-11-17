import { ExternalLink } from 'lucide-react';
import type { Material } from '@/data/types';
import { youtubeEmbedUrl } from '@/lib/files';

export function LinkViewer({ material }: { material: Material }) {
  const url = material.url ?? '';
  const embed = youtubeEmbedUrl(url);
  let host = url;
  try {
    host = new URL(url).hostname.replace(/^www\./, '');
  } catch {
    /* mantém a URL */
  }
  return (
    <div className="space-y-4">
      {embed ? (
        <div className="aspect-video overflow-hidden rounded-xl border border-border bg-black">
          <iframe
            src={embed}
            title={material.title}
            className="h-full w-full"
            allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      ) : null}
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-2/50 p-4 transition-colors hover:border-border-strong"
      >
        <span className="min-w-0">
          <span className="block text-sm font-medium text-fg">{host}</span>
          <span className="block truncate text-xs text-fg-subtle">{url}</span>
        </span>
        <ExternalLink className="size-4 shrink-0 text-fg-subtle" aria-hidden />
      </a>
    </div>
  );
}
