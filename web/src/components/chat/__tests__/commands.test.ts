import { describe, expect, it } from 'vitest';
import { CHAT_COMMANDS, matchingCommands, parseInput } from '../commands';

describe('chat commands', () => {
  it('tells a command from a message', () => {
    expect(parseInput('  hello /context  ')).toEqual({ kind: 'message', text: 'hello /context' });
    expect(parseInput('/context')).toEqual({ kind: 'command', command: CHAT_COMMANDS[1], argument: '' });
    // Case does not matter; what follows a word is handed over, trimmed
    // (the page ignores it for a command that takes nothing).
    expect(parseInput(' /COMPACT now ')).toEqual({ kind: 'command', command: CHAT_COMMANDS[2], argument: 'now' });
    expect(parseInput('/help\nplease')).toEqual({ kind: 'command', command: CHAT_COMMANDS[0], argument: 'please' });
  });

  it('hands /btw the rest of the line as its question', () => {
    const btw = CHAT_COMMANDS[3];
    expect(btw.name).toBe('btw');
    expect(btw.argumentKey).toBeDefined();
    expect(parseInput('/btw what is tier 2?')).toEqual({ kind: 'command', command: btw, argument: 'what is tier 2?' });
    expect(parseInput('/BTW  two\nlines ')).toEqual({ kind: 'command', command: btw, argument: 'two\nlines' });
    // Without a question the line is still the command; the page refuses it.
    expect(parseInput('/btw')).toEqual({ kind: 'command', command: btw, argument: '' });
    expect(parseInput('/btw   ')).toEqual({ kind: 'command', command: btw, argument: '' });
  });

  it('names an unknown command and leaves paths alone', () => {
    expect(parseInput('/nope')).toEqual({ kind: 'unknown', name: '/nope' });
    expect(parseInput('/Model gpt')).toEqual({ kind: 'unknown', name: '/model' });
    // "/usr/bin" is no command word: a message, for the bot to puzzle over.
    expect(parseInput('/usr/bin')).toEqual({ kind: 'message', text: '/usr/bin' });
    expect(parseInput('/btw/now')).toEqual({ kind: 'message', text: '/btw/now' });
    expect(parseInput('/ context')).toEqual({ kind: 'message', text: '/ context' });
    expect(parseInput('/')).toEqual({ kind: 'message', text: '/' });
  });

  it('offers the commands the typed prefix could become', () => {
    expect(matchingCommands('/').map((c) => c.name)).toEqual(['help', 'context', 'compact', 'btw']);
    expect(matchingCommands('/co').map((c) => c.name)).toEqual(['context', 'compact']);
    expect(matchingCommands('/COM').map((c) => c.name)).toEqual(['compact']);
    expect(matchingCommands('/b').map((c) => c.name)).toEqual(['btw']);
    expect(matchingCommands('/x')).toEqual([]);
    // Once the word is over, or the line is no command, the menu goes.
    expect(matchingCommands('/context ')).toEqual([]);
    expect(matchingCommands('/btw what')).toEqual([]);
    expect(matchingCommands('hi /co')).toEqual([]);
    expect(matchingCommands('')).toEqual([]);
  });
});
