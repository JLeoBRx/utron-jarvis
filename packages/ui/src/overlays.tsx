import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button, IconButton, type ButtonVariant } from "./Button";
import { focusableIn, useFocusTrap } from "./focus";
import { Icon, type IconName } from "./Icon";

// ------------------------------------------------------------------ modal
export type ModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Ações no rodapé (botões). */
  actions?: ReactNode;
  /** Descrição curta lida ao abrir. */
  description?: ReactNode;
  size?: "normal" | "largo";
};

/** Janela modal: foco preso, Esc fecha sem confirmar, o foco volta para quem abriu. */
export function Modal({ open, title, onClose, children, actions, description, size = "normal" }: ModalProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useFocusTrap(open, panel, onClose);
  if (!open) return null;
  return createPortal(
    <div className="ui-modal">
      <div className="ui-modal__fundo" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={`ui-modal__painel ui-modal__painel--${size}`}
        tabIndex={-1}
      >
        <header className="ui-modal__cabecalho">
          <h2 id={titleId} className="ui-modal__titulo">
            {title}
          </h2>
          <IconButton icon="fechar" label="Fechar" onClick={onClose} size="pequeno" />
        </header>
        {description && (
          <p id={descriptionId} className="ui-modal__descricao">
            {description}
          </p>
        )}
        <div className="ui-modal__corpo">{children}</div>
        {actions && <footer className="ui-modal__rodape">{actions}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: ButtonVariant;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Confirmação simples. Em ações destrutivas o foco inicial fica em "Cancelar". */
export function ConfirmDialog({ open, title, message, confirmLabel, cancelLabel = "Cancelar", variant = "principal", busy, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      actions={
        <>
          <Button onClick={onCancel} disabled={busy} data-autofocus={variant === "perigo" ? "" : undefined}>
            {cancelLabel}
          </Button>
          <Button variant={variant} onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="ui-modal__mensagem">{message}</div>
    </Modal>
  );
}

// ------------------------------------------------------------------ menu
export type MenuItem = {
  id: string;
  label: string;
  icon?: IconName;
  danger?: boolean;
  disabled?: boolean;
  onSelect: () => void;
};

export type MenuProps = {
  /** Nome do botão que abre o menu (lido por leitores de tela). */
  label: string;
  items: MenuItem[];
  icon?: IconName;
  /** Mostra o rótulo ao lado do ícone. */
  showLabel?: boolean;
  align?: "inicio" | "fim";
};

/** Menu de ações: setas, Home e End navegam; Esc fecha e devolve o foco ao botão. */
export function Menu({ label, items, icon = "mais-opcoes", showLabel = false, align = "fim" }: MenuProps) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const first = list.current ? focusableIn(list.current)[0] : undefined;
    first?.focus();
    const outside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!list.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (!list.current) return;
    const options = focusableIn(list.current);
    const index = options.indexOf(document.activeElement as HTMLElement);
    const move = (to: number) => options[(to + options.length) % options.length]?.focus();
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(options.length - 1);
    else if (event.key === "Escape") close(true);
    else if (event.key === "Tab") close(false);
    else return;
    if (event.key !== "Tab") event.preventDefault();
  };

  return (
    <div className="ui-menu">
      <Button
        ref={button}
        variant="discreto"
        icon={icon}
        className={showLabel ? undefined : "ui-botao--icone"}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={showLabel ? undefined : label}
        title={showLabel ? undefined : label}
        onClick={() => setOpen((value) => !value)}
      >
        {showLabel ? label : undefined}
      </Button>
      {open && (
        <ul ref={list} id={menuId} role="menu" aria-label={label} className={`ui-menu__lista ui-menu__lista--${align}`} onKeyDown={onKeyDown}>
          {items.map((item) => (
            <li key={item.id} role="none">
              <button
                type="button"
                role="menuitem"
                className={["ui-menu__item", item.danger && "ui-menu__item--perigo"].filter(Boolean).join(" ")}
                disabled={item.disabled}
                onClick={() => {
                  close(true);
                  item.onSelect();
                }}
              >
                {item.icon && <Icon name={item.icon} size={18} />}
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
