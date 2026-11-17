import { Camera, CameraOff, Check, Flashlight, FlashlightOff, ImagePlus, RefreshCw, SwitchCamera, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export type CameraState = 'iniciando' | 'ativa' | 'negada' | 'indisponivel' | 'em_uso' | 'inseguro' | 'erro';

interface CameraCaptureProps {
  pageCount: number;
  lastThumbnail?: string;
  onCapture: (blob: Blob) => void;
  onDone: () => void;
  /** Alternativas quando a câmera do navegador não está disponível. */
  onUseSystemCamera: () => void;
  onUseGallery: () => void;
}

interface TorchCapabilities extends MediaTrackCapabilities {
  torch?: boolean;
}

/** Traduz o erro do getUserMedia em um estado com orientação clara. */
export function cameraErrorState(error: unknown): CameraState {
  const name = (error as { name?: string })?.name ?? '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') return 'negada';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') return 'indisponivel';
  if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') return 'em_uso';
  return 'erro';
}

const MESSAGES: Record<Exclude<CameraState, 'iniciando' | 'ativa'>, { title: string; body: string }> = {
  negada: {
    title: 'Permissão da câmera negada',
    body: 'Para fotografar por aqui, libere a câmera para este site. No Android (Chrome): toque no cadeado ao lado do endereço → Permissões → Câmera → Permitir. No iPhone (Safari): toque em “aA” → Configurações do site → Câmera → Permitir. Depois, toque em “Tentar novamente”.',
  },
  indisponivel: {
    title: 'Nenhuma câmera encontrada',
    body: 'Este aparelho não tem câmera disponível para o navegador. Você pode escolher fotos da galeria.',
  },
  em_uso: {
    title: 'A câmera está em uso',
    body: 'Outro aplicativo (ou outra aba) está usando a câmera. Feche-o e tente novamente.',
  },
  inseguro: {
    title: 'Câmera do navegador indisponível',
    body: 'O navegador só libera a câmera em conexões seguras (HTTPS). Use a câmera do sistema ou a galeria — funciona do mesmo jeito.',
  },
  erro: {
    title: 'Não foi possível abrir a câmera',
    body: 'Tente novamente ou use a câmera do sistema.',
  },
};

