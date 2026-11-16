import type { CSSProperties } from 'react';

/**
 * Paleta de cores das disciplinas. Cada cor tem um tom para o tema claro e
 * outro para o escuro — usados em pequenos acentos (pontos, barras, ícones),
 * nunca em grandes áreas, para manter a interface sóbria.
 */
export interface SubjectColor {
  key: string;
  label: string;
  light: string;
  dark: string;
}

export const SUBJECT_COLORS: SubjectColor[] = [
  { key: 'indigo', label: 'Índigo', light: '#4f46e5', dark: '#818cf8' },
  { key: 'violet', label: 'Violeta', light: '#7c3aed', dark: '#a78bfa' },
  { key: 'purple', label: 'Roxo', light: '#9333ea', dark: '#c084fc' },
  { key: 'fuchsia', label: 'Fúcsia', light: '#c026d3', dark: '#e879f9' },
  { key: 'pink', label: 'Rosa', light: '#db2777', dark: '#f472b6' },
  { key: 'rose', label: 'Carmim', light: '#e11d48', dark: '#fb7185' },
  { key: 'red', label: 'Vermelho', light: '#dc2626', dark: '#f87171' },
  { key: 'orange', label: 'Laranja', light: '#ea580c', dark: '#fb923c' },
  { key: 'copper', label: 'Cobre', light: '#9a5b34', dark: '#d29b74' },
  { key: 'amber', label: 'Âmbar', light: '#d97706', dark: '#fbbf24' },
  { key: 'yellow', label: 'Amarelo', light: '#ca8a04', dark: '#facc15' },
  { key: 'lime', label: 'Lima', light: '#65a30d', dark: '#a3e635' },
  { key: 'green', label: 'Verde', light: '#16a34a', dark: '#4ade80' },
  { key: 'emerald', label: 'Esmeralda', light: '#059669', dark: '#34d399' },
  { key: 'teal', label: 'Turquesa', light: '#0d9488', dark: '#2dd4bf' },
  { key: 'cyan', label: 'Ciano', light: '#0891b2', dark: '#22d3ee' },
  { key: 'sky', label: 'Céu', light: '#0284c7', dark: '#38bdf8' },
  { key: 'blue', label: 'Azul', light: '#2563eb', dark: '#60a5fa' },
  { key: 'slate', label: 'Grafite', light: '#475569', dark: '#94a3b8' },
  { key: 'stone', label: 'Pedra', light: '#57534e', dark: '#a8a29e' },
];

const FALLBACK = SUBJECT_COLORS.find((c) => c.key === 'slate')!;

export function getSubjectColor(key: string | null | undefined): SubjectColor {
  return SUBJECT_COLORS.find((c) => c.key === key) ?? FALLBACK;
}

/** Variáveis CSS para aplicar a cor da disciplina em um elemento (`.sc`). */
export function subjectColorStyle(key: string | null | undefined): CSSProperties {
  const color = getSubjectColor(key);
  return { '--sc-l': color.light, '--sc-d': color.dark } as CSSProperties;
}
