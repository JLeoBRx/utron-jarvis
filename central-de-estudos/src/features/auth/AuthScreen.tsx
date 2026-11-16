import { zodResolver } from '@hookform/resolvers/zod';
import { MailCheck } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { LogoMark } from '@/components/layout/Logo';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { Segmented } from '@/components/ui/misc';
import { errorMessage } from '@/lib/errors';
import { getSupabase } from '@/lib/supabase';

type Mode = 'entrar' | 'criar' | 'recuperar';

const schema = z.object({
  email: z.string().trim().email('Informe um e-mail válido.'),
  password: z.string().optional(),
});
type Values = z.infer<typeof schema>;

function translateAuthError(error: unknown): string {
  const message = errorMessage(error).toLowerCase();
  if (message.includes('invalid login credentials')) return 'E-mail ou senha incorretos.';
  if (message.includes('email not confirmed')) return 'Confirme seu e-mail antes de entrar (verifique sua caixa de entrada).';
  if (message.includes('already registered') || message.includes('already been registered')) return 'Este e-mail já possui conta. Use "Entrar".';
  if (message.includes('rate limit')) return 'Muitas tentativas. Aguarde alguns minutos e tente novamente.';
  if (message.includes('password')) return 'A senha precisa ter pelo menos 8 caracteres.';
  return errorMessage(error);
}

export function AuthScreen() {
  const [mode, setMode] = useState<Mode>('entrar');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { register, handleSubmit, formState, setError: setFieldError } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ email, password }) => {
    const supabase = getSupabase();
    if (!supabase) return;
    setError(null);
    setNotice(null);
    if (mode !== 'recuperar' && (!password || password.length < 8)) {
      setFieldError('password', { message: 'A senha precisa ter pelo menos 8 caracteres.' });
      return;
    }
    setLoading(true);
    try {
      if (mode === 'entrar') {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password: password! });
        if (err) throw err;
      } else if (mode === 'criar') {
        const { data, error: err } = await supabase.auth.signUp({
          email,
          password: password!,
          options: { emailRedirectTo: window.location.origin },
        });
        if (err) throw err;
        if (!data.session) setNotice('Conta criada! Enviamos um link de confirmação para o seu e-mail.');
      } else {
        const { error: err } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
        if (err) throw err;
        setNotice('Se houver uma conta com este e-mail, você receberá um link para redefinir a senha.');
      }
    } catch (err) {
      setError(translateAuthError(err));
    } finally {
      setLoading(false);
    }
  });

  const titles: Record<Mode, string> = {
    entrar: 'Entrar na Central de Estudos',
    criar: 'Criar sua conta',
    recuperar: 'Recuperar acesso',
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm animate-rise">
        <div className="mb-7 flex flex-col items-center text-center">
          <LogoMark size={40} />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">{titles[mode]}</h1>
          <p className="mt-1.5 text-sm text-fg-muted">Seus estudos, organizados e sincronizados.</p>
        </div>
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-card">
          {mode !== 'recuperar' ? (
            <Segmented
              label="Acesso"
              value={mode}
              onChange={(m) => {
                setMode(m);
                setError(null);
                setNotice(null);
              }}
              className="mb-5 flex w-full [&>button]:flex-1 [&>button]:justify-center"
              options={[
                { value: 'entrar', label: 'Entrar' },
                { value: 'criar', label: 'Criar conta' },
              ]}
            />
          ) : null}
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Field label="E-mail" error={formState.errors.email?.message}>
              <Input type="email" autoComplete="email" autoFocus placeholder="voce@exemplo.com" {...register('email')} />
            </Field>
            {mode !== 'recuperar' ? (
              <Field label="Senha" error={formState.errors.password?.message} hint={mode === 'criar' ? 'Mínimo de 8 caracteres.' : undefined}>
                <Input
                  type="password"
                  autoComplete={mode === 'criar' ? 'new-password' : 'current-password'}
                  {...register('password')}
                />
              </Field>
            ) : null}
            {error ? (
              <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">
                {error}
              </p>
            ) : null}
            {notice ? (
              <p role="status" className="flex gap-2 rounded-lg bg-success-soft px-3 py-2 text-xs text-success">
                <MailCheck className="size-4 shrink-0" aria-hidden />
                {notice}
              </p>
            ) : null}
            <Button type="submit" variant="primary" className="w-full" loading={loading}>
              {mode === 'entrar' ? 'Entrar' : mode === 'criar' ? 'Criar conta' : 'Enviar link de recuperação'}
            </Button>
          </form>
          <div className="mt-4 text-center text-xs">
            {mode === 'recuperar' ? (
              <button type="button" className="text-fg-muted hover:text-fg" onClick={() => setMode('entrar')}>
                Voltar para entrar
              </button>
            ) : (
              <button type="button" className="text-fg-muted hover:text-fg" onClick={() => setMode('recuperar')}>
                Esqueci minha senha
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
