import * as Radix from '@radix-ui/react-dropdown-menu';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export const DropdownMenu = Radix.Root;
export const DropdownMenuTrigger = Radix.Trigger;

export function DropdownMenuContent({
  children,
  align = 'end',
  className,
}: {
  children: ReactNode;
  align?: 'start' | 'center' | 'end';
  className?: string;
}) {
  return (
    <Radix.Portal>
      <Radix.Content
        align={align}
        sideOffset={6}
        collisionPadding={8}
        className={cn(
          'z-50 min-w-48 rounded-xl border border-border bg-elevated p-1 shadow-pop data-[state=open]:animate-fade-in',
          className,
        )}
      >
        {children}
      </Radix.Content>
    </Radix.Portal>
  );
}

export function DropdownMenuItem({
  children,
  onSelect,
  icon,
  danger,
  disabled,
}: {
  children: ReactNode;
  onSelect?: () => void;
  icon?: ReactNode;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <Radix.Item
      disabled={disabled}
      onSelect={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none [&_svg]:size-4',
        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
        danger
          ? 'text-danger data-[highlighted]:bg-danger-soft'
          : 'text-fg-muted data-[highlighted]:bg-surface-2 data-[highlighted]:text-fg',
      )}
    >
      {icon}
      {children}
    </Radix.Item>
  );
}

export function DropdownMenuLabel({ children }: { children: ReactNode }) {
  return <Radix.Label className="px-2 pt-1.5 pb-1 text-[11px] font-medium tracking-wide text-fg-subtle uppercase">{children}</Radix.Label>;
}

export function DropdownMenuSeparator() {
  return <Radix.Separator className="my-1 h-px bg-border" />;
}

export const DropdownMenuRadioGroup = Radix.RadioGroup;

export function DropdownMenuRadioItem({ value, children }: { value: string; children: ReactNode }) {
  return (
    <Radix.RadioItem
      value={value}
      className="relative flex cursor-pointer items-center gap-2 rounded-md py-1.5 pr-2 pl-7 text-sm text-fg-muted outline-none select-none data-[highlighted]:bg-surface-2 data-[highlighted]:text-fg data-[state=checked]:text-fg"
    >
      <Radix.ItemIndicator className="absolute left-2 flex size-3.5 items-center justify-center">
        <span className="size-1.5 rounded-full bg-accent" />
      </Radix.ItemIndicator>
      {children}
    </Radix.RadioItem>
  );
}
