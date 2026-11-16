import { useEffect, useState, type FormEvent } from "react";

import { Button, ConfirmDialog, EmptyState, ErrorState, Menu, Modal, SearchField, Select, Skeleton, StatusBadge, Switch, TextArea, useToast } from "@safra/ui";

import { api, messageOf } from "../api";
import { PageHeader, useCanAct } from "../components";
import { formatRelative } from "../format";
import { useResource, useTitle } from "../hooks";
import type { Memory, MemoryKind, Project } from "../types";

const KINDS: Array<{ value: MemoryKind; label: string }> = [
  { value: "note", label: "Nota" }, { value: "fact", label: "Fato" }, { value: "reminder", label: "Lembrete" },
  { value: "procedure", label: "Procedimento" }, { value: "episode", label: "Episódio" },
];
const IMPORTANCE = ["normal", "relevante", "importante", "essencial"];
type Draft = { id?: number; kind: MemoryKind; content: string; project_id: string; importance: string };

function MemoryForm({ draft, projects, onClose, onSaved }: { draft: Draft; projects: Project[]; onClose: () => void; onSaved: () => void }) {
  const [value, setValue] = useState(draft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const body = { kind: value.kind, content: value.content, project_id: value.project_id ? Number(value.project_id) : null, importance: Number(value.importance) };
    try {
      if (draft.id) await api.patch(`/memories/${draft.id}`, body);
      else await api.post("/memories", body);
      onSaved();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal open title={draft.id ? "Editar memória" : "Registrar na memória"} onClose={onClose}
      description="O que você registrar aqui fica no banco privado deste computador.">
      <form className="formulario" onSubmit={submit}>
        <Select label="Tipo" value={value.kind} options={KINDS} onChange={(e) => setValue({ ...value, kind: e.target.value as MemoryKind })} />
        <TextArea label="Conteúdo" required maxLength={5000} value={value.content} error={error} onChange={(e) => setValue({ ...value, content: e.target.value })} />
        <div className="formulario__linha">
          <Select label="Projeto" value={value.project_id} options={[{ value: "", label: "Nenhum" }, ...projects.map((p) => ({ value: String(p.id), label: p.name }))]}
            onChange={(e) => setValue({ ...value, project_id: e.target.value })} />
          <Select label="Importância" value={value.importance} options={IMPORTANCE.map((label, i) => ({ value: String(i), label }))}
            onChange={(e) => setValue({ ...value, importance: e.target.value })} />
        </div>
        <div className="formulario__acoes">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="principal" loading={saving}>{draft.id ? "Salvar" : "Registrar"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function MemoryPage() {
  useTitle("Memória");
  const toast = useToast();
  const canAct = useCanAct();
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [trash, setTrash] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [toTrash, setToTrash] = useState<Memory | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const params = new URLSearchParams({ ...(kind ? { kind } : {}), ...(debounced ? { q: debounced } : {}), ...(trash ? { trash: "true" } : {}) });
  const list = useResource<Memory[]>(`/memories?${params.toString()}`);
  const projects = useResource<Project[]>("/projects?status=active");
  const projectName = (id: number | null) => projects.data?.find((p) => p.id === id)?.name;

  const restore = async (m: Memory) => {
    try {
      await api.post(`/memories/${m.id}/restore`);
      toast.notify("Memória restaurada.");
      await list.reload();
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  const confirmTrash = async () => {
    if (!toTrash) return;
    try {
      await api.del(`/memories/${toTrash.id}`);
      toast.notify("Memória movida para a lixeira. Você pode restaurá-la.");
      setToTrash(null);
      await list.reload();
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  const blank: Draft = { kind: "note", content: "", project_id: "", importance: "0" };

  return (
    <div className="pagina">
      <PageHeader title="Memória" description="Fatos, notas, lembretes e procedimentos que você quer que o SAFRA guarde."
        actions={<Button variant="principal" icon="mais" disabled={!canAct || trash} onClick={() => setDraft(blank)}>Registrar</Button>} />
      <div className="filtros">
        <SearchField label="Buscar" placeholder="Palavras da memória" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Select label="Tipo" value={kind} options={[{ value: "", label: "Todos" }, ...KINDS]} onChange={(e) => setKind(e.target.value)} />
        <Switch label="Lixeira" checked={trash} onChange={setTrash} />
      </div>
      {list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : !list.data ? <Skeleton lines={5} /> : list.data.length === 0 ? (
        <EmptyState title={trash ? "A lixeira está vazia" : debounced || kind ? "Nada encontrado" : "Nada registrado ainda"}
          description={trash ? undefined : "Registre algo que o SAFRA deve lembrar: um fato, uma nota, um lembrete."} icon="memoria"
          action={!trash && !debounced && !kind ? <Button variant="principal" icon="mais" disabled={!canAct} onClick={() => setDraft(blank)}>Registrar a primeira</Button> : undefined} />
      ) : (
        <ul className="lista-memorias">
          {list.data.map((m) => (
            <li key={m.id} className="ui-cartao memoria">
              <div className="memoria__topo">
                <StatusBadge tone="neutro" icon="categoria">{m.kind_label}</StatusBadge>
                {m.importance > 0 && <StatusBadge tone="marca" icon="alerta">{IMPORTANCE[m.importance]}</StatusBadge>}
                {projectName(m.project_id) && <StatusBadge tone="informacao" icon="projetos">{projectName(m.project_id)}</StatusBadge>}
                <span className="memoria__acoes">
                  {trash ? (
                    <Button size="pequeno" icon="restaurar" disabled={!canAct} onClick={() => void restore(m)}>Restaurar</Button>
                  ) : (
                    <Menu label="Ações da memória" items={[
                      { id: "editar", label: "Editar", icon: "editar", disabled: !canAct, onSelect: () => setDraft({ id: m.id, kind: m.kind, content: m.content, project_id: m.project_id ? String(m.project_id) : "", importance: String(m.importance) }) },
                      { id: "lixeira", label: "Mover para a lixeira", icon: "lixeira", danger: true, disabled: !canAct, onSelect: () => setToTrash(m) },
                    ]} />
                  )}
                </span>
              </div>
              <p className="memoria__conteudo">{m.content}</p>
              <p className="apoio">Registrada por você · atualizada {formatRelative(m.updated_at)}</p>
            </li>
          ))}
        </ul>
      )}
      {draft && <MemoryForm draft={draft} projects={projects.data ?? []} onClose={() => setDraft(null)} onSaved={() => { setDraft(null); toast.notify(draft.id ? "Memória salva." : "Registrado na memória."); void list.reload(); }} />}
      <ConfirmDialog open={toTrash !== null} title="Mover para a lixeira?" message="A memória sai da lista e pode ser restaurada pela lixeira." confirmLabel="Mover para a lixeira"
        variant="perigo" onConfirm={() => void confirmTrash()} onCancel={() => setToTrash(null)} />
    </div>
  );
}
