import { describe, expect, it } from 'vitest';
import { CHAT_COMMANDS, matchingCommands, parseInput } from '../commands';

describe('chat commands', () => {
  it('tells a command from a message', () => {
    expect(parseInput('  hello /context  ')).toEqual({ kind: 'message', text: 'hello /context' });
    expect(parseInput('/context')).toEqual({ kind: 'command', command: CHAT_COMMANDS[1] });
    // Case and trailing words do not matter; no command takes arguments yet.
    expect(parseInput(' /COMPACT now ')).toEqual({ kind: 'command', command: CHAT_COMMANDS[2] });
    expect(parseInput('/help\nplease')).toEqual({ kind: 'command', command: CHAT_COMMANDS[0] });
  });

  it('names an unknown command and leaves paths alone', () => {
    expect(parseInput('/nope')).toEqual({ kind: 'unknown', name: '/nope' });
    expect(parseInput('/Model gpt')).toEqual({ kind: 'unknown', name: '/model' });
    // "/usr/bin" is no command word: a message, for the bot to puzzle over.
    expect(parseInput('/usr/bin')).toEqual({ kind: 'message', text: '/usr/bin' });
    expect(parseInput('/ context')).toEqual({ kind: 'message', text: '/ context' });
    expect(parseInput('/')).toEqual({ kind: 'message', text: '/' });
  });

  it('offers the commands the typed prefix could become', () => {
    expect(matchingCommands('/').map((c) => c.name)).toEqual(['help', 'context', 'compact']);
    expect(matchingCommands('/co').map((c) => c.name)).toEqual(['context', 'compact']);
    expect(matchingCommands('/COM').map((c) => c.name)).toEqual(['compact']);
    expect(matchingCommands('/x')).toEqual([]);
    // Once the word is over, or the line is no command, the menu goes.
    expect(matchingCommands('/context ')).toEqual([]);
    expect(matchingCommands('hi /co')).toEqual([]);
    expect(matchingCommands('')).toEqual([]);
  });
});
