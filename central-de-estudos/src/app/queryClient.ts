import { QueryClient } from '@tanstack/react-query';
import { toAppError } from '@/lib/errors';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Repete automaticamente apenas falhas transitórias (conexão/servidor).
      retry: (failureCount, error) => failureCount < 2 && toAppError(error).retryable,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      refetchOnWindowFocus: true,
    },
    mutations: { retry: false },
  },
});
