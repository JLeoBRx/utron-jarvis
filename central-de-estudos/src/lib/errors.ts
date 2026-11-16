/**
 * Erro padronizado da aplicação. A mensagem é sempre em português e pode ser
 * exibida diretamente ao usuário.
 */
export type AppErrorCode =
  | 'offline'
  | 'not_found'
  | 'conflict'
  | 'integrity'
  | 'validation'
  | 'permission'
  | 'auth'
  | 'storage'
  | 'config'
  | 'unknown';

export class AppError extends Error {
  readonly code: AppErrorCode;
  override readonly cause: unknown;

  constructor(code: AppErrorCode, message: string, cause?: unknown) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.cause = cause;
  }

  /** Falhas transitórias que valem uma nova tentativa automática. */
  get retryable(): boolean {
    return this.code === 'offline' || this.code === 'unknown';
  }
}

export function isAppError(error: unknown): error is AppError {
  return error instanceof AppError;
}

export function toAppError(error: unknown): AppError {
  if (error instanceof AppError) return error;
  if (isNetworkError(error)) {
    return new AppError('offline', 'Sem conexão com o servidor. Verifique sua internet e tente novamente.', error);
  }
  const message = error instanceof Error ? error.message : String(error);
  return new AppError('unknown', `Ocorreu um erro inesperado: ${message}`, error);
}

export function isNetworkError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message.toLowerCase();
  return (
    (error.name === 'TypeError' && (msg.includes('fetch') || msg.includes('network'))) ||
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('load failed')
  );
}

export function errorMessage(error: unknown): string {
  return toAppError(error).message;
}
