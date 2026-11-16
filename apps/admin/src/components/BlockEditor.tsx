import { useState } from "react";

import type { Block, BlockType, Media, Tag } from "../types";
import { BLOCK_LABELS, move, newBlock } from "./blocks";

const TAGS: Tag[] = ["", "implementado", "em desenvolvimento", "planejado"];

export function BlockEditor({ blocks, onChange, media }: { blocks: Block[]; onChange: (b: Block[]) => void; media: Media[] }) {
  const [adding, setAdding] = useState<BlockType>("paragraph");
  const replace = (index: number, block: Block) => onChange(blocks.map((b, i) => (i === index ? block : b)));
  return (
    <div className="blocos">
      {blocks.length === 0 && <p className="estado estado--vazio">Nenhum bloco ainda. Adicione o primeiro abaixo.</p>}
      {blocks.map((block, index) => (
        <section className="bloco" key={index} aria-label={`Bloco ${index + 1}: ${BLOCK_LABELS[block.type]}`}>
          <header className="bloco__cabecalho">
            <span className="bloco__tipo">{index + 1}. {BLOCK_LABELS[block.type]}</span>
            <span className="bloco__acoes">
              <button type="button" className="botao botao--discreto" aria-label="Mover para cima" disabled={index === 0}
                onClick={() => onChange(move(blocks, index, -1))}>↑</button>
              <button type="button" className="botao botao--discreto" aria-label="Mover para baixo" disabled={index === blocks.length - 1}
                onClick={() => onChange(move(blocks, index, 1))}>↓</button>
              <button type="button" className="botao botao--discreto" onClick={() => onChange(blocks.filter((_, i) => i !== index))}>Remover</button>
            </span>
          </header>
          <BlockFields block={block} onChange={(b) => replace(index, b)} media={media} id={`bloco-${index}`} />
        </section>
      ))}
      <div className="blocos__novo">
        <label htmlFor="novo-bloco">Novo bloco</label>
        <select id="novo-bloco" value={adding} onChange={(e) => setAdding(e.target.value as BlockType)}>
          {(Object.keys(BLOCK_LABELS) as BlockType[]).map((type) => <option key={type} value={type}>{BLOCK_LABELS[type]}</option>)}
        </select>
        <button type="button" className="botao botao--secundario" onClick={() => onChange([...blocks, newBlock(adding, media[0]?.id)])}>Adicionar</button>
      </div>
      <p className="campo__ajuda">Nos textos valem <code>**negrito**</code>, <code>*itálico*</code>, <code>`código`</code> e <code>[texto](endereço)</code>. HTML é exibido como texto.</p>
    </div>
  );
}

