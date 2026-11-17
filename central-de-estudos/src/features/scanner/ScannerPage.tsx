import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Camera,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ImagePlus,
  Lightbulb,
  Loader2,
  Pencil,
  Trash2,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { LogoMark } from '@/components/layout/Logo';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Field } from '@/components/ui/Field';
import { Input, Textarea } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/misc';
import { ProgressBar } from '@/components/ui/Progress';
import { useBackend } from '@/data/DataContext';
import { scopeKey, useYearData } from '@/data/hooks';
import { defaultScanTitle, discardPartialScan, saveScan, type SaveScanInput, type ScanPageUpload } from '@/data/services/scans';
import type { Material } from '@/data/types';
import { errorMessage } from '@/lib/errors';
import { newId } from '@/lib/ids';
import { cn, pluralize } from '@/lib/utils';
import { SubjectExamFields, type Placement } from '../library/MaterialDialogs';
import { CameraCapture } from './CameraCapture';
import { saveDraftMeta } from './draftStore';
import { PageEditor } from './PageEditor';
import { useScannerPages, type IncomingImage, type ScannerPageState } from './useScannerPages';

type Step = 'capturar' | 'revisar' | 'salvando' | 'concluido';

function PageCard({
  page,
  index,
  total,
  onEdit,
  onMove,
  onRemove,
}: {
  page: ScannerPageState;
  index: number;
  total: number;
  onEdit: () => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-card" data-testid="scanner-page">
      <button
        type="button"
        onClick={onEdit}
        disabled={page.status === 'erro'}
        className="relative block aspect-[3/4] w-full bg-surface-2"
        aria-label={`Editar página ${index + 1}`}
      >
        {page.previewUrl ? <img src={page.previewUrl} alt={`Página ${index + 1}`} className="h-full w-full object-contain" /> : null}
        {page.status === 'processando' ? (
          <span className="absolute inset-0 flex items-center justify-center bg-bg/40" role="status">
            <Loader2 className="size-5 animate-spin text-accent-text" aria-label="Processando" />
          </span>
        ) : null}
        {page.status === 'erro' ? (
          <span className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-danger-soft p-3 text-center text-[11px] text-danger">
            <AlertTriangle className="size-5" aria-hidden />
            {page.error ?? 'Não foi possível abrir esta imagem.'}
          </span>
        ) : null}
        <span className="absolute top-2 left-2 flex size-6 items-center justify-center rounded-full bg-black/65 text-[11px] font-semibold text-white tabular">
          {index + 1}
        </span>
        {page.edits.quad ? (
          <span className="absolute top-2 right-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white">recortada</span>
        ) : null}
      </button>
      <div className="flex items-center justify-between gap-1 border-t border-border px-1.5 py-1">
        <Button size="icon-sm" variant="ghost" onClick={() => onMove(-1)} disabled={index === 0} aria-label={`Mover página ${index + 1} para antes`}>
          <ChevronLeft />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={() => onMove(1)} disabled={index === total - 1} aria-label={`Mover página ${index + 1} para depois`}>
          <ChevronRight />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={onEdit} disabled={page.status === 'erro'} aria-label={`Editar página ${index + 1}`}>
          <Pencil />
        </Button>
        <Button size="icon-sm" variant="danger-ghost" onClick={onRemove} aria-label={`Excluir página ${index + 1}`}>
          <Trash2 />
        </Button>
      </div>
    </li>
  );
}

