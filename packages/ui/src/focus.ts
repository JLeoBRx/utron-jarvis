import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function focusableIn(node: HTMLElement): HTMLElement[] {
  return Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
}

/**
 * Prende o foco do teclado dentro de `ref` enquanto `active`: Tab e Shift+Tab circulam só ali, Esc chama `onEscape`
 * e, ao sair, o foco volta para onde estava antes.
 */
export function useFocusTrap(
  active: boolean,
  ref: RefObject<HTMLElement | null>,
  onEscape?: () => void,
  initialFocus?: RefObject<HTMLElement | null>,
): void {
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    const node = ref.current;
    if (!active || !node) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    (initialFocus?.current ?? node.querySelector<HTMLElement>("[data-autofocus]") ?? focusableIn(node)[0] ?? node).focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        escape.current?.();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusableIn(node);
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) {
        event.preventDefault();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    node.addEventListener("keydown", onKey);
    return () => {
      node.removeEventListener("keydown", onKey);
      if (previous && document.contains(previous)) previous.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reage só à abertura e ao fechamento
  }, [active]);
}
