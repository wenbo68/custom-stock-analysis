import type { UiTextKey } from '../../i18n/uiText';

// The chat's slash commands (owner request 2026-10-13, after Claude
// Code's): a line in the message box that starts with "/" is a command
// for the page or the server, never a message for the bot. /help lists
// them, /context sizes the next request against the model's max,
// /compact summarizes the conversation to free up context, and /btw
// asks the LLM a side question it will not remember afterwards (owner
// request 2026-10-16). The table is the one place a command is
// declared: the menu over the box, /help and the dispatcher all read it.
//
// Whether a command may run while the bot is still replying is the
// command's own call (owner decision 2026-10-15; Claude Code marks it
// the same way, one flag per command): /help reads nothing but the
// table, so it answers at once; /context would measure a conversation
// that is still changing, and /compact and /btw need the turn's lock,
// so they are refused until the reply is back — an error line over the
// box says so, and nothing is queued.
//
// A command may take the rest of the line (`argumentKey` names what,
// for the menu and /help: "/btw <question>"); the others ignore what
// follows their word.
export type ChatCommandName = 'help' | 'context' | 'compact' | 'btw';

export interface ChatCommand {
  name: ChatCommandName;
  /** One line on what it does, for the menu and /help. */
  descriptionKey: UiTextKey;
  /** Typed while a reply is awaited, the command is refused, not run. */
  blockedWhileWaiting: boolean;
  /** What the command takes after its word, named for the menu and
   *  /help; the line is refused without it. Absent: nothing is taken. */
  argumentKey?: UiTextKey;
}

export const CHAT_COMMANDS: readonly ChatCommand[] = [
  { name: 'help', descriptionKey: 'chat.command.help.help', blockedWhileWaiting: false },
  { name: 'context', descriptionKey: 'chat.command.help.context', blockedWhileWaiting: true },
  { name: 'compact', descriptionKey: 'chat.command.help.compact', blockedWhileWaiting: true },
  { name: 'btw', descriptionKey: 'chat.command.help.btw', blockedWhileWaiting: true, argumentKey: 'chat.command.btw.argument' },
];

/** What a typed line is: a known command (with whatever followed its
 *  word, trimmed — '' when nothing did), an unknown one, or a message. */
export type ParsedInput =
  | { kind: 'message'; text: string }
  | { kind: 'command'; command: ChatCommand; argument: string }
  | { kind: 'unknown'; name: string };

// A line is a command when its first character is "/" and the word
// after it has no spaces or punctuation — "/context" or "/COMPACT ",
// not "/usr/bin" or "/ a path". The word is matched without regard to
// case; what follows it, after whitespace, is the argument.
const COMMAND_LINE = /^\/([a-z]+)(?:\s+([\s\S]*))?$/i;

export const parseInput = (text: string): ParsedInput => {
  const trimmed = text.trim();
  const match = COMMAND_LINE.exec(trimmed);
  if (!match) {
    return { kind: 'message', text: trimmed };
  }
  const name = match[1].toLowerCase();
  const command = CHAT_COMMANDS.find((candidate) => candidate.name === name);
  return command ? { kind: 'command', command, argument: (match[2] ?? '').trim() } : { kind: 'unknown', name: `/${name}` };
};

// The commands the menu over the box offers while a command is being
// typed: every one whose name starts with what follows the "/", or
// none once a space ends the word or the line is no command at all.
export const matchingCommands = (draft: string): readonly ChatCommand[] => {
  const match = /^\/([a-z]*)$/i.exec(draft);
  if (!match) {
    return [];
  }
  const prefix = match[1].toLowerCase();
  return CHAT_COMMANDS.filter((command) => command.name.startsWith(prefix));
};
