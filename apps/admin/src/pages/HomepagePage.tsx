import { useEffect, useState } from "react";

import { get, put } from "../api";
import { blockProblems, move } from "../components/blocks";
import { LinksEditor } from "../components/LinksEditor";
import { ErrorBox, Field, Loading, Notice, useAction, useLoad } from "../components/ui";
import type { HomeSection, Homepage, Media, SiteInfo, Tag } from "../types";

const SECTION_NAMES: Record<HomeSection["key"], string> = {
  status: "Estado do projeto", features: "Funcionalidades", hybrid_ai: "IA híbrida", security: "Segurança e privacidade",
  news: "Novidades (lista as notícias publicadas)", resources: "Documentação e downloads",
};
const TAGS: Tag[] = ["", "implementado", "em desenvolvimento", "planejado"];

export function HomepagePage() {
  const home = useLoad(() => get<Homepage>("/homepage"));
  const site = useLoad(() => get<SiteInfo>("/site"));
  const media = useLoad(() => get<Media[]>("/media"));
  const [draft, setDraft] = useState<Homepage | null>(null);
  const [info, setInfo] = useState<SiteInfo | null>(null);
  const [message, setMessage] = useState("");
  const action = useAction();
  useEffect(() => { if (home.data) setDraft(home.data); }, [home.data]);
  useEffect(() => { if (site.data) setInfo(site.data); }, [site.data]);
  if (home.loading || site.loading) return <Loading />;
  if (home.error || site.error) return <ErrorBox error={home.error ?? site.error} onRetry={() => { home.reload(); site.reload(); }} />;
  if (!draft || !info) return null;

  const section = (index: number, patch: Partial<HomeSection>) => setDraft({ ...draft, sections: draft.sections.map((s, i) => (i === index ? { ...s, ...patch } : s)) });
  const missing = (Object.keys(SECTION_NAMES) as HomeSection["key"][]).filter((key) => !draft.sections.some((s) => s.key === key));
  const save = async () => {
    setMessage("");
    const buttons = blockProblems(draft.buttons.map((b) => ({ type: "button" as const, ...b })));
    if (buttons.length) {
      action.setError(new Error("Confira os botões: cada um precisa de texto e de um endereço válido."));
      return;
    }
    const savedHome = await action.run(() => put<Homepage>("/homepage", draft));
    if (!savedHome) return;
    const savedSite = await action.run(() => put<SiteInfo>("/site", info));
    if (savedSite) setMessage("Página inicial e dados do site salvos. As mudanças já estão no ar.");
  };

  return (
    <>
      <header className="pagina__cabecalho pagina__cabecalho--acoes">
        <div><h1>Página inicial e dados do site</h1><p>Estas informações são públicas e entram no ar ao salvar.</p></div>
        <div className="acoes">
          <a className="botao botao--discreto" href="/" target="_blank" rel="noopener">Ver a página inicial</a>
          <button type="button" className="botao botao--principal" disabled={action.busy} onClick={() => void save()}>Salvar</button>
        </div>
      </header>
      {message && <Notice tone="sucesso">{message}</Notice>}
      <ErrorBox error={action.error} />
      <div className="editor">
        <div className="editor__principal">
          <section className="cartao">
            <h2>Destaque</h2>
            <Field label="Título principal" id="home-titulo"><input id="home-titulo" maxLength={120} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></Field>
            <Field label="Subtítulo" id="home-sub"><textarea id="home-sub" rows={3} maxLength={400} value={draft.subtitle} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} /></Field>
            <Field label="Imagem principal" id="home-imagem" hint="Sem imagem, o site mostra a composição com o símbolo.">
              <select id="home-imagem" value={draft.image_media_id ?? ""} onChange={(e) => setDraft({ ...draft, image_media_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Composição padrão</option>
                {(media.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.original_name}</option>)}
              </select>
            </Field>
            <p className="rotulo">Botões (até 3)</p>
            <LinksEditor value={draft.buttons} onChange={(buttons) => setDraft({ ...draft, buttons })} max={3} idPrefix="botao" />
          </section>
          <h2 className="editor__secao">Seções, na ordem em que aparecem</h2>
          {draft.sections.map((s, index) => (
            <section key={s.key} className="cartao" aria-label={SECTION_NAMES[s.key]}>
              <header className="bloco__cabecalho">
                <label className="caixa"><input type="checkbox" checked={s.enabled} onChange={(e) => section(index, { enabled: e.target.checked })} /> {SECTION_NAMES[s.key]}</label>
                <span className="bloco__acoes">
                  <button type="button" className="botao botao--discreto" aria-label="Mover para cima" disabled={index === 0} onClick={() => setDraft({ ...draft, sections: move(draft.sections, index, -1) })}>↑</button>
                  <button type="button" className="botao botao--discreto" aria-label="Mover para baixo" disabled={index === draft.sections.length - 1} onClick={() => setDraft({ ...draft, sections: move(draft.sections, index, 1) })}>↓</button>
                  <button type="button" className="botao botao--discreto" onClick={() => setDraft({ ...draft, sections: draft.sections.filter((_, i) => i !== index) })}>Retirar</button>
                </span>
              </header>
              <Field label="Título" id={`sec-${s.key}-titulo`}><input id={`sec-${s.key}-titulo`} maxLength={120} value={s.title} onChange={(e) => section(index, { title: e.target.value })} /></Field>
              <Field label="Texto" id={`sec-${s.key}-texto`}><textarea id={`sec-${s.key}-texto`} rows={2} maxLength={800} value={s.text} onChange={(e) => section(index, { text: e.target.value })} /></Field>
              {s.key !== "news" && (
                <>
                  <p className="rotulo">Destaques</p>
                  {s.items.map((item, i) => (
                    <div key={i} className="cartao-editor">
                      <div className="linha">
                        <input aria-label="Título do destaque" maxLength={120} value={item.title} onChange={(e) => section(index, { items: s.items.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)) })} />
                        <select aria-label="Estado" value={item.tag} onChange={(e) => section(index, { items: s.items.map((x, j) => (j === i ? { ...x, tag: e.target.value as Tag } : x)) })}>
                          {TAGS.map((t) => <option key={t} value={t}>{t || "sem selo"}</option>)}
                        </select>
                        <button type="button" className="botao botao--discreto" onClick={() => section(index, { items: s.items.filter((_, j) => j !== i) })}>Remover</button>
                      </div>
                      <textarea aria-label="Texto do destaque" rows={2} maxLength={600} value={item.text} onChange={(e) => section(index, { items: s.items.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
                    </div>
                  ))}
                  {s.items.length < 12 && <button type="button" className="botao botao--secundario" onClick={() => section(index, { items: [...s.items, { title: "", text: "", tag: "" }] })}>Adicionar destaque</button>}
                </>
              )}
              <p className="rotulo">Links da seção</p>
              <LinksEditor value={s.links} onChange={(links) => section(index, { links })} max={6} idPrefix={`sec-${s.key}-link`} />
            </section>
          ))}
          {missing.length > 0 && (
            <div className="filtros">
              {missing.map((key) => (
                <button key={key} type="button" className="botao botao--secundario"
                  onClick={() => setDraft({ ...draft, sections: [...draft.sections, { key, enabled: true, title: SECTION_NAMES[key].split(" (")[0] ?? key, text: "", items: [], links: [] }] })}>
                  Incluir “{SECTION_NAMES[key]}”
                </button>
              ))}
            </div>
          )}
        </div>
        <aside className="editor__lateral">
          <section className="cartao">
            <h2>Notícias em destaque</h2>
            <Field label="Quantidade na página inicial" id="destaques"><input id="destaques" type="number" min={0} max={6} value={draft.featured_news} onChange={(e) => setDraft({ ...draft, featured_news: Number(e.target.value) })} /></Field>
          </section>
          <section className="cartao">
            <h2>Rodapé e contato</h2>
            <Field label="Lema" id="lema"><input id="lema" maxLength={200} value={info.tagline} onChange={(e) => setInfo({ ...info, tagline: e.target.value })} /></Field>
            <Field label="Texto do rodapé" id="rodape"><textarea id="rodape" rows={3} maxLength={400} value={info.footer_text} onChange={(e) => setInfo({ ...info, footer_text: e.target.value })} /></Field>
            <p className="rotulo">Links do rodapé</p>
            <LinksEditor value={info.footer_links} onChange={(footer_links) => setInfo({ ...info, footer_links })} max={12} idPrefix="rodape-link" />
            <Field label="E-mail de contato" id="contato"><input id="contato" type="email" maxLength={254} value={info.contact_email} onChange={(e) => setInfo({ ...info, contact_email: e.target.value })} /></Field>
            <p className="rotulo">Outros canais de contato</p>
            <LinksEditor value={info.contact_links} onChange={(contact_links) => setInfo({ ...info, contact_links })} max={8} idPrefix="contato-link" />
          </section>
        </aside>
      </div>
    </>
  );
}
