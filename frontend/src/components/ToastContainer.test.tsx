import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from '../context/AppContext';
import type { Toast } from '../context/AppContext';
import ToastContainer from './ToastContainer';

function Harness({ toasts }: { toasts: Toast[] }) {
  const { dispatch } = useApp();
  return (
    <>
      <button onClick={() => toasts.forEach((toast) => dispatch({ type: 'ADD_TOAST', payload: toast }))}>Add toasts</button>
      <ToastContainer />
    </>
  );
}

function renderToasts(toasts: Toast[]) {
  render(<AppProvider><Harness toasts={toasts} /></AppProvider>);
  act(() => screen.getByRole('button', { name: 'Add toasts' }).click());
}

const toast = (id: string, type: Toast['type'], dismissAt = Date.now() + 10_000): Toast => ({
  id,
  type,
  title: `${type} ${id}`,
  dismissAt,
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ToastContainer', () => {
  it('shows at most three discrete toasts and prioritizes errors', () => {
    renderToasts([
      toast('one', 'info'),
      toast('two', 'info'),
      toast('three', 'info'),
      toast('failure', 'error'),
      toast('progress', 'downloading'),
    ]);

    expect(screen.getAllByRole('status')).toHaveLength(2);
    expect(screen.getByRole('alert')).toHaveTextContent('error failure');
    expect(screen.queryByText('downloading progress')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Dismiss/ })).toHaveLength(3);
  });

  it('pauses auto-dismiss on hover and animates before removal', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    renderToasts([toast('one', 'info', 5000)]);
    const notification = screen.getByRole('status');

    fireEvent.mouseEnter(notification);
    act(() => vi.advanceTimersByTime(10_000));
    expect(notification).toBeInTheDocument();

    fireEvent.mouseLeave(notification);
    act(() => vi.advanceTimersByTime(3999));
    expect(notification).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(notification).toHaveClass('animate-toast-out');
    act(() => vi.advanceTimersByTime(180));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('always exposes a close action', () => {
    renderToasts([toast('one', 'success')]);
    expect(screen.getByRole('button', { name: 'Dismiss success one' })).toBeInTheDocument();
  });
});
