import { useState } from 'react';
import { toast } from 'sonner';
import { useSession } from '@/app/session';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { errorMessage } from '@/lib/errors';
import { getSupabase } from '@/lib/supabase';

/** Aberto automaticamente quando o usuário chega por um link de redefinição de senha. */
export function PasswordRecoveryDialog() {
  const { passwordRecovery, clearPasswordRecovery } = useSession();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const save = async () => {
    if (password.length < 8) {
      setError('A senha precisa ter pelo menos 8 caracteres.');
      return;
    }
    setLoading(true);
    const { error: err } = (await getSupabase()?.auth.updateUser({ password })) ?? { error: null };
    setLoading(false);
    if (err) {
      setError(errorMessage(err));
      return;
    }
    toast.success('Senha redefinida.');
    clearPasswordRecovery();
  };

  return (
    <Dialog
      open={passwordRecovery}
      onOpenChange={(open) => !open && clearPasswordRecovery()}
      title="Defina sua nova senha"
      size="sm"
      footer={
        <Button variant="primary" onClick={() => void save()} loading={loading}>
          Salvar nova senha
        </Button>
      }
    >
      <Field label="Nova senha" error={error ?? undefined} hint="Mínimo de 8 caracteres.">
        <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
    </Dialog>
  );
}
