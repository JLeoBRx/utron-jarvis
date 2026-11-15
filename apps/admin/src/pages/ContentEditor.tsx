import { useEffect, useState } from "react";

import { ApiError, del, get, post, put } from "../api";
import { BlockEditor } from "../components/BlockEditor";
import { blockProblems } from "../components/blocks";
import { Badge, ErrorBox, Field, Loading, Modal, Notice, useAction, useLoad } from "../components/ui";
import { when } from "../format";
import { go, href } from "../router";
import { useSession } from "../session";
import type { Block, Category, Content, ContentKind, Media, Version } from "../types";
import { KIND_LABEL } from "./ContentList";

interface Draft {
  slug: string;
  title: string;
  summary: string;
  blocks: Block[];
  seo_title: string;
  seo_description: string;
  cover_media_id: number | null;
  category_id: number | null;
}

const EMPTY: Draft = { slug: "", title: "", summary: "", blocks: [{ type: "paragraph", text: "" }], seo_title: "", seo_description: "",
  cover_media_id: null, category_id: null };

export function slugify(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
}

export function ContentEditor({ kind, id }: { kind: ContentKind; id: number | null }) {
  const { can } = useSession();
  const label = KIND_LABEL[kind];
  const editable = can("content.edit");
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [content, setContent] = useState<Content | null>(null);
  const [dirty, setDirty] = useState(false);
  const [slugTouched, setSlugTouched] = useState(id !== null);
  const [message, setMessage] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewing, setViewing] = useState<(Version & { blocks?: Block[]; summary?: string }) | null>(null);
  const action = useAction();
  const media = useLoad(() => (can("media.read") ? get<Media[]>("/media") : Promise.resolve([])), []);
  const categories = useLoad(() => (kind === "news" ? get<Category[]>("/categories") : Promise.resolve([])), [kind]);
  const loaded = useLoad(() => (id === null ? Promise.resolve(null) : get<Content>(`/${kind}/${id}`)), [kind, id]);
  const versions = useLoad(() => (id === null ? Promise.resolve([] as Version[]) : get<Version[]>(`/${kind}/${id}/versions`)), [kind, id]);

  const adopt = (value: Content) => {
    setContent(value);
    setDraft({ slug: value.slug, title: value.title, summary: value.summary, blocks: value.blocks, seo_title: value.seo_title,
      seo_description: value.seo_description, cover_media_id: value.cover_media_id, category_id: value.category_id });
    setDirty(false);
  };
  useEffect(() => { if (loaded.data) adopt(loaded.data); }, [loaded.data]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const change = (patch: Partial<Draft>) => {
    setDraft((current) => ({ ...current, ...patch, ...(patch.title !== undefined && !slugTouched ? { slug: slugify(patch.title) } : {}) }));
    setDirty(true);
    setMessage("");
  };

  const save = async () => {
    const problems = blockProblems(draft.blocks);
    if (problems.length) {
      action.setError(new Error(problems.join(" ")));
      return;
    }
    const saved = await action.run(() => (content
      ? put<Content>(`/${kind}/${content.id}`, { ...draft, lock_version: content.lock_version })
      : post<Content>(`/${kind}`, draft)));
    if (!saved) return;
    if (!content) {
      setDirty(false);
      go(`${kind}/${saved.id}`);
      return;
    }
    adopt(saved);
    versions.reload();
    setMessage("Rascunho salvo como nova versão.");
  };

  const transition = async (verb: "publish" | "unpublish") => {
    if (!content) return;
    const result = await action.run(() => post<Content>(`/${kind}/${content.id}/${verb}`));
    if (result) {
      adopt(result);
      versions.reload();
      setMessage(verb === "publish" ? "Publicado. A versão mais recente está no ar." : "Despublicado. O conteúdo saiu do site.");
    }
  };

  const restore = async (version: Version) => {
    if (!content) return;
    const result = await action.run(() => post<Content>(`/${kind}/${content.id}/versions/${version.id}/restore`));
    if (result) {
      setViewing(null);
      loaded.reload();
      versions.reload();
      setMessage(`Versão ${version.number} restaurada como rascunho. Publique para colocá-la no ar.`);
    }
  };

  const open = async (version: Version) => {
    if (!content) return;
    const full = await action.run(() => get<Version & { blocks: Block[]; summary: string }>(`/${kind}/${content.id}/versions/${version.id}`));
    if (full) setViewing({ ...version, ...full });
  };

  if (id !== null && loaded.loading && !content) return <Loading />;
  if (loaded.error) return <ErrorBox error={loaded.error} onRetry={loaded.reload} />;
  const conflict = action.error instanceof ApiError && action.error.status === 409 && action.error.details["current_lock_version"] !== undefined;

  return (
    <>
      <header className="pagina__cabecalho pagina__cabecalho--acoes">
        <div>
          <p className="trilha"><a href={href(kind)}>{label.plural}</a></p>
          <h1>{content ? content.title : label.novo}</h1>
          {content && (
            <p className="pagina__estado">
              <Badge status={content.status} />
              {content.has_unpublished_changes && <span className="selo selo--pendente">alterações não publicadas</span>}
              {dirty && <span className="selo selo--pendente">não salvo</span>}
              <span>Atualizado em {when(content.updated_at)}</span>
            </p>
          )}
        </div>
        <div className="acoes">
          {content && <a className="botao botao--discreto" href={content.preview_path} target="_blank" rel="noopener">Pré-visualizar rascunho</a>}
          {content?.public_path && <a className="botao botao--discreto" href={content.public_path} target="_blank" rel="noopener">Ver publicado</a>}
          {editable && <button type="button" className="botao botao--principal" disabled={action.busy || (!dirty && !!content)} onClick={() => void save()}>{content ? "Salvar rascunho" : "Criar rascunho"}</button>}
          {content && can("content.publish") && (
            <>
              <button type="button" className="botao botao--secundario" disabled={action.busy || dirty} title={dirty ? "Salve antes de publicar" : undefined}
                onClick={() => void transition("publish")}>{content.status === "published" ? "Publicar alterações" : "Publicar"}</button>
              {content.status === "published" && <button type="button" className="botao botao--secundario" disabled={action.busy} onClick={() => void transition("unpublish")}>Despublicar</button>}
            </>
          )}
        </div>
      </header>
      {message && <Notice tone="sucesso">{message}</Notice>}
      {conflict ? (
        <div className="alerta alerta--erro" role="alert">
          <p>{(action.error as ApiError).message}</p>
          <button type="button" className="botao botao--secundario" onClick={() => { action.setError(null); loaded.reload(); }}>Recarregar a versão atual (descarta suas alterações)</button>
        </div>
      ) : <ErrorBox error={action.error} />}
      <div className="editor">
        <fieldset className="editor__principal" disabled={!editable}>
          <legend className="visualmente-oculto">Conteúdo</legend>
          <Field label="Título" id="titulo"><input id="titulo" required maxLength={200} value={draft.title} onChange={(e) => change({ title: e.target.value })} /></Field>
          <Field label="Endereço (slug)" id="slug" hint={`Fica em ${kind === "pages" ? "/" : "/atualizacoes/"}${draft.slug || "…"}. Letras minúsculas, números e hífens.`}>
            <input id="slug" required maxLength={80} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={draft.slug}
              onChange={(e) => { setSlugTouched(true); change({ slug: e.target.value }); }} />
          </Field>
          <Field label="Resumo" id="resumo" hint="Aparece abaixo do título e nas listagens."><textarea id="resumo" rows={2} maxLength={500} value={draft.summary} onChange={(e) => change({ summary: e.target.value })} /></Field>
          <h2 className="editor__secao">Conteúdo</h2>
          <BlockEditor blocks={draft.blocks} onChange={(blocks) => change({ blocks })} media={media.data ?? []} />
        </fieldset>
        <aside className="editor__lateral">
          <fieldset className="cartao" disabled={!editable}>
            <legend>SEO</legend>
            <Field label="Título para buscadores" id="seo-titulo" hint="Vazio usa o título."><input id="seo-titulo" maxLength={200} value={draft.seo_title} onChange={(e) => change({ seo_title: e.target.value })} /></Field>
            <Field label="Descrição para buscadores" id="seo-descricao" hint={`${draft.seo_description.length}/300. Vazia usa o resumo.`}>
              <textarea id="seo-descricao" rows={3} maxLength={300} value={draft.seo_description} onChange={(e) => change({ seo_description: e.target.value })} />
            </Field>
          </fieldset>
          <fieldset className="cartao" disabled={!editable}>
            <legend>Imagem e classificação</legend>
            <Field label="Imagem de destaque" id="capa">
              <select id="capa" value={draft.cover_media_id ?? ""} onChange={(e) => change({ cover_media_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Nenhuma</option>
                {(media.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.original_name}</option>)}
              </select>
            </Field>
            {kind === "news" && (
              <Field label="Categoria" id="categoria">
                <select id="categoria" value={draft.category_id ?? ""} onChange={(e) => change({ category_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Sem categoria</option>
                  {(categories.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
            )}
          </fieldset>
          {content && (
            <section className="cartao" aria-labelledby="versoes">
              <h2 id="versoes">Versões</h2>
              {versions.loading && <Loading />}
              <ol className="versoes">
                {(versions.data ?? []).map((v) => (
                  <li key={v.id}>
                    <button type="button" className="botao botao--discreto" onClick={() => void open(v)}>v{v.number}</button>
                    <span>{v.author || "sistema"} · {when(v.created_at)}{v.published && <> · <strong>publicada</strong></>}{v.note && <> · {v.note}</>}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {content && can("content.delete") && (
            <section className="cartao cartao--perigo" aria-labelledby="excluir">
              <h2 id="excluir">Excluir</h2>
              <p>O conteúdo sai do site e do painel. O registro e as versões ficam guardados no banco.</p>
              <button type="button" className="botao botao--perigo" onClick={() => setConfirmDelete(true)}>Excluir {label.singular}</button>
            </section>
          )}
        </aside>
      </div>
      {viewing && content && (
        <Modal title={`Versão ${viewing.number}`} onClose={() => setViewing(null)}>
          <p><strong>{viewing.title}</strong></p>
          {viewing.summary && <p>{viewing.summary}</p>}
          <p className="campo__ajuda">{viewing.blocks?.length ?? 0} blocos · {viewing.author || "sistema"} · {when(viewing.created_at)}</p>
          <div className="modal__acoes">
            <button type="button" className="botao botao--secundario" onClick={() => setViewing(null)}>Fechar</button>
            {editable && <button type="button" className="botao botao--principal" disabled={action.busy} onClick={() => void restore(viewing)}>Restaurar como rascunho</button>}
          </div>
        </Modal>
      )}
      {confirmDelete && content && <DeleteDialog kind={kind} content={content} onClose={() => setConfirmDelete(false)} />}
    </>
  );
}

function DeleteDialog({ kind, content, onClose }: { kind: ContentKind; content: Content; onClose: () => void }) {
  const [typed, setTyped] = useState("");
  const action = useAction();
  const confirm = async () => {
    const ok = await action.run(() => del(`/${kind}/${content.id}`, { confirm_slug: typed }));
    if (ok) go(kind);
  };
  return (
    <Modal title="Confirmar exclusão" onClose={onClose}>
      <p>Para excluir <strong>{content.title}</strong>, digite o endereço <code>{content.slug}</code>.</p>
      <Field label="Endereço" id="confirmar-slug"><input id="confirmar-slug" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></Field>
      <ErrorBox error={action.error} />
      <div className="modal__acoes">
        <button type="button" className="botao botao--secundario" onClick={onClose}>Cancelar</button>
        <button type="button" className="botao botao--perigo" disabled={typed !== content.slug || action.busy} onClick={() => void confirm()}>Excluir</button>
      </div>
    </Modal>
  );
}
