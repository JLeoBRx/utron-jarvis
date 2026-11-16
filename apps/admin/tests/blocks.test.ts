import { describe, expect, it } from "vitest";

import { BLOCK_LABELS, blockProblems, move, newBlock } from "../src/components/blocks";
import { slugify } from "../src/pages/ContentEditor";
import type { BlockType } from "../src/types";

describe("blocos de conteúdo", () => {
  it("cria um bloco válido de cada tipo", () => {
    for (const type of Object.keys(BLOCK_LABELS) as BlockType[]) {
      expect(newBlock(type, 7).type).toBe(type);
    }
    expect(newBlock("image", 7)).toEqual({ type: "image", media_id: 7, caption: "" });
  });

  it("move blocos sem sair da lista", () => {
    expect(move([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(move([1, 2, 3], 2, 1)).toEqual([1, 2, 3]);
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });

  it("aponta problemas antes de enviar", () => {
    expect(blockProblems([{ type: "paragraph", text: "ok" }])).toEqual([]);
    expect(blockProblems([{ type: "paragraph", text: "  " }])[0]).toContain("Bloco 1");
    expect(blockProblems([{ type: "button", label: "x", href: "javascript:alert(1)" }])).toHaveLength(1);
    expect(blockProblems([{ type: "button", label: "x", href: "//evil.example" }])).toHaveLength(1);
    expect(blockProblems([{ type: "button", label: "x", href: "/sobre" }])).toEqual([]);
    expect(blockProblems([{ type: "image", media_id: 0, caption: "" }])).toHaveLength(1);
  });

  it("gera endereços aceitos pelo servidor", () => {
    expect(slugify("Inteligência Artificial: o básico!")).toBe("inteligencia-artificial-o-basico");
    expect(slugify("  --  ")).toBe("");
    expect(slugify("x".repeat(100))).toHaveLength(80);
  });
});