function BlockFields({ block, onChange, media, id }: { block: Block; onChange: (b: Block) => void; media: Media[]; id: string }) {
  switch (block.type) {
    case "heading":
      return (
        <div className="linha">
          <select aria-label="Nível" value={block.level} onChange={(e) => onChange({ ...block, level: Number(e.target.value) as 2 | 3 })}>
            <option value={2}>Seção</option><option value={3}>Subseção</option>
          </select>
          <input aria-label="Texto do título" id={id} value={block.text} maxLength={200} onChange={(e) => onChange({ ...block, text: e.target.value })} />
        </div>
      );
    case "paragraph":
      return <textarea aria-label="Texto" id={id} rows={4} maxLength={4000} value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} />;
    case "quote":
      return (
        <>
          <textarea aria-label="Citação" id={id} rows={3} maxLength={4000} value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} />
          <input aria-label="Fonte" placeholder="Fonte (opcional)" maxLength={200} value={block.cite} onChange={(e) => onChange({ ...block, cite: e.target.value })} />
        </>
      );
    case "callout":
      return (
        <>
          <div className="linha">
            <select aria-label="Tom do aviso" value={block.tone} onChange={(e) => onChange({ ...block, tone: e.target.value as typeof block.tone })}>
              <option value="info">Informação</option><option value="attention">Atenção</option><option value="status">Estado do projeto</option>
            </select>
            <input aria-label="Título do aviso" placeholder="Título (opcional)" maxLength={200} value={block.title} onChange={(e) => onChange({ ...block, title: e.target.value })} />
          </div>
          <textarea aria-label="Texto do aviso" id={id} rows={3} maxLength={4000} value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} />
        </>
      );
    case "list":
      return (
        <>
          <label className="caixa"><input type="checkbox" checked={block.ordered} onChange={(e) => onChange({ ...block, ordered: e.target.checked })} /> Numerada</label>
          {block.items.map((item, i) => (
            <div className="linha" key={i}>
              <input aria-label={`Item ${i + 1}`} value={item} maxLength={1000} onChange={(e) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? e.target.value : x)) })} />
              <button type="button" className="botao botao--discreto" disabled={block.items.length === 1} onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}>Remover</button>
            </div>
          ))}
          <button type="button" className="botao botao--secundario" onClick={() => onChange({ ...block, items: [...block.items, ""] })}>Adicionar item</button>
        </>
      );
    case "image":
      return media.length === 0 ? <p className="estado estado--vazio">Envie uma imagem em Mídia para usá-la aqui.</p> : (
        <div className="linha">
          <select aria-label="Imagem" id={id} value={block.media_id} onChange={(e) => onChange({ ...block, media_id: Number(e.target.value) })}>
            <option value={0}>Escolha…</option>
            {media.map((m) => <option key={m.id} value={m.id}>{m.original_name}{m.alt_text ? "" : " (sem texto alternativo)"}</option>)}
          </select>
          <input aria-label="Legenda" placeholder="Legenda (opcional)" maxLength={300} value={block.caption} onChange={(e) => onChange({ ...block, caption: e.target.value })} />
        </div>
      );
    case "cards":
      return (
        <>
          {block.items.map((card, i) => (
            <div className="cartao-editor" key={i}>
              <div className="linha">
                <input aria-label={`Título do cartão ${i + 1}`} placeholder="Título" maxLength={200} value={card.title}
                  onChange={(e) => onChange({ ...block, items: block.items.map((c, j) => (j === i ? { ...c, title: e.target.value } : c)) })} />
                <select aria-label={`Estado do cartão ${i + 1}`} value={card.tag}
                  onChange={(e) => onChange({ ...block, items: block.items.map((c, j) => (j === i ? { ...c, tag: e.target.value as Tag } : c)) })}>
                  {TAGS.map((t) => <option key={t} value={t}>{t || "sem selo"}</option>)}
                </select>
                <button type="button" className="botao botao--discreto" disabled={block.items.length === 1}
                  onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}>Remover</button>
              </div>
              <textarea aria-label={`Texto do cartão ${i + 1}`} rows={2} maxLength={1000} value={card.text}
                onChange={(e) => onChange({ ...block, items: block.items.map((c, j) => (j === i ? { ...c, text: e.target.value } : c)) })} />
            </div>
          ))}
          <button type="button" className="botao botao--secundario" onClick={() => onChange({ ...block, items: [...block.items, { title: "", text: "", tag: "" }] })}>Adicionar cartão</button>
        </>
      );
    case "faq":
      return (
        <>
          {block.items.map((q, i) => (
            <div className="cartao-editor" key={i}>
              <div className="linha">
                <input aria-label={`Pergunta ${i + 1}`} placeholder="Pergunta" maxLength={200} value={q.question}
                  onChange={(e) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, question: e.target.value } : x)) })} />
                <button type="button" className="botao botao--discreto" disabled={block.items.length === 1}
                  onClick={() => onChange({ ...block, items: block.items.filter((_, j) => j !== i) })}>Remover</button>
              </div>
              <textarea aria-label={`Resposta ${i + 1}`} rows={2} maxLength={4000} value={q.answer}
                onChange={(e) => onChange({ ...block, items: block.items.map((x, j) => (j === i ? { ...x, answer: e.target.value } : x)) })} />
            </div>
          ))}
          <button type="button" className="botao botao--secundario" onClick={() => onChange({ ...block, items: [...block.items, { question: "", answer: "" }] })}>Adicionar pergunta</button>
        </>
      );
    case "button":
      return (
        <div className="linha">
          <input aria-label="Texto do botão" id={id} placeholder="Texto" maxLength={60} value={block.label} onChange={(e) => onChange({ ...block, label: e.target.value })} />
          <input aria-label="Endereço do botão" placeholder="/pagina ou https://…" maxLength={500} value={block.href} onChange={(e) => onChange({ ...block, href: e.target.value })} />
        </div>
      );
    case "divider":
      return <p className="campo__ajuda">Linha divisória entre seções.</p>;
  }
}
