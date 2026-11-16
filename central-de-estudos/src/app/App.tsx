import { QueryClientProvider } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { RouterProvider } from 'react-router';
import { Toaster } from 'sonner';
import { LogoMark } from '@/components/layout/Logo';
import { ErrorState, Spinner } from '@/components/ui/misc';
import { TooltipProvider } from '@/components/ui/Tooltip';
import { DataContext } from '@/data/DataContext';
import { useWorkspace } from '@/data/hooks';
import { AuthScreen } from '@/features/auth/AuthScreen';
import { OnboardingPage } from '@/features/onboarding/OnboardingPage';
import { queryClient } from './queryClient';
import { router } from './router';
import { SessionProvider, useSession } from './session';
import { ThemeProvider, useTheme } from './theme';

function FullScreenLoader() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <LogoMark size={36} className="animate-pulse" />
      <Spinner />
    </div>
  );
}

function ConfigErrorScreen({ reason }: { reason: string }) {
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="max-w-md rounded-2xl border border-danger/30 bg-surface p-6 shadow-card">
        <ShieldAlert className="mb-3 size-6 text-danger" aria-hidden />
        <h1 className="text-base font-semibold">Configuração bloqueada por segurança</h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">{reason}</p>
        <p className="mt-3 text-xs text-fg-subtle">Veja docs/CONFIGURACAO.md para os passos corretos.</p>
      </div>
    </div>
  );
}

function WorkspaceGate() {
  const { years, isLoading, error, refetch } = useWorkspace();
  if (isLoading) return <FullScreenLoader />;
  if (error) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6">
        <ErrorState error={error} onRetry={() => void refetch()} className="max-w-md" />
      </div>
    );
  }
  if (!years.length) return <OnboardingPage />;
  return <RouterProvider router={router} />;
}

function Root() {
  const { state } = useSession();
  switch (state.status) {
    case 'config_error':
      return <ConfigErrorScreen reason={state.reason} />;
    case 'loading':
      return <FullScreenLoader />;
    case 'signed_out':
      return <AuthScreen />;
    case 'ready':
      return (
        <DataContext.Provider value={state.backend}>
          <WorkspaceGate />
        </DataContext.Provider>
      );
  }
}

function ThemedToaster() {
  const { resolved } = useTheme();
  return (
    <Toaster
      theme={resolved}
      position="bottom-right"
      closeButton
      toastOptions={{
        style: {
          background: 'var(--ce-elevated)',
          border: '1px solid var(--ce-border-strong)',
          color: 'var(--ce-fg)',
          fontSize: '13px',
        },
      }}
    />
  );
}

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <SessionProvider>
            <Root />
          </SessionProvider>
          <ThemedToaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
