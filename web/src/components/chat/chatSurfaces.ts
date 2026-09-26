// The chat page's backdrops, matching the analysis page's stacking
// (owner requests 2026-09-24 and 2026-09-26): level 1 is the darker
// panel surface the analysis page uses for its form and history
// panels; level 2 is the lighter card surface, only ever for a backdrop
// that sits on top of a level-1 one. Everything on the chat page that
// sits directly on the page takes level 1 — the history panel, the
// user's bubble, the pending question, the composer, an opened fold's
// text, a code block inside a reply. The one thing on top of a level-1
// surface is the active history entry, inside the history panel, so it
// alone takes level 2. The bot's steps themselves are bare text (owner
// request 2026-09-24).
export const CHAT_SURFACE_1 = 'bg-gray-900';
export const CHAT_SURFACE_2 = 'bg-gray-800';
/** Level 2, faded: the hover of a history entry that is not the active one. */
export const CHAT_SURFACE_2_HOVER = 'hover:bg-gray-800/60';
