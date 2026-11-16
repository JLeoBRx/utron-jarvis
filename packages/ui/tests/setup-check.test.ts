import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("estilos do pacote", () => {
  const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

  it("usam só tokens para cor (sem hexadecimais soltos)", () => {
    expect(css.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
  });

  it("animam só transform e opacity (as propriedades baratas para o navegador), salvo cor nas transições", () => {
    const keyframes = css.match(/@keyframes[^{]+\{([^{}]*\{[^}]*\})*[^}]*\}/g) ?? [];
    expect(keyframes.length).toBeGreaterThan(5);
    for (const block of keyframes) {
      const props = [...block.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
      for (const prop of props) expect(["transform", "opacity"]).toContain(prop);
    }
  });

  it("respeitam a preferência do sistema por movimento reduzido", () => {
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });
});
