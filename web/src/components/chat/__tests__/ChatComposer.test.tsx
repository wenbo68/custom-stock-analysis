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
});
