import * as RadixDialog from '@radix-ui/react-dialog';
import { Menu, Moon, Sun, WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router';
import { useTheme } from '@/app/theme';
import { Sidebar } from './Sidebar';
import { LogoMark } from './Logo';
import { PasswordRecoveryDialog } from '@/features/auth/PasswordRecoveryDialog';

const COLLAPSE_KEY = 'ce:sidebar-collapsed';

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine));
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const online = useOnline();
  const location = useLocation();
  const { resolved, toggle } = useTheme();

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignora */
    }
  }, [collapsed]);

  // Fecha o menu móvel e volta ao topo ao trocar de página.
  useEffect(() => {
    setMobileOpen(false);
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded-md bg-accent px-3 py-2 text-accent-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Pular para o conteúdo
      </a>

      <div className="sticky top-0 hidden h-dvh shrink-0 lg:block">
        <Sidebar collapsed={collapsed} onToggleCollapse={() => setCollapsed((c) => !c)} />
      </div>

      <RadixDialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <RadixDialog.Portal>
          <RadixDialog.Overlay className="fixed inset-0 z-40 bg-overlay data-[state=open]:animate-fade-in lg:hidden" />
          <RadixDialog.Content className="fixed inset-y-0 left-0 z-50 shadow-pop outline-none data-[state=open]:animate-slide-in-left lg:hidden">
            <RadixDialog.Title className="sr-only">Menu</RadixDialog.Title>
            <RadixDialog.Description className="sr-only">Navegação principal da Central de Estudos</RadixDialog.Description>
            <Sidebar onNavigate={() => setMobileOpen(false)} className="w-72 max-w-[85vw]" />
          </RadixDialog.Content>
        </RadixDialog.Portal>
      </RadixDialog.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur-md lg:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="-ml-1.5 rounded-lg p-1.5 text-fg-muted hover:bg-surface-2 hover:text-fg"
            aria-label="Abrir menu"
          >
            <Menu className="size-5" />
          </button>
          <Link to="/" className="flex items-center gap-2" aria-label="Central de Estudos — início">
            <LogoMark size={24} />
            <span className="text-[13px] font-semibold tracking-tight">Central de Estudos</span>
          </Link>
          <button
            type="button"
            onClick={toggle}
            className="-mr-1.5 rounded-lg p-1.5 text-fg-muted hover:bg-surface-2 hover:text-fg"
            aria-label="Alternar tema claro/escuro"
          >
            {resolved === 'dark' ? <Sun className="size-5" /> : <Moon className="size-5" />}
          </button>
        </header>

        {!online ? (
          <div role="status" className="flex items-center justify-center gap-2 bg-warning-soft px-4 py-2 text-xs text-warning">
            <WifiOff className="size-3.5" aria-hidden />
            Você está sem conexão. Alterações podem falhar até a internet voltar.
          </div>
        ) : null}

        <main id="conteudo" className="mx-auto w-full max-w-[1180px] flex-1 px-4 pt-5 pb-16 sm:px-6 lg:px-10 lg:pt-9">
          <Outlet />
        </main>
      </div>
      <PasswordRecoveryDialog />
    </div>
  );
}