export function ScannerPage() {
  const db = useBackend();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const { subjectById, exams, isLoading } = useYearData();
  const owner = `${db.mode}:${db.userId}`;
  const scanner = useScannerPages(owner);

  const [step, setStep] = useState<Step>('capturar');
  const [cameraOpen, setCameraOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [discarding, setDiscarding] = useState(false);
  const [placement, setPlacement] = useState<Placement>({ subject_id: '', exam_id: '' });
  const [topic, setTopic] = useState('');
  const [description, setDescription] = useState('');
  const [placementError, setPlacementError] = useState<string | undefined>();
  const [progress, setProgress] = useState<{ label: string; done: number; total: number } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [result, setResult] = useState<{ material: Material; pageCount: number } | null>(null);
  const ids = useRef({ scanId: newId(), materialId: newId() });
  const uploads = useRef<ScanPageUpload[] | null>(null);
  const lastInput = useRef<SaveScanInput | null>(null);
  const prefilled = useRef(false);
  const gallery = useRef<HTMLInputElement>(null);
  const systemCamera = useRef<HTMLInputElement>(null);

  // Disciplina/prova vindas do contexto (?disciplina=…&prova=…) ou do rascunho.
  useEffect(() => {
    if (prefilled.current || isLoading || !scanner.loaded) return;
    prefilled.current = true;
    const examId = params.get('prova') ?? '';
    const exam = exams.find((e) => e.id === examId);
    const subjectId = exam?.subject_id ?? params.get('disciplina') ?? '';
    if (subjectById.has(subjectId)) {
      setPlacement({ subject_id: subjectId, exam_id: exam ? exam.id : '' });
    } else if (scanner.draftMeta && subjectById.has(scanner.draftMeta.subjectId)) {
      setPlacement({ subject_id: scanner.draftMeta.subjectId, exam_id: scanner.draftMeta.examId });
    }
    if (scanner.draftMeta) {
      setTopic(scanner.draftMeta.topic);
      setDescription(scanner.draftMeta.description);
    }
  }, [isLoading, scanner.loaded, scanner.draftMeta, params, exams, subjectById]);

  // Guarda a organização junto com o rascunho.
  useEffect(() => {
    if (!prefilled.current) return;
    const timer = window.setTimeout(() => {
      void saveDraftMeta({
        owner,
        subjectId: placement.subject_id,
        examId: placement.exam_id,
        topic,
        description,
        updatedAt: new Date().toISOString(),
      }).catch(() => undefined);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [owner, placement, topic, description]);

  // Qualquer mudança nas páginas invalida as versões finais já geradas.
  useEffect(() => {
    uploads.current = null;
  }, [scanner.pages]);

  const origin = useMemo(() => {
    const examId = params.get('prova');
    const subjectId = params.get('disciplina');
    if (examId) return `/provas/${examId}/materiais`;
    if (subjectId) return `/disciplinas/${subjectId}`;
    return '/';
  }, [params]);

  const pages = scanner.pages;
  const processing = pages.some((p) => p.status === 'processando');
  const failed = pages.filter((p) => p.status === 'erro').length;
  const editingPage = pages.find((p) => p.id === editingId);
  const subjectName = subjectById.get(placement.subject_id)?.name;

  const addFromInput = (files: FileList | null, source: IncomingImage['source']) => {
    if (!files?.length) return;
    void scanner.addImages(Array.from(files).map((file) => ({ blob: file, name: file.name, source })));
  };

  const onCapture = (blob: Blob) => {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    void scanner.addImages([{ blob, name: `camera-${stamp}.jpg`, source: 'camera' }]);
  };

  const goReview = () => {
    if (!pages.length) return;
    setStep('revisar');
    window.scrollTo({ top: 0 });
  };

  const save = async () => {
    if (!placement.subject_id) {
      setPlacementError('Selecione a disciplina.');
      return;
    }
    setPlacementError(undefined);
    setSaveError(null);
    setStep('salvando');
    try {
      if (!uploads.current) {
        uploads.current = await scanner.buildUploads((done, total) =>
          setProgress({ label: `Preparando as páginas (${Math.min(done + 1, total)} de ${total})`, done, total }),
        );
      }
      const input: SaveScanInput = {
        ...ids.current,
        subject_id: placement.subject_id,
        exam_id: placement.exam_id || null,
        topic: topic.trim() || null,
        description: description.trim() || null,
        pages: uploads.current,
      };
      lastInput.current = input;
      const { material } = await saveScan(db, input, { title: defaultScanTitle(topic, subjectName) }, (p) =>
        setProgress({
          label: p.step === 'arquivos' ? `Enviando as fotos (${p.done} de ${p.total})` : 'Organizando na biblioteca…',
          done: p.done,
          total: p.total,
        }),
      );
      const pageCount = input.pages.length;
      await scanner.reset();
      uploads.current = null;
      lastInput.current = null;
      ids.current = { scanId: newId(), materialId: newId() };
      setResult({ material, pageCount });
      setStep('concluido');
      void queryClient.invalidateQueries({ queryKey: scopeKey(db) });
    } catch (error) {
      setSaveError(errorMessage(error));
    }
  };

  /** Volta para a revisão desfazendo o que foi enviado parcialmente. */
  const abandonSave = async () => {
    const input = lastInput.current;
    if (input) await discardPartialScan(db, input).catch(() => undefined);
    lastInput.current = null;
    ids.current = { scanId: newId(), materialId: newId() };
    setStep('revisar');
    setSaveError(null);
  };

  const restart = () => {
    setResult(null);
    setTopic('');
    setDescription('');
    setStep('capturar');
  };

  const stepIndex = step === 'capturar' ? 0 : 1;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-3 px-4">
          <button
            type="button"
            onClick={() => navigate(origin)}
            className="-ml-1.5 flex items-center gap-1.5 rounded-lg p-1.5 text-sm text-fg-muted hover:bg-surface-2 hover:text-fg"
            aria-label="Sair do scanner"
          >
            <X className="size-5" />
            <span className="hidden sm:inline">Sair</span>
          </button>
          <div className="flex items-center gap-2">
            <LogoMark size={22} />
            <h1 className="text-sm font-semibold">Fotografar meu caderno</h1>
          </div>
          <ol className="hidden items-center gap-2 text-xs sm:flex" aria-label="Etapas">
            {['Capturar', 'Revisar e salvar'].map((label, i) => (
              <li key={label} className={cn('flex items-center gap-1.5', i === stepIndex ? 'text-fg' : 'text-fg-subtle')} aria-current={i === stepIndex ? 'step' : undefined}>
                <span className={cn('flex size-5 items-center justify-center rounded-full text-[10px] font-semibold', i === stepIndex ? 'bg-accent text-accent-fg' : 'bg-surface-3')}>
                  {i + 1}
                </span>
                {label}
              </li>
            ))}
          </ol>
          <span className="w-9 sm:hidden" aria-hidden />
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-5 pb-32">
        {!scanner.loaded || isLoading ? (
          <div className="flex justify-center py-20">
            <Spinner label="Preparando o scanner…" />
          </div>
        ) : step === 'capturar' ? (
          <>
            {scanner.restoredCount > 0 && pages.length > 0 ? (
              <div className="mb-4 flex animate-rise flex-wrap items-center justify-between gap-2 rounded-xl border border-info/25 bg-info-soft px-4 py-3 text-xs">
                <span className="text-fg-muted">
                  <strong className="font-medium text-fg">Rascunho recuperado:</strong> {pluralize(scanner.restoredCount, 'página fotografada antes', 'páginas fotografadas antes')}.
                </span>
                <Button size="sm" variant="ghost" onClick={() => setDiscarding(true)}>
                  Descartar rascunho
                </Button>
              </div>
            ) : null}

            {!pages.length ? (
              <Card className="mx-auto max-w-xl animate-rise p-6 text-center sm:p-8">
                <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-fg">
                  <Camera className="size-7" aria-hidden />
                </span>
                <h2 className="mt-4 text-lg font-semibold tracking-tight">Fotografe as páginas do caderno</h2>
                <p className="mt-1.5 text-sm text-fg-muted">
                  Tire várias fotos em sequência. Depois você ajusta recorte e iluminação, confere tudo e salva na disciplina.
                </p>
                <div className="mt-6 grid gap-2.5">
                  <Button variant="primary" size="lg" onClick={() => setCameraOpen(true)}>
                    <Camera /> Abrir câmera
                  </Button>
                  <Button size="lg" onClick={() => gallery.current?.click()}>
                    <ImagePlus /> Escolher da galeria
                  </Button>
                  <button type="button" onClick={() => systemCamera.current?.click()} className="mt-1 text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline">
                    Usar o aplicativo de câmera do aparelho
                  </button>
                </div>
                <ul className="mt-6 space-y-2 border-t border-border pt-5 text-left text-xs text-fg-muted">
                  {[
                    'Use boa iluminação e evite sombras sobre a folha.',
                    'Enquadre a página inteira, com a mesa ao redor (ajuda o recorte automático).',
                    'Fotografe na ordem das páginas — dá para reordenar depois.',
                  ].map((tip) => (
                    <li key={tip} className="flex gap-2">
                      <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
                      {tip}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : (
              <>
                <div className="mb-3 flex items-baseline justify-between gap-3">
                  <h2 className="text-base font-semibold">{pluralize(pages.length, 'página', 'páginas')}</h2>
                  <p className="text-xs text-fg-subtle">Toque em uma página para recortar, girar ou ajustar a iluminação.</p>
                </div>
                <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-label="Páginas capturadas">
                  {pages.map((page, index) => (
                    <PageCard
                      key={page.id}
                      page={page}
                      index={index}
                      total={pages.length}
                      onEdit={() => setEditingId(page.id)}
                      onMove={(d) => scanner.move(page.id, d)}
                      onRemove={() => setRemoving(page.id)}
                    />
                  ))}
                  <li className="flex aspect-[3/4] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong p-3 text-center">
                    <span className="text-xs font-medium text-fg-muted">Adicionar páginas</span>
                    <Button size="sm" onClick={() => setCameraOpen(true)}>
                      <Camera /> Câmera
                    </Button>
                    <Button size="sm" onClick={() => gallery.current?.click()}>
                      <ImagePlus /> Galeria
                    </Button>
                  </li>
                </ol>
              </>
            )}
          </>
        ) : step === 'revisar' ? (
          <div className="grid animate-rise gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
            <div className="order-2 space-y-4 lg:order-1">
              <h2 className="text-base font-semibold">Confira todas as páginas</h2>
              <ol className="space-y-4" aria-label="Revisão das páginas">
                {pages.map((page, index) => (
                  <li key={page.id} className="overflow-hidden rounded-xl border border-border bg-surface" data-testid="review-page">
                    {page.previewUrl ? <img src={page.previewUrl} alt={`Página ${index + 1}`} className="mx-auto max-h-[80vh] w-full bg-surface-2 object-contain" /> : null}
                    <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs">
                      <span className="font-medium text-fg-muted">
                        Página {index + 1} de {pages.length}
                      </span>
                      <Button size="sm" variant="ghost" onClick={() => setEditingId(page.id)}>
                        <Pencil /> Editar
                      </Button>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <Card className="order-1 p-4 sm:p-5 lg:sticky lg:top-20 lg:order-2">
              <h2 className="text-base font-semibold">Onde guardar</h2>
              <p className="mt-1 text-xs text-fg-muted">O caderno será salvo na biblioteca, ligado à disciplina e, se quiser, a uma prova.</p>
              <div className="mt-4 grid gap-4 [&_.grid]:grid-cols-1">
                <SubjectExamFields
                  value={placement}
                  onChange={(v) => {
                    setPlacement(v);
                    setPlacementError(undefined);
                  }}
                  errors={{ subject_id: placementError }}
                />
                <Field label="Nome ou assunto do conteúdo" optional hint="Ex.: Cinemática e velocidade média">
                  <Input value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200} />
                </Field>
                <Field label="Observações" optional>
                  <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
                </Field>
              </div>
              <p className="mt-4 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-fg-muted">
                Serão guardadas as <strong className="font-medium text-fg">fotos originais</strong> e as versões tratadas, na ordem
                acima — prontas para a leitura automática por IA (Fase 7).
              </p>
            </Card>
          </div>
        ) : step === 'salvando' ? (
          <Card className="mx-auto max-w-md animate-rise p-6 text-center" role="status" aria-live="polite">
            {saveError ? (
              <>
                <AlertTriangle className="mx-auto size-8 text-danger" aria-hidden />
                <p className="mt-3 text-base font-semibold">Não foi possível salvar</p>
                <p className="mt-1 text-sm text-fg-muted">{saveError}</p>
                <p className="mt-2 text-xs text-fg-subtle">Suas páginas continuam guardadas neste aparelho.</p>
                <div className="mt-5 grid gap-2">
                  <Button variant="primary" onClick={() => void save()}>
                    Tentar novamente
                  </Button>
                  <Button onClick={() => void abandonSave()}>Voltar e revisar</Button>
                </div>
              </>
            ) : (
              <>
                <Loader2 className="mx-auto size-8 animate-spin text-accent-text" aria-hidden />
                <p className="mt-3 text-base font-semibold">Salvando o caderno…</p>
                <p className="mt-1 text-sm text-fg-muted">{progress?.label ?? 'Preparando…'}</p>
                <ProgressBar value={progress && progress.total ? progress.done / progress.total : 0} className="mt-4" label="Progresso do salvamento" />
                <p className="mt-3 text-xs text-fg-subtle">Mantenha esta tela aberta até terminar.</p>
              </>
            )}
          </Card>
        ) : result ? (
          <Card className="mx-auto max-w-md animate-rise p-6 text-center">
            <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
            <h2 className="mt-3 text-lg font-semibold">Caderno salvo!</h2>
            <p className="mt-1 text-sm text-fg-muted">
              {pluralize(result.pageCount, 'página guardada', 'páginas guardadas')} em <strong className="text-fg">{subjectById.get(result.material.subject_id)?.name}</strong>
              {result.material.exam_id ? <> · {exams.find((e) => e.id === result.material.exam_id)?.title}</> : null}.
            </p>
            <p className="mt-3 rounded-lg bg-surface-2 p-3 text-xs text-fg-muted">
              As fotos originais e tratadas estão prontas para a leitura automática por IA, que chega na Fase 7.
            </p>
            <div className="mt-5 grid gap-2">
              <ButtonLink to={`/biblioteca/${result.material.id}`} variant="primary">
                Ver o caderno salvo
              </ButtonLink>
              <Button onClick={restart}>
                <Camera /> Fotografar outro caderno
              </Button>
              <Link to={`/disciplinas/${result.material.subject_id}`} className="pt-1 text-xs text-fg-muted hover:text-fg">
                Ir para a disciplina
              </Link>
            </div>
          </Card>
        ) : null}
      </main>

      {(step === 'capturar' && pages.length > 0) || step === 'revisar' ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-bg/95 backdrop-blur-md">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 pt-3 pb-[max(env(safe-area-inset-bottom),0.75rem)]">
            {step === 'capturar' ? (
              <>
                <span className="text-xs text-fg-muted">
                  {failed ? <span className="text-danger">{pluralize(failed, 'página com erro', 'páginas com erro')} — remova para continuar</span> : processing ? 'Processando páginas…' : pluralize(pages.length, 'página pronta', 'páginas prontas')}
                </span>
                <Button variant="primary" onClick={goReview} disabled={processing || failed > 0}>
                  Revisar e salvar <ArrowRight />
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" onClick={() => setStep('capturar')}>
                  <ArrowLeft /> Páginas
                </Button>
                <Button variant="primary" onClick={() => void save()} disabled={processing}>
                  Salvar caderno
                </Button>
              </>
            )}
          </div>
        </div>
      ) : null}

      <input
        ref={gallery}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        aria-label="Escolher fotos da galeria"
        onChange={(e) => {
          addFromInput(e.target.files, 'galeria');
          e.target.value = '';
        }}
      />
      <input
        ref={systemCamera}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        aria-label="Fotografar com a câmera do aparelho"
        onChange={(e) => {
          addFromInput(e.target.files, 'camera');
          e.target.value = '';
        }}
      />

      {cameraOpen ? (
        <CameraCapture
          pageCount={pages.length}
          lastThumbnail={pages.at(-1)?.previewUrl}
          onCapture={onCapture}
          onDone={() => setCameraOpen(false)}
          onUseSystemCamera={() => {
            setCameraOpen(false);
            systemCamera.current?.click();
          }}
          onUseGallery={() => {
            setCameraOpen(false);
            gallery.current?.click();
          }}
        />
      ) : null}

      {editingPage ? (
        <PageEditor
          key={editingPage.id}
          open
          pageNumber={pages.indexOf(editingPage) + 1}
          total={pages.length}
          initialEdits={editingPage.edits}
          loadSource={() => scanner.sourceRaster(editingPage)}
          onCancel={() => setEditingId(null)}
          onSave={(edits) => {
            scanner.updateEdits(editingPage.id, edits);
            setEditingId(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Excluir esta página?"
        description="A foto será removida desta digitalização."
        confirmLabel="Excluir página"
        onConfirm={() => {
          if (removing) scanner.remove(removing);
          setRemoving(null);
        }}
      />
      <ConfirmDialog
        open={discarding}
        onOpenChange={setDiscarding}
        title="Descartar o rascunho?"
        description="Todas as páginas ainda não salvas serão apagadas deste aparelho."
        confirmLabel="Descartar"
        onConfirm={async () => {
          await scanner.reset();
          setDiscarding(false);
          toast.success('Rascunho descartado.');
        }}
      />
    </div>
  );
}
