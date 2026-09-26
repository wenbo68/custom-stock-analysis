// The chat page's backdrops, matching the analysis page's stacking
// (owner requests 2026-09-24 and 2026-09-26): level 1 is the panel
// surface the analysis page uses for its form and history panels;
// level 2 is the card surface, only ever for a backdrop that sits on
// top of a level-1 one. (Both take their light and dark colors from
// the surface roles in index.css.) Everything on the chat page that
// sits directly on the page takes level 1 — the history panel, the
// user's bubble, the pending question, the composer, an opened fold's
// text, a code block inside a reply. The one thing on top of a level-1
// surface is the active history entry, inside the history panel, so it
// alone takes level 2. The bot's steps themselves are bare text (owner
// request 2026-09-24).
export const CHAT_SURFACE_1 = 'bg-surface-1';
export const CHAT_SURFACE_2 = 'bg-surface-2';
/** Level 2, faded: the hover of a history entry that is not the active one. */
export const CHAT_SURFACE_2_HOVER = 'hover:bg-surface-2/60';
