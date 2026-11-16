import { ArrowDown, ArrowUp, ChevronDown, ListChecks, MoreHorizontal, NotebookText, Pencil, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent } from 'react';
import { TOPIC_STATUS_STYLES } from '@/components/domain/badges';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Dialog } from '@/components/ui/Dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { Field } from '@/components/ui/Field';
import { Input, Textarea } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/misc';
import { ProgressBar } from '@/components/ui/Progress';
import { useAction } from '@/data/hooks';
import { createTopics, deleteTopic, moveTopic, parseTopicLines, setTopicStatus, updateTopic } from '@/data/services/topics';
import type { Exam, ExamTopic, TopicStatus } from '@/data/types';
import { TOPIC_STATUS_LABELS, TOPIC_STATUS_ORDER } from '@/lib/labels';
import { formatPercent, topicsProgress } from '@/lib/progress';
import { cn, pluralize } from '@/lib/utils';

function StatusPicker({ topic }: { topic: ExamTopic }) {
  const change = useAction((db, status: TopicStatus) => setTopicStatus(db, topic.id, status));
  const style = TOPIC_STATUS_STYLES[topic.status];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border px-2 text-xs font-medium transition-colors hover:border-border-strong',
          style.text,
        )}
        aria-label={`Status de "${topic.title}": ${TOPIC_STATUS_LABELS[topic.status]}. Alterar`}
      >
        <span className={cn('size-1.5 rounded-full', style.dot)} aria-hidden />
        {TOPIC_STATUS_LABELS[topic.status]}
        <ChevronDown className="size-3 text-fg-subtle" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-44">
        <DropdownMenuLabel>Como está este conteúdo?</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={topic.status} onValueChange={(value) => change.mutate(value as TopicStatus)}>
          {TOPIC_STATUS_ORDER.map((status) => (
            <DropdownMenuRadioItem key={status} value={status}>
              {TOPIC_STATUS_LABELS[status]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function TopicEditDialog({ topic, open, onOpenChange }: { topic: ExamTopic; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [title, setTitle] = useState(topic.title);
  const [notes, setNotes] = useState(topic.notes ?? '');
  useEffect(() => {
    if (open) {
      setTitle(topic.title);
      setNotes(topic.notes ?? '');
    }
  }, [open, topic]);
  const save = useAction((db) => updateTopic(db, topic.id, { title, notes, status: topic.status }), {
    success: 'Conteúdo atualizado.',
    onSuccess: () => onOpenChange(false),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Editar conteúdo"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)} disabled={!title.trim()}>
            Salvar
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Conteúdo">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus />
        </Field>
        <Field label="Anotações" optional hint="Ex.: páginas do livro, observações do professor, dúvidas.">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} maxLength={4000} />
        </Field>
      </div>
    </Dialog>
  );
}

function TopicRow({ topic, index, total, examId }: { topic: ExamTopic; index: number; total: number; examId: string }) {
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const move = useAction((db, direction: -1 | 1) => moveTopic(db, examId, topic.id, direction));
  const remove = useAction((db) => deleteTopic(db, topic.id), {
    success: 'Conteúdo removido.',
    onSuccess: () => setDeleting(false),
  });

  return (
    <li className="group flex items-start gap-3 px-4 py-3 sm:px-5">
      <span className="mt-1 w-5 shrink-0 text-right text-xs text-fg-subtle tabular">{index + 1}</span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className={cn(
            'block w-full text-left text-sm leading-snug break-words hover:text-accent-text',
            topic.status === 'dominado' ? 'text-fg-muted' : 'text-fg',
          )}
        >
          {topic.title}
        </button>
        {topic.notes ? (
          <p className="mt-1 flex gap-1.5 text-xs leading-relaxed text-fg-subtle">
            <NotebookText className="mt-0.5 size-3 shrink-0" aria-hidden />
            <span className="line-clamp-2 whitespace-pre-line">{topic.notes}</span>
          </p>
        ) : null}
      </div>
      <StatusPicker topic={topic} />
      <DropdownMenu>
        <DropdownMenuTrigger
          className="mt-0.5 rounded-md p-1 text-fg-subtle transition hover:bg-surface-2 hover:text-fg"
          aria-label={`Ações de "${topic.title}"`}
        >
          <MoreHorizontal className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem icon={<Pencil />} onSelect={() => setEditing(true)}>
            Editar e anotar
          </DropdownMenuItem>
          <DropdownMenuItem icon={<ArrowUp />} disabled={index === 0} onSelect={() => move.mutate(-1)}>
            Mover para cima
          </DropdownMenuItem>
          <DropdownMenuItem icon={<ArrowDown />} disabled={index === total - 1} onSelect={() => move.mutate(1)}>
            Mover para baixo
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem icon={<Trash2 />} danger onSelect={() => setDeleting(true)}>
            Remover
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <TopicEditDialog topic={topic} open={editing} onOpenChange={setEditing} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Remover conteúdo?"
        description={`"${topic.title}" será removido desta prova.`}
        confirmLabel="Remover"
        loading={remove.isPending}
        onConfirm={() => remove.mutate(undefined)}
      />
    </li>
  );
}

export function TopicsTab({ exam, topics }: { exam: Exam; topics: ExamTopic[] }) {
  const [text, setText] = useState('');
  const [multiline, setMultiline] = useState(false);
  const progress = topicsProgress(topics);
  const lines = parseTopicLines(text);

  const add = useAction((db, titles: string[]) => createTopics(db, exam.id, titles), {
    success: (rows) => (rows.length > 1 ? `${rows.length} conteúdos adicionados.` : 'Conteúdo adicionado.'),
    onSuccess: () => {
      setText('');
      setMultiline(false);
    },
  });

  const submit = () => {
    if (lines.length && !add.isPending) add.mutate(lines);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (!multiline || event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <Card className="animate-rise">
        <div className="border-b border-border p-4 sm:p-5">
          <label htmlFor="novo-conteudo" className="text-xs font-medium text-fg-muted">
            Adicionar conteúdos cobrados
          </label>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-start">
            {multiline ? (
              <Textarea
                id="novo-conteudo"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKeyDown}
                rows={5}
                autoFocus
                placeholder={'Um conteúdo por linha, por exemplo:\nCinemática\nVelocidade média\nMovimento uniforme'}
              />
            ) : (
              <Input
                id="novo-conteudo"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKeyDown}
                onPaste={(e) => {
                  if (e.clipboardData.getData('text').includes('\n')) setMultiline(true);
                }}
                placeholder="Ex.: Cinemática e velocidade média"
                maxLength={4000}
              />
            )}
            <Button variant="primary" onClick={submit} disabled={!lines.length} loading={add.isPending} className="sm:w-auto">
              <Plus /> {lines.length > 1 ? `Adicionar ${lines.length}` : 'Adicionar'}
            </Button>
          </div>
          <p className="mt-2 text-[11px] text-fg-subtle">
            {multiline ? (
              <>
                Um conteúdo por linha · <kbd className="font-mono">Ctrl</kbd>+<kbd className="font-mono">Enter</kbd> para adicionar ·{' '}
                <button type="button" className="underline-offset-2 hover:underline" onClick={() => setMultiline(false)}>
                  voltar para um por vez
                </button>
              </>
            ) : (
              <>
                Enter para adicionar ·{' '}
                <button type="button" className="underline-offset-2 hover:underline" onClick={() => setMultiline(true)}>
                  adicionar vários de uma vez
                </button>
              </>
            )}
          </p>
        </div>
        {topics.length ? (
          <ul className="divide-y divide-border" aria-label="Conteúdos da prova">
            {topics.map((topic, index) => (
              <TopicRow key={topic.id} topic={topic} index={index} total={topics.length} examId={exam.id} />
            ))}
          </ul>
        ) : (
          <EmptyState
            compact
            icon={<ListChecks />}
            title="Nenhum conteúdo cadastrado"
            description="Informe os assuntos que serão cobrados nesta prova. Eles organizam o resumo, os flashcards e os simulados."
          />
        )}
      </Card>

      <Card className="h-fit animate-rise p-4 sm:p-5">
        <p className="text-xs font-medium text-fg-muted">Preparação</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight text-fg tabular">{formatPercent(progress.value)}</p>
        <ProgressBar value={progress.value} className="mt-3" label="Preparação da prova" />
        <ul className="mt-4 space-y-2">
          {TOPIC_STATUS_ORDER.map((status) => (
            <li key={status} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-fg-muted">
                <span className={cn('size-2 rounded-full', TOPIC_STATUS_STYLES[status].dot)} aria-hidden />
                {TOPIC_STATUS_LABELS[status]}
              </span>
              <span className="font-medium text-fg tabular">{progress.byStatus[status]}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t border-border pt-3 text-[11px] leading-relaxed text-fg-subtle">
          {progress.total
            ? `${pluralize(progress.total, 'conteúdo', 'conteúdos')}. Atualize o status conforme estudar: cada nível conta 1/3 do conteúdo.`
            : 'O progresso é calculado a partir do status de estudo de cada conteúdo.'}
        </p>
      </Card>
    </div>
  );
}
