import type { Block, BlockType } from "../types";

export const BLOCK_LABELS: Record<BlockType, string> = {
  heading: "Título de seção", paragraph: "Parágrafo", list: "Lista", quote: "Citação", callout: "Aviso", image: "Imagem",
  cards: "Cartões", faq: "Perguntas e respostas", button: "Botão", divider: "Divisória",
};

export function newBlock(type: BlockType, firstMediaId?: number): Block {
  switch (type) {
    case "heading": return { type, level: 2, text: "" };
    case "paragraph": return { type, text: "" };
    case "list": return { type, ordered: false, items: [""] };
    case "quote": return { type, text: "", cite: "" };
    case "callout": return { type, tone: "info", title: "", text: "" };
    case "image": return { type, media_id: firstMediaId ?? 0, caption: "" };
    case "cards": return { type, items: [{ title: "", text: "", tag: "" }] };
    case "faq": return { type, items: [{ question: "", answer: "" }] };
    case "button": return { type, label: "", href: "/" };
    case "divider": return { type };
  }
}

export function move<T>(list: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const copy = [...list];
  const [item] = copy.splice(index, 1);
  copy.splice(target, 0, item as T);
  return copy;
}

/** Conferência rápida antes de enviar; a validação que vale é a do servidor. */
export function blockProblems(blocks: Block[]): string[] {
  const problems: string[] = [];
  blocks.forEach((block, i) => {
    const n = i + 1;
    if (block.type === "heading" || block.type === "paragraph" || block.type === "quote") {
      if (!block.text.trim()) problems.push(`Bloco ${n}: o texto está vazio.`);
    } else if (block.type === "callout" && !block.text.trim()) problems.push(`Bloco ${n}: o texto do aviso está vazio.`);
    else if (block.type === "list" && block.items.some((item) => !item.trim())) problems.push(`Bloco ${n}: há item de lista vazio.`);
    else if (block.type === "image" && !block.media_id) problems.push(`Bloco ${n}: escolha uma imagem.`);
    else if (block.type === "button" && (!block.label.trim() || !/^(https?:\/\/|mailto:|\/(?!\/)|#)/.test(block.href.trim())))
      problems.push(`Bloco ${n}: o botão precisa de texto e de um endereço https://, mailto:, /caminho ou #âncora.`);
    else if (block.type === "cards" && block.items.some((c) => !c.title.trim() || !c.text.trim())) problems.push(`Bloco ${n}: há cartão sem título ou texto.`);
    else if (block.type === "faq" && block.items.some((q) => !q.question.trim() || !q.answer.trim())) problems.push(`Bloco ${n}: há pergunta sem resposta.`);
  });
  return problems;
}
