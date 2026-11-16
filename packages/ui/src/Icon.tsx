import { createElement } from "react";

import { ICONS, type IconName } from "@safra/design-tokens/icons";

export type { IconName };

export type IconProps = {
  name: IconName;
  /** Tamanho em px (20 por padrão). */
  size?: number;
  /** Texto para leitores de tela. Sem ele, o ícone é decorativo e fica oculto (o texto ao lado já diz o que é). */
  label?: string;
  className?: string;
};

/** Ícone do conjunto próprio do SAFRA (packages/design-tokens/icons.json). Herda a cor do texto. */
export function Icon({ name, size = 20, label, className }: IconProps) {
  const nodes = ICONS[name];
  return (
    <svg
      className={["ui-icone", className].filter(Boolean).join(" ")}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true, focusable: "false" })}
    >
      {nodes.map(([tag, attrs], index) => createElement(tag, { key: index, ...toReact(attrs) }))}
    </svg>
  );
}

function toReact(attrs: Readonly<Record<string, string>>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(attrs)) out[key.replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase())] = value;
  return out;
}
