import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { Icon } from "./Icon";

type FieldFrame = {
  label: string;
  /** Texto de ajuda, sempre visível abaixo do campo. */
  help?: ReactNode;
  /** Mensagem de erro: marca o campo como inválido e é lida junto com ele. */
  error?: string | null;
  /** Esconde o rótulo visualmente (continua para leitores de tela). Use só quando o contexto já mostra o rótulo. */
  hideLabel?: boolean;
  className?: string;
};

function describedBy(id: string, help: unknown, error: unknown): string | undefined {
  const ids = [error ? `${id}-erro` : "", help ? `${id}-ajuda` : ""].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function Frame({ id, label, help, error, hideLabel, className, required, children }: FieldFrame & { id: string; required?: boolean; children: ReactNode }) {
  return (
    <div className={["ui-campo", error && "ui-campo--erro", className].filter(Boolean).join(" ")}>
      <label className={hideLabel ? "ui-oculto" : "ui-campo__rotulo"} htmlFor={id}>
        {label}
        {required && <span className="ui-campo__obrigatorio" aria-hidden="true"> *</span>}
      </label>
      {children}
      {error && (
        <p className="ui-campo__erro" id={`${id}-erro`}>
          <Icon name="erro" size={16} /> {error}
        </p>
      )}
      {help && (
        <p className="ui-campo__ajuda" id={`${id}-ajuda`}>
          {help}
        </p>
      )}
    </div>
  );
}

export type TextFieldProps = FieldFrame & Omit<InputHTMLAttributes<HTMLInputElement>, "className">;

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, help, error, hideLabel, className, id, ...input },
  ref,
) {
  const auto = useId();
  const fieldId = id ?? auto;
  return (
    <Frame id={fieldId} label={label} help={help} error={error} hideLabel={hideLabel} className={className} required={input.required}>
      <input
        ref={ref}
        id={fieldId}
        className="ui-entrada"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, help, error)}
        {...input}
      />
    </Frame>
  );
});

export type TextAreaProps = FieldFrame & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "className">;

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
  { label, help, error, hideLabel, className, id, rows = 4, ...input },
  ref,
) {
  const auto = useId();
  const fieldId = id ?? auto;
  return (
    <Frame id={fieldId} label={label} help={help} error={error} hideLabel={hideLabel} className={className} required={input.required}>
      <textarea
        ref={ref}
        id={fieldId}
        rows={rows}
        className="ui-entrada ui-entrada--area"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, help, error)}
        {...input}
      />
    </Frame>
  );
});

export type SelectProps = FieldFrame &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, "className"> & {
    options: ReadonlyArray<{ value: string; label: string; disabled?: boolean }>;
  };

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, help, error, hideLabel, className, id, options, ...select },
  ref,
) {
  const auto = useId();
  const fieldId = id ?? auto;
  return (
    <Frame id={fieldId} label={label} help={help} error={error} hideLabel={hideLabel} className={className} required={select.required}>
      <div className="ui-selecao">
        <select
          ref={ref}
          id={fieldId}
          className="ui-entrada"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(fieldId, help, error)}
          {...select}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon name="chevron-baixo" size={16} className="ui-selecao__seta" />
      </div>
    </Frame>
  );
});

export type SearchFieldProps = Omit<TextFieldProps, "type">;

export const SearchField = forwardRef<HTMLInputElement, SearchFieldProps>(function SearchField({ className, ...props }, ref) {
  return (
    <div className={["ui-busca", className].filter(Boolean).join(" ")}>
      <Icon name="busca" size={18} className="ui-busca__icone" />
      <TextField ref={ref} type="search" autoComplete="off" {...props} />
    </div>
  );
});

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "className"> & {
  label: ReactNode;
  help?: ReactNode;
  className?: string;
};

export function Checkbox({ label, help, className, id, ...input }: CheckboxProps) {
  const auto = useId();
  const fieldId = id ?? auto;
  return (
    <div className={["ui-opcao", className].filter(Boolean).join(" ")}>
      <input id={fieldId} type="checkbox" className="ui-opcao__caixa" aria-describedby={help ? `${fieldId}-ajuda` : undefined} {...input} />
      <label htmlFor={fieldId} className="ui-opcao__rotulo">
        {label}
      </label>
      {help && (
        <p className="ui-campo__ajuda" id={`${fieldId}-ajuda`}>
          {help}
        </p>
      )}
    </div>
  );
}

export type SwitchProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  help?: ReactNode;
  disabled?: boolean;
  className?: string;
};

/** Alternador (liga/desliga) com papel "switch": o estado é anunciado como "ligado"/"desligado". */
export function Switch({ label, checked, onChange, help, disabled, className }: SwitchProps) {
  const id = useId();
  return (
    <div className={["ui-alternador", className].filter(Boolean).join(" ")}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={help ? `${id}-ajuda` : undefined}
        className="ui-alternador__botao"
        disabled={disabled}
        onClick={() => onChange(!checked)}
      >
        <span className="ui-alternador__trilho" aria-hidden="true">
          <span className="ui-alternador__pino" />
        </span>
        <span className="ui-alternador__rotulo">{label}</span>
      </button>
      {help && (
        <p className="ui-campo__ajuda" id={`${id}-ajuda`}>
          {help}
        </p>
      )}
    </div>
  );
}
