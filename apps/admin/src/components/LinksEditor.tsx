import type { Link } from "../types";

export function LinksEditor({ value, onChange, max, idPrefix }: { value: Link[]; onChange: (v: Link[]) => void; max: number; idPrefix: string }) {
  const update = (index: number, patch: Partial<Link>) => onChange(value.map((link, i) => (i === index ? { ...link, ...patch } : link)));
  return (
    <div className="lista-editavel">
      {value.map((link, index) => (
        <div className="lista-editavel__linha" key={index}>
          <input aria-label="Texto do link" id={`${idPrefix}-rotulo-${index}`} value={link.label} maxLength={60} placeholder="Texto"
            onChange={(e) => update(index, { label: e.target.value })} />
          <input aria-label="Endereço do link" value={link.href} maxLength={500} placeholder="/pagina ou https://…"
            onChange={(e) => update(index, { href: e.target.value })} />
          <button type="button" className="botao botao--discreto" onClick={() => onChange(value.filter((_, i) => i !== index))}>Remover</button>
        </div>
      ))}
      {value.length < max && (
        <button type="button" className="botao botao--secundario" onClick={() => onChange([...value, { label: "", href: "/" }])}>Adicionar link</button>
      )}
    </div>
  );
}
