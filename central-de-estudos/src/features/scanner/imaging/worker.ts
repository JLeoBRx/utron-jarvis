/// <reference lib="webworker" />
import type { PageEdits } from '@/data/services/scans';
import { processPage } from './pipeline';

interface Request {
  id: number;
  width: number;
  height: number;
  buffer: ArrayBuffer;
  edits: PageEdits;
  maxSide: number;
}

self.onmessage = (event: MessageEvent<Request>) => {
  const { id, width, height, buffer, edits, maxSide } = event.data;
  try {
    const out = processPage({ width, height, data: new Uint8ClampedArray(buffer) }, edits, maxSide);
    const copy = out.data.slice();
    (self as unknown as DedicatedWorkerGlobalScope).postMessage(
      { id, ok: true, width: out.width, height: out.height, buffer: copy.buffer },
      [copy.buffer],
    );
  } catch (error) {
    (self as unknown as DedicatedWorkerGlobalScope).postMessage({ id, ok: false, message: (error as Error).message });
  }
};
