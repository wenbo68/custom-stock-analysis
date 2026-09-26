import type { LucideIcon } from 'lucide-react';

export interface ChoiceOption<Value extends string> {
  value: Value;
  label: string;
  icon: LucideIcon;
}

// One setting the user picks from a short list — the color scheme, the
// UI language, the page (mode) — described once so that every place
// that offers it (the header's dropdown menus on the analysis page, the
// folds in the chat page's sidebar) shows the same word, symbol,
// options and tick.
export interface Choice<Value extends string> {
  /** The symbol before the setting's word. */
  icon: LucideIcon;
  /** The setting's word: "Color", "Language", "Mode". */
  label: string;
  /** What opening it does, for screen readers and the hover tip. */
  triggerLabel: string;
  /** The open list's name, for screen readers. */
  menuLabel: string;
  options: readonly ChoiceOption<Value>[];
  value: Value;
  onSelect: (value: Value) => void;
}
