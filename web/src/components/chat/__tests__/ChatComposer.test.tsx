import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ChatComposer, MAX_ROWS } from '../ChatComposer';

afterEach(cleanup);

const renderComposer = (disabled = false, hint: string | null = null) => {
  const onSend = vi.fn();
  render(
    <UiLanguageProvider>
      <ChatComposer disabled={disabled} disabledHint={hint} onSend={onSend} />
    </UiLanguageProvider>,
  );
  return onSend;
};

describe('ChatComposer', () => {
  it('sends on Enter and clears, keeps Shift+Enter as a new line', () => {
    const onSend = renderComposer();
    const box = screen.getByTestId('chat-input') as HTMLTextAreaElement;
    expect(screen.getByTestId('chat-send')).toBeDisabled();
    fireEvent.change(box, { target: { value: '  hello  ' } });
    expect(screen.getByTestId('chat-send')).toBeEnabled();
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('hello');
    expect(box.value).toBe('');
  });

  it('sends with the button', () => {
    const onSend = renderComposer();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'go' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    expect(onSend).toHaveBeenCalledWith('go');
  });

  it('is inert with its hint while disabled', () => {
    const onSend = renderComposer(true, 'wait');
    const box = screen.getByTestId('chat-input');
    expect(box).toBeDisabled();
    expect(screen.getByText('wait')).toBeInTheDocument();
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('grows with the lines typed, up to a cap', () => {
    renderComposer();
    const box = screen.getByTestId('chat-input') as HTMLTextAreaElement;
    expect(box.rows).toBe(1);
    fireEvent.change(box, { target: { value: 'a\nb\nc' } });
    expect(box.rows).toBe(3);
    fireEvent.change(box, { target: { value: Array(20).fill('x').join('\n') } });
    expect(box.rows).toBe(MAX_ROWS);
  });

  it('moves the send arrow to its own row once the draft needs a second line', () => {
    renderComposer();
    const composer = screen.getByTestId('chat-composer');
    const box = screen.getByTestId('chat-input');
    expect(composer).toHaveAttribute('data-multiline', 'false');
    fireEvent.change(box, { target: { value: 'one line' } });
    expect(composer).toHaveAttribute('data-multiline', 'false');
    fireEvent.change(box, { target: { value: 'one line\nand another' } });
    expect(composer).toHaveAttribute('data-multiline', 'true');
    fireEvent.change(box, { target: { value: 'back to one' } });
    expect(composer).toHaveAttribute('data-multiline', 'false');
  });

  it('labels the arrow-only send button and shows the key hint as the placeholder', () => {
    renderComposer();
    const button = screen.getByTestId('chat-send');
    expect(button).toHaveAccessibleName('Send');
    expect(button).toHaveTextContent('');
    expect(screen.getByTestId('chat-input')).toHaveAttribute('placeholder', 'Enter = send; Shift+Enter = new line');
  });

  it('puts a stop button in the arrow\'s place while a turn runs, and an unclickable "…" once clicked', () => {
    const onStop = vi.fn();
    const composer = (stopping: boolean) => (
      <UiLanguageProvider>
        <ChatComposer disabled working stopping={stopping} onSend={vi.fn()} onStop={onStop} />
      </UiLanguageProvider>
    );
    const { rerender } = render(composer(false));
    expect(screen.queryByTestId('chat-send')).toBeNull();
    const stop = screen.getByTestId('chat-stop');
    expect(stop).toBeEnabled();
    expect(stop).toHaveAccessibleName('Stop');
    expect(stop).toHaveTextContent('');
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);

    // The server lets the running step finish before it stops, so the
    // wait can be long: the button gives way to a disabled "…".
    rerender(composer(true));
    expect(screen.queryByTestId('chat-stop')).toBeNull();
    const stopping = screen.getByTestId('chat-stopping');
    expect(stopping).toBeDisabled();
    expect(stopping).toHaveAccessibleName('Stopping after the current step…');
    expect(stopping).toHaveTextContent('');
  });

  it('shows the stop button disabled when there is nothing to stop yet', () => {
    render(
      <UiLanguageProvider>
        <ChatComposer disabled working onSend={vi.fn()} />
      </UiLanguageProvider>,
    );
    expect(screen.getByTestId('chat-stop')).toBeDisabled();
  });
});

describe('ChatComposer slash commands', () => {
  it('lists the commands the typed word could become, fills one in on a click or Tab, and sends the line as typed', () => {
    const onSend = renderComposer();
    const box = screen.getByTestId('chat-input') as HTMLTextAreaElement;
    expect(screen.queryByTestId('chat-command-menu')).toBeNull();
    fireEvent.change(box, { target: { value: '/co' } });
    const menu = screen.getByTestId('chat-command-menu');
    expect(menu).toHaveTextContent('/context');
    expect(menu).toHaveTextContent('/compact');
    expect(menu).not.toHaveTextContent('/help');
    // Tab fills in the first; the menu closes once the word is whole.
    fireEvent.keyDown(box, { key: 'Tab' });
    expect(box.value).toBe('/context');
    expect(screen.getByTestId('chat-command-menu')).toHaveTextContent('/context');
    fireEvent.change(box, { target: { value: '/' } });
    fireEvent.click(screen.getByTestId('chat-command-compact'));
    expect(box.value).toBe('/compact');
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('/compact');
    expect(screen.queryByTestId('chat-command-menu')).toBeNull();
  });

  it('offers no menu for a message or while disabled', () => {
    renderComposer();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'tell me /co' } });
    expect(screen.queryByTestId('chat-command-menu')).toBeNull();
    cleanup();
    renderComposer(true, 'wait');
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: '/co' } });
    expect(screen.queryByTestId('chat-command-menu')).toBeNull();
  });
});
