import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ModeToggle } from '../ModeToggle';

afterEach(cleanup);

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <UiLanguageProvider>
        <ModeToggle />
        <Routes>
          <Route path="/" element={<p>manual page</p>} />
          <Route path="/chat" element={<p>agentic page</p>} />
        </Routes>
      </UiLanguageProvider>
    </MemoryRouter>,
  );

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
    expect(screen.getByText('agentic page')).toBeInTheDocument();
    expect(screen.queryByRole('menu')).toBeNull();

    fireEvent.click(trigger);
    expect(screen.getByRole('menuitemradio', { name: 'Agentic' })).toHaveAttribute('aria-checked', 'true');
  });

  it('closes on Escape without moving', () => {
    renderAt('/chat');
    fireEvent.click(screen.getByRole('button', { name: 'Switch mode' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByText('agentic page')).toBeInTheDocument();
  });
});
