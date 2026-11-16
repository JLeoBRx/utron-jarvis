import { useState, type FormEvent } from "react";

import { Button, Card, EmptyState, ErrorState, Menu, Modal, Skeleton, StatusBadge, Switch, TextArea, TextField, useToast } from "@safra/ui";

import { api, messageOf } from "../api";
import { PageHeader, useCanAct } from "../components";
import { formatDateTime, formatRelative } from "../format";
import { useResource, useTitle } from "../hooks";
import { href } from "../router";
import type { ConversationSummary, Memory, Project } from "../types";

type Draft = { id?: number; name: string; description: string };

function ProjectForm({ draft, onClose, onSaved }: { draft: Draft; onClose: () => void; onSaved: (p: Project) => void }) {
  const [value, setValue] = useState(draft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = { name: value.name, description: value.description };
      const saved = draft.id ? await api.patch<Project>(`/projects/${draft.id}`, body) : await api.post<Project>("/projects", body);
      onSaved(saved);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal open title={draft.id ? "Editar projeto" : "Novo projeto"} onClose={onClose}>
      <form className="formulario" onSubmit={submit}>
        <TextField label="Nome" required maxLength={120} value={value.name} error={error} onChange={(e) => setValue({ ...value, name: e.target.value })} />
        <TextArea label="Descrição" maxLength={2000} value={value.description} help="Opcional. Para que serve o projeto." onChange={(e) => setValue({ ...value, description: e.target.value })} />
        <div className="formulario__acoes">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="principal" loading={saving}>{draft.id ? "Salvar" : "Criar projeto"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ProjectDetail({ id }: { id: number }) {
  const toast = useToast();
  const canAct = useCanAct();
  const project = useResource<Project>(`/projects/${id}`);
  const conversations = useResource<ConversationSummary[]>(`/conversations?project_id=${id}`);
  const memories = useResource<Memory[]>(`/memories?project_id=${id}`);
  const [editing, setEditing] = useState(false);
  useTitle(project.data?.name ?? "Projeto");
  if (project.error) return <ErrorState message={project.error} onRetry={project.reload} />;
  if (!project.data) return <Skeleton lines={6} />;
  const p = project.data;
  const setStatus = async (status: "active" | "archived") => {
    try {
      project.setData(await api.patch<Project>(`/projects/${id}`, { status }));
      toast.notify(status === "archived" ? "Projeto arquivado." : "Projeto reativado.");
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  return (
    <div className="pagina">
      <PageHeader title={p.name} description={p.description || "Sem descrição."}
        actions={
          <>
            <a className="ui-botao ui-botao--discreto" href={href("/projetos")}>Todos os projetos</a>
            <Button icon="editar" disabled={!canAct} onClick={() => setEditing(true)}>Editar</Button>
            <Button icon={p.status === "active" ? "arquivar" : "restaurar"} disabled={!canAct} onClick={() => void setStatus(p.status === "active" ? "archived" : "active")}>
              {p.status === "active" ? "Arquivar" : "Reativar"}
            </Button>
          </>
        } />
      <p className="apoio">
        <StatusBadge tone={p.status === "active" ? "sucesso" : "neutro"}>{p.status === "active" ? "ativo" : "arquivado"}</StatusBadge> Criado em {formatDateTime(p.created_at)} · atualizado {formatRelative(p.updated_at)}
      </p>
      <div className="grade grade--2">
        <Card title={`Conversas (${p.conversation_count})`} icon="conversa">
          {conversations.data?.length ? (
            <ul className="lista-simples">{conversations.data.map((c) => <li key={c.id}><a href={href(`/conversas/${c.id}`)}>{c.title}</a><span className="apoio">{formatRelative(c.updated_at)}</span></li>)}</ul>
          ) : conversations.data ? <EmptyState title="Nenhuma conversa ligada" description="Abra uma conversa e use “Ligar a um projeto” no menu dela." icon="conversa" /> : <Skeleton />}
        </Card>
        <Card title={`Memórias (${p.memory_count})`} icon="memoria">
          {memories.data?.length ? (
            <ul className="lista-simples">{memories.data.map((m) => <li key={m.id}><span>{m.content}</span><span className="apoio">{m.kind_label}</span></li>)}</ul>
          ) : memories.data ? <EmptyState title="Nenhuma memória ligada" description="Ao registrar uma memória, escolha este projeto." icon="memoria" /> : <Skeleton />}
        </Card>
      </div>
      {editing && <ProjectForm draft={{ id, name: p.name, description: p.description }} onClose={() => setEditing(false)} onSaved={(saved) => { project.setData(saved); setEditing(false); toast.notify("Projeto salvo."); }} />}
    </div>
  );
}

export function ProjectsPage({ id }: { id?: number }) {
  if (id !== undefined) return <ProjectDetail id={id} />;
  return <ProjectList />;
}

function ProjectList() {
  useTitle("Projetos");
  const toast = useToast();
  const canAct = useCanAct();
  const [showArchived, setShowArchived] = useState(false);
  const list = useResource<Project[]>(showArchived ? "/projects" : "/projects?status=active");
  const [draft, setDraft] = useState<Draft | null>(null);
  const setStatus = async (p: Project, status: "active" | "archived") => {
    try {
      await api.patch(`/projects/${p.id}`, { status });
      toast.notify(status === "archived" ? `Projeto "${p.name}" arquivado.` : `Projeto "${p.name}" reativado.`);
      await list.reload();
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  return (
    <div className="pagina">
      <PageHeader title="Projetos" description="Agrupe conversas e memórias por assunto."
        actions={<Button variant="principal" icon="mais" disabled={!canAct} onClick={() => setDraft({ name: "", description: "" })}>Novo projeto</Button>} />
      <div className="filtros"><Switch label="Mostrar arquivados" checked={showArchived} onChange={setShowArchived} /></div>
      {list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : !list.data ? <Skeleton lines={4} /> : list.data.length === 0 ? (
        <EmptyState title="Nenhum projeto" description="Crie um projeto para reunir conversas e memórias sobre o mesmo assunto." icon="projetos"
          action={<Button variant="principal" icon="mais" disabled={!canAct} onClick={() => setDraft({ name: "", description: "" })}>Criar o primeiro projeto</Button>} />
      ) : (
        <ul className="grade grade--3 lista-cartoes">
          {list.data.map((p) => (
            <li key={p.id} className="ui-cartao cartao-projeto">
              <div className="cartao-projeto__topo">
                <h2 className="cartao-projeto__nome"><a href={href(`/projetos/${p.id}`)}>{p.name}</a></h2>
                <Menu label={`Ações do projeto ${p.name}`} items={[
                  { id: "editar", label: "Editar", icon: "editar", disabled: !canAct, onSelect: () => setDraft({ id: p.id, name: p.name, description: p.description }) },
                  p.status === "active"
                    ? { id: "arquivar", label: "Arquivar", icon: "arquivar", disabled: !canAct, onSelect: () => void setStatus(p, "archived") }
                    : { id: "reativar", label: "Reativar", icon: "restaurar", disabled: !canAct, onSelect: () => void setStatus(p, "active") },
                ]} />
              </div>
              <p className="cartao-projeto__descricao">{p.description || "Sem descrição."}</p>
              <p className="apoio">{p.conversation_count} conversas · {p.memory_count} memórias · {p.status === "active" ? "ativo" : "arquivado"}</p>
            </li>
          ))}
        </ul>
      )}
      {draft && <ProjectForm draft={draft} onClose={() => setDraft(null)} onSaved={(p) => { setDraft(null); toast.notify(draft.id ? "Projeto salvo." : `Projeto "${p.name}" criado.`); void list.reload(); }} />}
    </div>
  );
}
