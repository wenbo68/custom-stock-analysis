import type { UiTextKey } from '../../i18n/uiText';

// The chat's slash commands (owner request 2026-10-13, after Claude
// Code's): a line in the message box that starts with "/" is a command
// for the page or the server, never a message for the bot. Three to
// begin with — /help lists them, /context sizes the next request
// against the model's max, /compact summarizes the conversation to
// free up context. The table is the one place a command is declared:
// the menu over the box, /help and the dispatcher all read it.
export type ChatCommandName = 'help' | 'context' | 'compact';

export interface ChatCommand {
  name: ChatCommandName;
  /** One line on what it does, for the menu and /help. */
  descriptionKey: UiTextKey;
}

export const CHAT_COMMANDS: readonly ChatCommand[] = [
  { name: 'help', descriptionKey: 'chat.command.help.help' },
  { name: 'context', descriptionKey: 'chat.command.help.context' },
  { name: 'compact', descriptionKey: 'chat.command.help.compact' },
];

/** What a typed line is: a known command, an unknown one, or a message. */
export type ParsedInput =
  | { kind: 'message'; text: string }
  | { kind: 'command'; command: ChatCommand }
  | { kind: 'unknown'; name: string };

// A line is a command when its first character is "/" and the word
// after it has no spaces or punctuation — "/context" or "/COMPACT ",
// not "/usr/bin" or "/ a path". The word is matched without regard to
// case; anything after it is ignored for now (no command takes arguments).
const COMMAND_LINE = /^\/([a-z]+)(?:\s|$)/i;

export const parseInput = (text: string): ParsedInput => {
  const trimmed = text.trim();
  const match = COMMAND_LINE.exec(trimmed);
  if (!match) {
    return { kind: 'message', text: trimmed };
  }
  const name = match[1].toLowerCase();
  const command = CHAT_COMMANDS.find((candidate) => candidate.name === name);
  return command ? { kind: 'command', command } : { kind: 'unknown', name: `/${name}` };
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
