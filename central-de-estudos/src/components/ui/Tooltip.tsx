import * as Radix from '@radix-ui/react-tooltip';
import type { ReactNode } from 'react';

export const TooltipProvider = Radix.Provider;

export function Tooltip({
  content,
  children,
  side = 'top',
  disabled,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  disabled?: boolean;
}) {
  if (disabled) return <>{children}</>;
  return (
    <Radix.Root delayDuration={250}>
      <Radix.Trigger asChild>{children}</Radix.Trigger>
      <Radix.Portal>
        <Radix.Content
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className="z-50 max-w-64 rounded-md border border-border bg-elevated px-2 py-1 text-xs leading-relaxed text-fg shadow-pop data-[state=delayed-open]:animate-fade-in"
        >
          {content}
        </Radix.Content>
      </Radix.Portal>
    </Radix.Root>
  );
}
