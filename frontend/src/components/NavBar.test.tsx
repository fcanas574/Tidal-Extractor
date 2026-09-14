import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AppProvider, useApp } from '../context/AppContext';
import NavBar from './NavBar';

function Harness() {
  const { dispatch } = useApp();

  return (
    <>
      <NavBar />
      <button type="button" onClick={() => dispatch({ type: 'SET_WS_CONNECTED', payload: false })}>
        Simulate reconnect
      </button>
    </>
  );
}

describe('NavBar', () => {
  it('exposes current navigation, panel controls, and readable connection state', () => {
    render(<AppProvider><Harness /></AppProvider>);

    expect(screen.getByRole('navigation', { name: 'Primary navigation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Queue' })).not.toHaveAttribute('aria-current');

    const activity = screen.getByRole('button', { name: /Activity/ });
    expect(activity).toHaveAttribute('aria-controls', 'download-activity-panel');
    expect(activity).toHaveAttribute('aria-expanded', 'false');

    const settings = screen.getByRole('button', { name: 'Settings' });
    expect(settings).toHaveAttribute('aria-controls', 'settings-panel');
    expect(settings).toHaveAttribute('aria-expanded', 'false');

    expect(screen.getByRole('status')).toHaveTextContent('Reconnecting');
  });

  it('keeps tab selection and panel toggles available', () => {
    render(<AppProvider><NavBar /></AppProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Queue' }));
    expect(screen.getByRole('button', { name: 'Queue' })).toHaveAttribute('aria-current', 'page');

    const activity = screen.getByRole('button', { name: /Activity/ });
    fireEvent.click(activity);
    expect(activity).toHaveAttribute('aria-expanded', 'true');

    const settings = screen.getByRole('button', { name: 'Settings' });
    fireEvent.click(settings);
    expect(settings).toHaveAttribute('aria-expanded', 'true');
    expect(activity).toHaveAttribute('aria-expanded', 'false');
  });
});
