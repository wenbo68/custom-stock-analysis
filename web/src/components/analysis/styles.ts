// showplayer badge recipe: soft tinted fill + matching inset ring, no border.
export const TAG_BASE =
  'inline-flex items-center rounded px-[9px] py-0.5 text-xs font-semibold ring-1 ring-inset';

// Outlooks render as plain colored text, not pills: bullish green,
// neutral amber, bearish red. The vote tree's per-vote item outlooks
// share the same palette.
export const OUTLOOK_TEXT: Record<string, string> = {
  bullish: 'text-positive',
  neutral: 'text-caution',
  bearish: 'text-negative',
  unknown: 'text-ink-3',
};

// The showplayer pill palette (tagClassMap order, stone skipped by owner
// decision): colors are handed out to a section's fields in this fixed
// order (1, 2, 3, …), and a range's Min and Max share one color. Meaning
// does not pick the color — position does. These are the one place that
// names raw palette shades: the tint and ring read fine on both themes,
// the text takes a deep shade on the light theme and a pale one on dark.
export const ALT_COLOR = {
  1: 'bg-red-500/20 text-red-700 ring-red-500/30 dark:text-red-300',
  2: 'bg-orange-500/20 text-orange-700 ring-orange-500/30 dark:text-orange-300',
  3: 'bg-amber-500/20 text-amber-700 ring-amber-500/30 dark:text-amber-300',
  4: 'bg-lime-500/20 text-lime-700 ring-lime-500/30 dark:text-lime-300',
  5: 'bg-emerald-500/20 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300',
  6: 'bg-sky-500/20 text-sky-700 ring-sky-500/30 dark:text-sky-300',
  7: 'bg-blue-500/20 text-blue-700 ring-blue-500/30 dark:text-blue-300',
  8: 'bg-indigo-500/20 text-indigo-700 ring-indigo-500/30 dark:text-indigo-300',
  9: 'bg-violet-500/20 text-violet-700 ring-violet-500/30 dark:text-violet-300',
  gray: 'bg-gray-500/20 text-gray-700 ring-gray-500/30 dark:text-gray-300',
} as const;

// The text colors alone out of a pill tone (the light one and its dark:
// twin), for a field title that turns the pill's color while a value is
// committed (owner request 2026-09-18): a colored title means "this
// filter is set", a gray one means it is not.
export const toneText = (tone: string): string =>
  tone
    .split(' ')
    .filter((token) => token.startsWith('text-') || token.startsWith('dark:text-'))
    .join(' ');

// One line of a formula block (words / plugged-in / result): same element,
// font and spacing on every line, never wrapping. Colors match the shared
// modal contract in Ui (body ink-2, emphasis ink-1 semibold).
export const FORMULA_LINE = 'whitespace-nowrap text-ink-2';
export const FORMULA_RESULT = 'whitespace-nowrap font-semibold text-ink-1';

// Inline text link, showplayer blue. The color utilities carry ! because
// index.css has an unlayered `a { color: inherit }` rule that outranks
// Tailwind's layered utilities on <a> tags — without !, every anchor link
// on this page silently renders in the surrounding text color.
export const ALT_LINK = 'text-link! hover:text-link-hover! hover:underline';
