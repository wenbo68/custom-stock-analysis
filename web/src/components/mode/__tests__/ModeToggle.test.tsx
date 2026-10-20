import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ModeToggle } from '../ModeToggle';
import { CHAT_PATH_STORAGE_KEY } from '../useModeChoice';

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});

const AgenticPage = () => <p>agentic page at {useLocation().pathname}</p>;

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <UiLanguageProvider>
        <ModeToggle />
        <Routes>
          <Route path="/" element={<p>manual page</p>} />
          <Route path="/chat/:conversationId?" element={<AgenticPage />} />
        </Routes>
      </UiLanguageProvider>
    </MemoryRouter>,
  );

const pick = (mode: 'Manual' | 'Agentic') => {
  fireEvent.click(screen.getByRole('button', { name: 'Switch mode' }));
  fireEvent.click(screen.getByRole('menuitemradio', { name: mode }));
};

describe('ModeToggle', () => {
  it('ticks the open page and moves to the other on a pick', () => {
    renderAt('/');
    const trigger = screen.getByRole('button', { name: 'Switch mode' });
    expect(trigger).toHaveTextContent('Mode');

    fireEvent.click(trigger);
    expect(screen.getByRole('menu', { name: 'Mode options' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: 'Manual' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('menuitemradio', { name: 'Agentic' })).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Agentic' }));
    expect(screen.getByText('agentic page at /chat')).toBeInTheDocument();
    expect(screen.queryByRole('menu')).toBeNull();

    fireEvent.click(trigger);
    expect(screen.getByRole('menuitemradio', { name: 'Agentic' })).toHaveAttribute('aria-checked', 'true');
  });

  it('returns to the conversation the user was in, not a new one', () => {
    // Going manual and back landed on a new, empty conversation (owner
    // request 2026-10-20): the chat URL last shown is kept by the tab,
    // and the switch back goes there.
    renderAt('/chat/conv-1');
    expect(window.sessionStorage.getItem(CHAT_PATH_STORAGE_KEY)).toBe('/chat/conv-1');
    pick('Manual');
    expect(screen.getByText('manual page')).toBeInTheDocument();
    pick('Agentic');
    expect(screen.getByText('agentic page at /chat/conv-1')).toBeInTheDocument();
  });

  it('returns to the chat URL another instance of the page remembered', () => {
    // The manual page's menu and the chat page's are different
    // instances: the memory must outlive the chat page's.
    window.sessionStorage.setItem(CHAT_PATH_STORAGE_KEY, '/chat/conv-2');
    renderAt('/');
    pick('Agentic');
    expect(screen.getByText('agentic page at /chat/conv-2')).toBeInTheDocument();
  });

  it('opens a new conversation when the tab remembers no chat URL, or a bad one', () => {
    window.sessionStorage.setItem(CHAT_PATH_STORAGE_KEY, '/somewhere/else');
    renderAt('/');
    pick('Agentic');
    expect(screen.getByText('agentic page at /chat')).toBeInTheDocument();
  });

  it('closes on Escape without moving', () => {
    renderAt('/chat');
    fireEvent.click(screen.getByRole('button', { name: 'Switch mode' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByText('agentic page at /chat')).toBeInTheDocument();
  });
});
