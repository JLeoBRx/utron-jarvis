import { Compass, TriangleAlert } from 'lucide-react';
import { isRouteErrorResponse, useRouteError } from 'react-router';
import { ButtonLink } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/misc';

export function NotFoundPage({ message }: { message?: string }) {
  return (
    <EmptyState
      icon={<Compass />}
      title="Página não encontrada"
      description={message ?? 'O endereço acessado não existe ou foi removido.'}
      actions={
        <ButtonLink to="/" variant="secondary">
          Voltar ao Dashboard
        </ButtonLink>
      }
    />
  );
}

export function RouteErrorPage() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} — ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'Erro desconhecido.';
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <EmptyState
        icon={<TriangleAlert />}
        title="Algo deu errado nesta página"
        description={`${message} Seus dados não foram afetados.`}
        actions={
          <a href="/" className="text-sm font-medium text-accent-text hover:underline">
            Recarregar a Central de Estudos
          </a>
        }
      />
    </div>
  );
}
