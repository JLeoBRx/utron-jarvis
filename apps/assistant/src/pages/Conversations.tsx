import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button, EmptyState, ErrorState, Icon, Menu, Modal, SearchField, Select, Skeleton, Spinner, TextField, useToast } from "@safra/ui";

import { useBusy } from "../activity";
import { ApiError, api, messageOf } from "../api";
import { NotImplemented, PageHeader, useCanAct } from "../components";
import { formatRelative, formatTime } from "../format";
import { useResource, useTitle } from "../hooks";
import { href, navigate } from "../router";
import type { AiStatus, Conversation, ConversationSummary, Message, Project, SendResult } from "../types";

function ConversationList({ current, conversations, onSearch, query }: { current?: number; conversations: ReturnType<typeof useResource<ConversationSummary[]>>; onSearch: (q: string) => void; query: string }) {
  const canAct = useCanAct();
  return (
    <section className="conversas__lista" aria-label="Lista de conversas">
      <div className="conversas__lista-topo">
        <SearchField label="Buscar nas conversas" hideLabel placeholder="Buscar nas conversas" value={query} onChange={(e) => onSearch(e.target.value)} />
        <Button variant="principal" icon="mais" disabled={!canAct} onClick={() => navigate("/conversas")}>Nova</Button>
      </div>
      {conversations.error ? <ErrorState message={conversations.error} onRetry={conversations.reload} /> : !conversations.data ? <Skeleton lines={5} /> : conversations.data.length === 0 ? (
        <EmptyState title={query ? "Nada encontrado" : "Nenhuma conversa"} description={query ? "Tente outras palavras." : "Escreva ao lado para começar."} icon="conversa" />
      ) : (
        <ul className="conversas__itens">
          {conversations.data.map((c) => (
            <li key={c.id}>
              <a className="conversas__item" href={href(`/conversas/${c.id}`)} aria-current={c.id === current ? "page" : undefined}>
                <span className="conversas__item-titulo">{c.title}</span>
                <span className="conversas__item-previa">{c.preview || "Sem mensagens"}</span>
                <span className="apoio">{formatRelative(c.updated_at)} · {c.message_count} {c.message_count === 1 ? "mensagem" : "mensagens"}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Lista as mensagens. Depois de cada pedido sem resposta, diz por que não há resposta (o fato registrado). */
function Thread({ messages }: { messages: Message[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // corpo em bloco: no Chromium recente scrollIntoView devolve uma Promise, e um efeito só pode devolver a limpeza
    const node = end.current;
    if (node && typeof node.scrollIntoView === "function") void node.scrollIntoView({ block: "end" });
  }, [messages.length]);
  if (messages.length === 0)
    return <EmptyState title="Conversa vazia" description="Escreva a primeira mensagem abaixo." icon="conversa" />;
  return (
    <ol className="mensagens" aria-label="Mensagens">
      {messages.map((m, index) => {
        const next = messages[index + 1];
        const unanswered = m.role === "user" && (!next || next.role === "user");
        return (
          <li key={m.id} className={`mensagem mensagem--${m.role}`}>
            <p className="mensagem__autor">{m.role === "user" ? "Você" : m.role === "assistant" ? "SAFRA" : "Sistema"} <span className="apoio">{formatTime(m.created_at)}</span></p>
            <div className="mensagem__texto">{m.content}</div>
            {unanswered && (
              <p className="mensagem__sem-resposta">
                <Icon name="informacao" size={16} /> Sem resposta: o gateway de IA ainda não foi implementado.
              </p>
            )}
          </li>
        );
      })}
      <div ref={end} />
    </ol>
  );
}

export function Composer({ disabled, archived, onSend, ai }: { disabled: boolean; archived: boolean; onSend: (text: string, signal: AbortSignal) => Promise<void>; ai: AiStatus | null }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const providers = ai?.providers.filter((p) => p.enabled) ?? [];

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const value = text.trim();
    if (!value || sending) return;
    controller.current = new AbortController();
    setSending(true);
    setError(null);
    try {
      await onSend(value, controller.current.signal);
      setText("");
    } catch (err) {
      setError(err instanceof ApiError && err.code === "cancelado" ? "Envio cancelado. A mensagem continua no campo." : messageOf(err));
    } finally {
      setSending(false);
      controller.current = null;
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };
  return (
    <form className="compositor" onSubmit={submit} aria-label="Escrever mensagem">
      <div className="compositor__linha">
        <label htmlFor="compositor-texto" className="ui-oculto">Mensagem</label>
        <textarea
          id="compositor-texto"
          className="ui-entrada compositor__texto"
          rows={2}
          maxLength={20000}
          placeholder={archived ? "Conversa arquivada" : "Escreva uma mensagem (Enter envia, Shift+Enter quebra a linha)"}
          value={text}
          disabled={disabled || archived}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby="compositor-estado"
        />
        {sending ? (
          <Button variant="secundario" icon="parar" onClick={() => controller.current?.abort()}>Cancelar</Button>
        ) : (
          <Button type="submit" variant="principal" icon="enviar" disabled={disabled || archived || !text.trim()}>Enviar</Button>
        )}
      </div>
      <div className="compositor__rodape">
        <Select
          label="Provedor de IA"
          className="compositor__provedor"
          disabled={!ai?.selection_allowed || providers.length === 0}
          options={providers.length ? providers.map((p) => ({ value: String(p.id), label: p.name })) : [{ value: "", label: "Nenhum disponível" }]}
          help={ai && !ai.selection_allowed ? "A escolha de provedor chega com o gateway de IA (Fase 5)." : undefined}
        />
        <p id="compositor-estado" className="compositor__estado" role="status">
          {sending ? <Spinner label="Enviando…" size="normal" /> : error ? <span className="texto-erro"><Icon name="erro" size={16} /> {error}</span> : null}
        </p>
      </div>
    </form>
  );
}

export function ConversationsPage({ id }: { id?: number }) {
  useTitle("Conversas");
  const toast = useToast();
  const { setBusy } = useBusy();
  const canAct = useCanAct();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const list = useResource<ConversationSummary[]>(`/conversations${debounced ? `?q=${encodeURIComponent(debounced)}` : ""}`);
  const conversation = useResource<Conversation>(id !== undefined ? `/conversations/${id}` : null);
  const ai = useResource<AiStatus>("/ai/status");

  const send = async (text: string, signal: AbortSignal) => {
    setBusy(true);
    try {
      let targetId = id;
      if (targetId === undefined) {
        const created = await api.post<ConversationSummary>("/conversations", {}, signal);
        targetId = created.id;
      }
      const result = await api.post<SendResult>(`/conversations/${targetId}/messages`, { content: text }, signal);
      if (id === undefined) navigate(`/conversas/${targetId}`);
      else if (conversation.data) conversation.setData({ ...conversation.data, messages: [...conversation.data.messages, result.message], message_count: conversation.data.message_count + 1 });
      void list.reload();
    } finally {
      setBusy(false);
    }
  };

  const archive = async (archived: boolean) => {
    if (id === undefined) return;
    try {
      await api.patch(`/conversations/${id}`, { archived });
      toast.notify(archived ? "Conversa arquivada." : "Conversa desarquivada.");
      await Promise.all([conversation.reload(), list.reload()]);
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };

  const projects = useResource<Project[]>("/projects?status=active");
  const [linking, setLinking] = useState<string | null>(null);
  const link = async (event: FormEvent) => {
    event.preventDefault();
    if (!conversation.data || linking === null) return;
    try {
      await api.patch(`/conversations/${conversation.data.id}`, { project_id: linking ? Number(linking) : null });
      await conversation.reload();
      setLinking(null);
      toast.notify(linking ? "Conversa ligada ao projeto." : "Conversa desligada do projeto.");
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  const [renaming, setRenaming] = useState<string | null>(null);
  const [savingTitle, setSavingTitle] = useState(false);
  const rename = async (event: FormEvent) => {
    event.preventDefault();
    if (!conversation.data || !renaming?.trim()) return;
    setSavingTitle(true);
    try {
      await api.patch(`/conversations/${conversation.data.id}`, { title: renaming });
      await Promise.all([conversation.reload(), list.reload()]);
      setRenaming(null);
      toast.notify("Título atualizado.");
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    } finally {
      setSavingTitle(false);
    }
  };

  const data = conversation.data;
  return (
    <div className={`pagina pagina--conversas ${id !== undefined ? "pagina--com-conversa" : ""}`}>
      <PageHeader title={data ? data.title : "Conversas"} description={data ? `${data.message_count} ${data.message_count === 1 ? "mensagem" : "mensagens"} · ${data.archived ? "arquivada" : "ativa"}` : "Converse com o SAFRA. As mensagens ficam neste computador."}
        actions={data && (
          <>
            <a className="ui-botao ui-botao--discreto voltar-lista" href={href("/conversas")}><Icon name="chevron-esquerda" size={18} /> Conversas</a>
            <Menu label="Ações da conversa" items={[
              { id: "renomear", label: "Renomear", icon: "editar", disabled: !canAct, onSelect: () => setRenaming(data.title) },
              { id: "projeto", label: "Ligar a um projeto", icon: "projetos", disabled: !canAct, onSelect: () => setLinking(data.project_id ? String(data.project_id) : "") },
              data.archived
                ? { id: "desarquivar", label: "Desarquivar", icon: "restaurar", disabled: !canAct, onSelect: () => void archive(false) }
                : { id: "arquivar", label: "Arquivar", icon: "arquivar", disabled: !canAct, onSelect: () => void archive(true) },
            ]} />
          </>
        )} />
      {ai.data && ai.data.gateway.situacao === "nao_implementado" && (
        <NotImplemented title="Sem respostas de IA nesta versão" phase={ai.data.gateway.fase}>
          <p>{ai.data.gateway.mensagem}</p>
        </NotImplemented>
      )}
      <div className="conversas">
        <ConversationList current={id} conversations={list} query={query} onSearch={setQuery} />
        <section className="conversas__fio" aria-label={data ? `Conversa: ${data.title}` : "Nova conversa"}>
          {id !== undefined && conversation.error ? (
            <ErrorState message={conversation.error} onRetry={conversation.reload} />
          ) : id !== undefined && !data ? (
            <Skeleton lines={6} />
          ) : (
            <Thread messages={data?.messages ?? []} />
          )}
          <Composer disabled={!canAct} archived={data?.archived ?? false} onSend={send} ai={ai.data} />
        </section>
      </div>
      {id === undefined && <p className="apoio dica-nova">Ao enviar a primeira mensagem, uma conversa nova é criada.</p>}
      <Modal open={linking !== null} title="Ligar a um projeto" onClose={() => setLinking(null)}>
        <form className="formulario" onSubmit={link}>
          <Select label="Projeto" value={linking ?? ""} onChange={(e) => setLinking(e.target.value)}
            options={[{ value: "", label: "Nenhum" }, ...(projects.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))]} />
          <div className="formulario__acoes">
            <Button onClick={() => setLinking(null)}>Cancelar</Button>
            <Button type="submit" variant="principal">Salvar</Button>
          </div>
        </form>
      </Modal>
      <Modal open={renaming !== null} title="Renomear conversa" onClose={() => setRenaming(null)}>
        <form className="formulario" onSubmit={rename}>
          <TextField label="Título" value={renaming ?? ""} maxLength={200} required onChange={(e) => setRenaming(e.target.value)} />
          <div className="formulario__acoes">
            <Button onClick={() => setRenaming(null)}>Cancelar</Button>
            <Button type="submit" variant="principal" loading={savingTitle}>Salvar</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
