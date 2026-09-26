import { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import { cn } from '../../utils/cn';
import type { Choice } from './choice';

type HeaderMenuProps<Value extends string> = Choice<Value> & { testId?: string };

// The header's one kind of button (owner request 2026-09-26): a symbol
// and a word that open a list of choices, the chosen one ticked. The
// theme menu came first; the mode and language menus took its shape so
// the three read as a set. The list closes on a pick, a click outside
// or Escape.
export function HeaderMenu<Value extends string>({
  icon: Icon,
  label,
  triggerLabel,
  menuLabel,
  options,
  value,
  onSelect,
  testId,
}: HeaderMenuProps<Value>) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <div className="relative" ref={containerRef} data-testid={testId}>
      <button
        type="button"
        onClick={() => setOpen((shown) => !shown)}
        data-state={open ? 'open' : 'closed'}
        className="inline-flex h-10 items-center gap-2 rounded-xl border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground data-[state=open]:border-border data-[state=open]:bg-hover data-[state=open]:text-foreground"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={triggerLabel}
        title={triggerLabel}
      >
        <Icon className="h-4 w-4 shrink-0" />
        <span className="hidden sm:inline">{label}</span>
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={menuLabel}
          className="absolute right-0 z-[100] mt-2 min-w-[8rem] overflow-hidden rounded-2xl border border-border/70 bg-popover p-1.5 shadow-[0_24px_48px_rgba(3,8,20,0.32)] backdrop-blur-xl"
        >
          {options.map(({ value: optionValue, label: optionLabel, icon: OptionIcon }) => {
            const isActive = value === optionValue;
            return (
              <button
                key={optionValue}
                type="button"
                role="menuitemradio"
                aria-checked={isActive}
                onClick={() => {
                  onSelect(optionValue);
                  setOpen(false);
                }}
                className={cn(
                  'flex w-full items-center justify-between gap-4 rounded-xl px-3 py-2 text-sm transition-colors',
                  isActive ? 'bg-cyan/10 text-foreground' : 'text-secondary-text hover:bg-hover hover:text-foreground',
                )}
              >
                <span className="flex items-center gap-2 whitespace-nowrap">
                  <OptionIcon className="h-4 w-4" />
                  {optionLabel}
                </span>
                {isActive ? <Check className="h-4 w-4 text-cyan" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
