import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type ButtonVariant = "principal" | "secundario" | "discreto" | "perigo";

export type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  variant?: ButtonVariant;
  size?: "normal" | "pequeno";
  icon?: IconName;
  /** Mostra o indicador de progresso, desabilita o botão e anuncia "carregando". */
  loading?: boolean;
  children?: ReactNode;
};

/** Botão com os estados do design system: normal, cursor, foco, pressionado, desabilitado e carregando. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secundario", size = "normal", icon, loading = false, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={["ui-botao", `ui-botao--${variant}`, size === "pequeno" && "ui-botao--pequeno", loading && "ui-botao--carregando", className]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="ui-giro" aria-hidden="true" /> : icon ? <Icon name={icon} size={size === "pequeno" ? 16 : 18} /> : null}
      {children !== undefined && <span className="ui-botao__texto">{children}</span>}
      {loading && <span className="ui-oculto">carregando</span>}
    </button>
  );
});

export type IconButtonProps = Omit<ButtonProps, "children" | "icon"> & {
  icon: IconName;
  /** Obrigatório: é o nome do botão para leitores de tela e a dica ao passar o cursor. */
  label: string;
};

/** Botão só com ícone. O nome acessível é obrigatório. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, label, variant = "discreto", className, ...rest },
  ref,
) {
  return (
    <Button ref={ref} variant={variant} className={["ui-botao--icone", className].filter(Boolean).join(" ")} aria-label={label} title={label} {...rest}>
      <Icon name={icon} size={rest.size === "pequeno" ? 16 : 20} />
    </Button>
  );
});
