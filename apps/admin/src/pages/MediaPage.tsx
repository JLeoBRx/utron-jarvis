import { useRef, useState, type FormEvent } from "react";

import { ApiError, del, get, patch, upload } from "../api";
import { Empty, ErrorBox, Field, Loading, Modal, Notice, useAction, useLoad } from "../components/ui";
import { bytes, when } from "../format";
import { useSession } from "../session";
import type { Media } from "../types";

const ACCEPT = "image/png,image/jpeg,image/gif,image/webp";
const MAX_BYTES = 5 * 1024 * 1024;

export function MediaPage() {
  const { can } = useSession();
  const { data, error, loading, reload } = useLoad(() => get<Media[]>("/media"));
  const [selected, setSelected] = useState<Media | null>(null);
  const [alt, setAlt] = useState("");
  const [category, setCategory] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const action = useAction();
  const [message, setMessage] = useState("");

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const chosen = file.current?.files?.[0];
    if (!chosen) return;
    if (chosen.size > MAX_BYTES) {
      action.setError(new Error("O arquivo passa do limite de 5 MiB."));
      return;
    }
    const created = await action.run(() => upload<Media>("/media", chosen, { filename: chosen.name, alt_text: alt, category }));
    if (created) {
      setMessage(`Imagem enviada: ${created.original_name} (${created.width}×${created.height}).`);
      setAlt("");
      if (file.current) file.current.value = "";
      reload();
    }
  };

  return (
    <>
      <header className="pagina__cabecalho"><h1>Mídia</h1><p>PNG, JPEG, GIF ou WebP, até 5 MiB. O tipo é conferido pelo conteúdo do arquivo.</p></header>
      {can("media.upload") && (
        <form className="cartao formulario-envio" onSubmit={send}>
          <Field label="Arquivo" id="arquivo"><input id="arquivo" ref={file} type="file" accept={ACCEPT} required /></Field>
          <Field label="Texto alternativo" id="alt" hint="Descreva a imagem para quem não pode vê-la."><input id="alt" maxLength={300} value={alt} onChange={(e) => setAlt(e.target.value)} /></Field>
          <Field label="Categoria" id="categoria-midia"><input id="categoria-midia" maxLength={64} value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
          <button className="botao botao--principal" type="submit" disabled={action.busy}>{action.busy ? "Enviando…" : "Enviar"}</button>
        </form>
      )}
      {message && <Notice tone="sucesso">{message}</Notice>}
      <ErrorBox error={action.error} />
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.length === 0 && <Empty>Nenhuma imagem na biblioteca.</Empty>}
      {data && data.length > 0 && (
        <ul className="galeria">
          {data.map((m) => (
            <li key={m.id} className="galeria__item">
              <button type="button" onClick={() => setSelected(m)} aria-label={`Abrir ${m.original_name}`}>
                <img src={m.url} alt={m.alt_text} loading="lazy" width={m.width ?? undefined} height={m.height ?? undefined} />
              </button>
              <p>{m.original_name}</p>
              <p className="campo__ajuda">{m.width}×{m.height} · {bytes(m.size)}{!m.alt_text && " · sem texto alternativo"}</p>
            </li>
          ))}
        </ul>
      )}
      {selected && <MediaDialog media={selected} onClose={() => setSelected(null)} onChanged={() => { setSelected(null); reload(); }} />}
    </>
  );
}

function MediaDialog({ media, onClose, onChanged }: { media: Media; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const [alt, setAlt] = useState(media.alt_text);
  const [category, setCategory] = useState(media.category);
  const action = useAction();
  const save = async () => { if (await action.run(() => patch(`/media/${media.id}`, { alt_text: alt, category }))) onChanged(); };
  const remove = async () => {
    if (window.confirm("Remover esta imagem? O arquivo sai do servidor.") && await action.run(() => del(`/media/${media.id}`))) onChanged();
  };
  const usedIn = action.error instanceof ApiError ? (action.error.details["used_in"] as string[] | undefined) : undefined;
  return (
    <Modal title={media.original_name} onClose={onClose}>
      <img className="previa" src={media.url} alt={media.alt_text} />
      <p className="campo__ajuda">{media.content_type} · {media.width}×{media.height} · {bytes(media.size)} · enviada em {when(media.created_at)}</p>
      <p className="campo__ajuda">Endereço: <code>{media.url}</code></p>
      <fieldset disabled={!can("media.upload")}>
        <Field label="Texto alternativo" id="alt-editar"><input id="alt-editar" maxLength={300} value={alt} onChange={(e) => setAlt(e.target.value)} /></Field>
        <Field label="Categoria" id="categoria-editar"><input id="categoria-editar" maxLength={64} value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
      </fieldset>
      <ErrorBox error={action.error} />
      {usedIn && <ul>{usedIn.map((u) => <li key={u}><code>{u}</code></li>)}</ul>}
      <div className="modal__acoes">
        {can("media.delete") && <button type="button" className="botao botao--perigo" disabled={action.busy} onClick={() => void remove()}>Remover</button>}
        <button type="button" className="botao botao--secundario" onClick={onClose}>Fechar</button>
        {can("media.upload") && <button type="button" className="botao botao--principal" disabled={action.busy} onClick={() => void save()}>Salvar</button>}
      </div>
    </Modal>
  );
}
