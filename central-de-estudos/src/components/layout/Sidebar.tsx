import { Check, ChevronsUpDown, Cloud, HardDrive, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Sun } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router';
import { NAV_SECTIONS, SETTINGS_ITEM, type NavItem } from '@/app/navigation';
import { useSession } from '@/app/session';
import { useTheme } from '@/app/theme';
import { useBackend } from '@/data/DataContext';
import { useAction, useWorkspace } from '@/data/hooks';
import { setActiveAcademicYear } from '@/data/services/workspace';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/DropdownMenu';
import { Tooltip } from '../ui/Tooltip';
import { Logo } from './Logo';

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onNavigate?: () => void;
  className?: string;
}

function NavEntry({ item, collapsed, onNavigate }: { item: NavItem; collapsed?: boolean; onNavigate?: () => void }) {
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex h-8 items-center gap-2.5 rounded-lg text-[13px] font-medium transition-colors',
          collapsed ? 'w-9 justify-center' : 'px-2.5',
          isActive ? 'bg-surface-2 text-fg dark:bg-surface-3' : 'text-fg-muted hover:bg-surface-2 hover:text-fg',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <span className="absolute top-1.5 bottom-1.5 -left-2 w-0.5 rounded-full bg-accent" aria-hidden />
          ) : null}
          <Icon className={cn('size-4 shrink-0', isActive ? 'text-accent-text' : 'text-fg-subtle group-hover:text-fg-muted')} />
          {!collapsed ? (
            <>
              <span className="truncate">{item.label}</span>
              {item.phase ? (
                <span className="ml-auto text-[10px] font-normal text-fg-subtle" title={`Disponível na Fase ${item.phase}`}>
                  Fase {item.phase}
                </span>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </NavLink>
  );
  return collapsed ? (
    <Tooltip content={item.phase ? `${item.label} · Fase ${item.phase}` : item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function YearSwitcher({ collapsed }: { collapsed?: boolean }) {
  const { years, activeYear } = useWorkspace();
  const navigate = useNavigate();
  const activate = useAction((db, id: string) => setActiveAcademicYear(db, id), {
    success: (year) => `Ano letivo "${year.name}" ativado.`,
  });
  if (!activeYear || collapsed) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="mt-3 flex h-8 w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface px-2.5 text-left text-xs text-fg-muted transition-colors hover:border-border-strong hover:text-fg dark:bg-surface-2"
        aria-label="Trocar ano letivo"
      >
        <span className="truncate">
          <span className="text-fg-subtle">Ano letivo · </span>
          <span className="font-medium text-fg">{activeYear.name}</span>
        </span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-fg-subtle" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Anos letivos</DropdownMenuLabel>
        {years.map((year) => (
          <DropdownMenuItem
            key={year.id}
            onSelect={() => year.id !== activeYear.id && activate.mutate(year.id)}
            icon={year.id === activeYear.id ? <Check className="text-accent-text" /> : <span className="size-4" />}
          >
            {year.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate('/configuracoes#ano-letivo')}>Gerenciar anos letivos…</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Sidebar({ collapsed, onToggleCollapse, onNavigate, className }: SidebarProps) {
  const db = useBackend();
  const navigate = useNavigate();
  const { state, signOut } = useSession();
  const { resolved, toggle } = useTheme();
  const email = state.status === 'ready' ? state.email : null;

  const footerButton = cn(
    'flex h-8 items-center gap-2.5 rounded-lg text-[13px] text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg [&_svg]:size-4 [&_svg]:text-fg-subtle',
    collapsed ? 'w-9 justify-center' : 'px-2.5',
  );

  return (
    <aside
      className={cn('flex h-full flex-col border-r border-border bg-sidebar', collapsed ? 'w-[60px] items-center' : 'w-60', className)}
    >
      <div className={cn('w-full pt-4 pb-2', collapsed ? 'flex flex-col items-center px-2' : 'px-3')}>
        <NavLink to="/" onClick={onNavigate} className="flex h-8 items-center rounded-lg px-1" aria-label="Central de Estudos — início">
          <Logo collapsed={collapsed} />
        </NavLink>
        <YearSwitcher collapsed={collapsed} />
      </div>

      <nav
        aria-label="Menu principal"
        className={cn('flex w-full flex-1 flex-col gap-4 overflow-y-auto py-3', collapsed ? 'items-center px-2' : 'px-3')}
      >
        {NAV_SECTIONS.map((section, index) => (
          <div key={section.label ?? index} className={cn('flex flex-col gap-0.5', collapsed && 'items-center')}>
            {section.label && !collapsed ? (
              <p className="px-2.5 pb-1 text-[11px] font-medium tracking-wide text-fg-subtle">{section.label}</p>
            ) : null}
            {section.label && collapsed ? <div className="mx-auto mb-1 h-px w-5 bg-border" aria-hidden /> : null}
            {section.items.map((item) => (
              <NavEntry key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
            ))}
          </div>
        ))}
      </nav>

      <div className={cn('flex w-full flex-col gap-0.5 border-t border-border py-3', collapsed ? 'items-center px-2' : 'px-3')}>
        <NavEntry item={SETTINGS_ITEM} collapsed={collapsed} onNavigate={onNavigate} />
        <Tooltip content={resolved === 'dark' ? 'Tema claro' : 'Tema escuro'} side="right" disabled={!collapsed}>
          <button type="button" onClick={toggle} className={footerButton} aria-label="Alternar tema claro/escuro">
            {resolved === 'dark' ? <Sun /> : <Moon />}
            {!collapsed ? <span>{resolved === 'dark' ? 'Tema claro' : 'Tema escuro'}</span> : null}
          </button>
        </Tooltip>
        {db.mode === 'supabase' ? (
          <Tooltip content="Sair" side="right" disabled={!collapsed}>
            <button
              type="button"
              onClick={() => {
                // Depois de sair, volta ao início: o próximo login não reabre a última página da conta anterior.
                void signOut().then(() => navigate('/', { replace: true }));
              }}
              className={footerButton}
              aria-label="Sair da conta"
            >
              <LogOut />
              {!collapsed ? <span>Sair</span> : null}
            </button>
          </Tooltip>
        ) : null}
        {onToggleCollapse ? (
          <Tooltip content={collapsed ? 'Expandir menu' : 'Recolher menu'} side="right">
            <button
              type="button"
              onClick={onToggleCollapse}
              className={footerButton}
              aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
              aria-expanded={!collapsed}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              {!collapsed ? <span>Recolher menu</span> : null}
            </button>
          </Tooltip>
        ) : null}

        <Tooltip
          content={
            db.mode === 'local'
              ? 'Modo local: os dados ficam salvos somente neste navegador. Configure o Supabase para sincronizar.'
              : `Conectado à nuvem${email ? ` como ${email}` : ''}.`
          }
          side="right"
        >
          <div
            className={cn(
              'mt-2 flex h-8 items-center gap-2 rounded-lg text-[11px] text-fg-subtle',
              collapsed ? 'w-9 justify-center' : 'border border-border px-2.5',
            )}
          >
            {db.mode === 'local' ? (
              <HardDrive className="size-3.5 text-warning" aria-hidden />
            ) : (
              <Cloud className="size-3.5 text-success" aria-hidden />
            )}
            {!collapsed ? (
              <span className="truncate">{db.mode === 'local' ? 'Modo local · este navegador' : (email ?? 'Nuvem conectada')}</span>
            ) : (
              <span className="sr-only">{db.mode === 'local' ? 'Modo local' : 'Nuvem'}</span>
            )}
          </div>
        </Tooltip>
      </div>
    </aside>
  );
}
