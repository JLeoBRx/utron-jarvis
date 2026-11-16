import axe from "axe-core";

/**
 * Violações de acessibilidade encontradas pelo axe-core no nó. O contraste não é calculado aqui (o jsdom não
 * desenha): ele é conferido sobre os tokens (tests/workspace) e no navegador real (Playwright).
 */
export async function axeViolations(node: Element): Promise<string[]> {
  const result = await axe.run(node, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.help} — ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}
