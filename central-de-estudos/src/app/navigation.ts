import {
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  FileText,
  FolderOpen,
  Layers,
  LayoutDashboard,
  PencilLine,
  Settings,
  Timer,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  /** Fase do roteiro em que o módulo será entregue (ainda não disponível). */
  phase?: number;
}

export interface NavSection {
  label?: string;
  items: NavItem[];
}

/** Menu lateral — mesma ordem definida no escopo do projeto. */
export const NAV_SECTIONS: NavSection[] = [
  { items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }] },
  {
    label: 'Organização',
    items: [
      { to: '/disciplinas', label: 'Disciplinas', icon: BookOpen },
      { to: '/provas', label: 'Provas', icon: ClipboardCheck },
      { to: '/biblioteca', label: 'Biblioteca', icon: FolderOpen },
    ],
  },
  {
    label: 'Estudo',
    items: [
      { to: '/resumos', label: 'Resumos', icon: FileText, phase: 4 },
      { to: '/flashcards', label: 'Flashcards', icon: Layers, phase: 5 },
      { to: '/exercicios', label: 'Exercícios', icon: PencilLine, phase: 5 },
      { to: '/simulados', label: 'Simulados', icon: Timer, phase: 5 },
    ],
  },
  {
    label: 'Planejamento',
    items: [
      { to: '/calendario', label: 'Calendário', icon: CalendarDays, phase: 6 },
      { to: '/desempenho', label: 'Desempenho', icon: TrendingUp, phase: 5 },
    ],
  },
];

export const SETTINGS_ITEM: NavItem = { to: '/configuracoes', label: 'Configurações', icon: Settings };
