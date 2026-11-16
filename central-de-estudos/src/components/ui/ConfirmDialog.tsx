import { useEffect, useState, type ReactNode } from 'react';
import { Button } from './Button';
import { Dialog } from './Dialog';
import { Input } from './Input';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  tone?: 'danger' | 'primary';
  /** Exige digitar este texto para confirmar (ações destrutivas grandes). */
  requireText?: string;
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  tone = 'danger',
  requireText,
  loading,
  onConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('');
  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);
  const blocked = Boolean(requireText) && typed.trim() !== requireText;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancelar
          </Button>
          <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={() => void onConfirm()} disabled={blocked} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
      {requireText ? (
        <div className="mt-3 space-y-1.5">
          <label className="text-xs text-fg-muted" htmlFor="confirm-text">
            Para confirmar, digite <strong className="font-semibold text-fg">{requireText}</strong>
          </label>
          <Input id="confirm-text" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
      ) : null}
    </Dialog>
  );
}