export function CameraCapture({ pageCount, lastThumbnail, onCapture, onDone, onUseSystemCamera, onUseGallery }: CameraCaptureProps) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>('iniciando');
  const [facing, setFacing] = useState<'environment' | 'user'>('environment');
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [canSwitch, setCanSwitch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const stop = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState('iniciando');
    setTorchOn(false);
    (async () => {
      if (!window.isSecureContext) return setState('inseguro');
      if (!navigator.mediaDevices?.getUserMedia) return setState('indisponivel');
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: facing }, width: { ideal: 3264 }, height: { ideal: 2448 } },
        });
        if (cancelled) {
          media.getTracks().forEach((t) => t.stop());
          return;
        }
        stream.current = media;
        const track = media.getVideoTracks()[0];
        const caps = (track?.getCapabilities?.() ?? {}) as TorchCapabilities;
        setTorchAvailable(Boolean(caps.torch));
        const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
        setCanSwitch(devices.filter((d) => d.kind === 'videoinput').length > 1);
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play().catch(() => undefined);
        }
        setState('ativa');
      } catch (error) {
        if (!cancelled) setState(cameraErrorState(error));
      }
    })();
    return () => {
      cancelled = true;
      stop();
    };
  }, [facing, attempt, stop]);

  const toggleTorch = async () => {
    const track = stream.current?.getVideoTracks()[0];
    if (!track) return;
    try {
      await track.applyConstraints({ advanced: [{ torch: !torchOn } as MediaTrackConstraintSet] });
      setTorchOn(!torchOn);
    } catch {
      setTorchAvailable(false);
    }
  };

  const capture = async () => {
    const el = video.current;
    const track = stream.current?.getVideoTracks()[0];
    if (!el || !track || busy) return;
    setBusy(true);
    setFlash(true);
    window.setTimeout(() => setFlash(false), 180);
    try {
      let blob: Blob | null = null;
      // Foto em resolução máxima quando o navegador oferece (Chrome/Android).
      const ImageCaptureCtor = (window as unknown as { ImageCapture?: new (t: MediaStreamTrack) => { takePhoto: () => Promise<Blob> } }).ImageCapture;
      if (ImageCaptureCtor && !torchOn) {
        try {
          blob = await new ImageCaptureCtor(track).takePhoto();
        } catch {
          blob = null;
        }
      }
      if (!blob) {
        const canvas = document.createElement('canvas');
        canvas.width = el.videoWidth;
        canvas.height = el.videoHeight;
        canvas.getContext('2d')?.drawImage(el, 0, 0, canvas.width, canvas.height);
        blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
      }
      if (blob) onCapture(blob);
    } finally {
      setBusy(false);
    }
  };

  const message = state !== 'iniciando' && state !== 'ativa' ? MESSAGES[state] : null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black text-white" role="dialog" aria-modal="true" aria-label="Câmera">
      <div className="flex items-center justify-between gap-2 px-3 pt-[max(env(safe-area-inset-top),0.75rem)] pb-2">
        <button type="button" onClick={onDone} className="rounded-full p-2 hover:bg-white/10" aria-label="Fechar câmera">
          <X className="size-5" />
        </button>
        <span className="text-sm font-medium tabular" aria-live="polite">
          {pageCount === 0 ? 'Enquadre a primeira página' : `${pageCount} ${pageCount === 1 ? 'página' : 'páginas'}`}
        </span>
        <div className="flex items-center gap-1">
          {torchAvailable ? (
            <button type="button" onClick={() => void toggleTorch()} className="rounded-full p-2 hover:bg-white/10" aria-label={torchOn ? 'Desligar lanterna' : 'Ligar lanterna'} aria-pressed={torchOn}>
              {torchOn ? <Flashlight className="size-5" /> : <FlashlightOff className="size-5" />}
            </button>
          ) : null}
          {canSwitch && state === 'ativa' ? (
            <button
              type="button"
              onClick={() => setFacing((f) => (f === 'environment' ? 'user' : 'environment'))}
              className="rounded-full p-2 hover:bg-white/10"
              aria-label="Trocar câmera"
            >
              <SwitchCamera className="size-5" />
            </button>
          ) : null}
        </div>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        <video
          ref={video}
          playsInline
          muted
          autoPlay
          className={cn('absolute inset-0 h-full w-full object-contain', state !== 'ativa' && 'invisible')}
          data-testid="camera-video"
        />
        {state === 'ativa' ? (
          <div className="pointer-events-none absolute inset-[8%] rounded-2xl border-2 border-white/60 shadow-[0_0_0_9999px_rgb(0_0_0/0.25)]" aria-hidden>
            <p className="absolute -bottom-8 left-0 right-0 text-center text-xs text-white/80">Enquadre a página inteira, com boa luz</p>
          </div>
        ) : null}
        {flash ? <div className="absolute inset-0 bg-white/70" aria-hidden /> : null}
        {state === 'iniciando' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-white/80" role="status">
            <Camera className="size-8 animate-pulse" aria-hidden />
            Abrindo a câmera… (o navegador pode pedir permissão)
          </div>
        ) : null}
        {message ? (
          <div className="absolute inset-0 flex items-center justify-center p-6">
            <div className="max-w-sm space-y-3 text-center" role="alert">
              <CameraOff className="mx-auto size-8 text-white/70" aria-hidden />
              <p className="text-base font-semibold">{message.title}</p>
              <p className="text-sm leading-relaxed text-white/75">{message.body}</p>
              <div className="flex flex-col gap-2 pt-2">
                {state === 'negada' || state === 'em_uso' || state === 'erro' ? (
                  <Button variant="primary" onClick={() => setAttempt((a) => a + 1)}>
                    <RefreshCw /> Tentar novamente
                  </Button>
                ) : null}
                <Button onClick={onUseSystemCamera} className="border-white/20 bg-white/10 text-white hover:bg-white/20">
                  <Camera /> Usar a câmera do sistema
                </Button>
                <Button onClick={onUseGallery} className="border-white/20 bg-white/10 text-white hover:bg-white/20">
                  <ImagePlus /> Escolher da galeria
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-3 items-center px-6 pt-4 pb-[max(env(safe-area-inset-bottom),1.25rem)]">
        <div>
          {lastThumbnail ? (
            <button type="button" onClick={onDone} className="relative block size-12 overflow-hidden rounded-lg border border-white/40" aria-label="Ver páginas capturadas">
              <img src={lastThumbnail} alt="" className="h-full w-full object-cover" />
              <span className="absolute -top-1 -right-1 flex size-5 items-center justify-center rounded-full bg-accent text-[10px] font-semibold">
                {pageCount}
              </span>
            </button>
          ) : null}
        </div>
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => void capture()}
            disabled={state !== 'ativa' || busy}
            className="flex size-[72px] items-center justify-center rounded-full border-4 border-white/80 transition-transform active:scale-95 disabled:opacity-40"
            aria-label="Fotografar página"
          >
            <span className="size-14 rounded-full bg-white" />
          </button>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onDone}
            className="flex items-center gap-1.5 rounded-full bg-white/15 px-4 py-2 text-sm font-medium hover:bg-white/25"
          >
            <Check className="size-4" /> Concluir
          </button>
        </div>
      </div>
    </div>
  );
}
