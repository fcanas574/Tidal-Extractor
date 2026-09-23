import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from '../context/AppContext';
import type { QueueItem } from '../api';
import DownloadActivityPanel from './DownloadActivityPanel';
import { queue } from '../api';

const defaultWindowWidth = window.innerWidth;

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    queue: { ...actual.queue, remove: vi.fn(), add: vi.fn() },
  };
});

function makeItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    id: 1,
    tidal_id: 'track-1',
    item_type: 'track',
    title: 'Track 1',
    artist: 'Artist 1',
    album: 'Album 1',
    quality: 'high_lossless',
    format: 'FLAC',
    status: 'queued',
    progress: 0,
    error: null,
    revision: 1,
    ...overrides,
  };
}

function Harness({ item, connected = true }: { item: QueueItem; connected?: boolean }) {
  const { dispatch } = useApp();
  return (
    <>
      <button onClick={() => dispatch({ type: 'SET_QUEUE', payload: [item] })}>Set queue</button>
      <button onClick={() => dispatch({ type: 'SET_WS_CONNECTED', payload: connected })}>Set connection</button>
      <button onClick={() => dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' })}>Open activity</button>
      <DownloadActivityPanel />
    </>
  );
}

function renderPanel(item: QueueItem, connected = true) {
  render(<AppProvider><Harness item={item} connected={connected} /></AppProvider>);
  act(() => {
    screen.getByRole('button', { name: 'Set queue' }).click();
    screen.getByRole('button', { name: 'Set connection' }).click();
    const trigger = screen.getByRole('button', { name: 'Open activity' });
    trigger.focus();
    trigger.click();
  });
}

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: defaultWindowWidth });
});

describe('DownloadActivityPanel', () => {
  it('renders canonical queue progress and status', () => {
    renderPanel(makeItem({ status: 'downloading', progress: 42 }));

    expect(screen.getByRole('dialog', { name: 'Download activity' })).toBeInTheDocument();
    expect(screen.getAllByText('Downloading')).not.toHaveLength(0);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
  });

  it('derives reconnecting and stale without changing the queue status', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    renderPanel(makeItem({ status: 'downloading', progress: 20 }), false);
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(screen.getByText('Stale')).toBeInTheDocument();
  });

  it('confirms active cancellation inline before removing the item', async () => {
    vi.mocked(queue.remove).mockResolvedValue({ ok: true });
    renderPanel(makeItem({ status: 'downloading', progress: 50 }));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Track 1' }));
    expect(screen.getByRole('button', { name: 'Cancel download' })).toBeInTheDocument();
    expect(queue.remove).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Keep downloading' }));
    expect(screen.queryByRole('button', { name: 'Cancel download' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Track 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel download' }));
    expect(queue.remove).toHaveBeenCalledWith(1);
    await act(async () => {});
  });

  it('focuses close on open, restores the trigger, and closes on Escape without being modal', () => {
    renderPanel(makeItem());

    const dialog = screen.getByRole('dialog', { name: 'Download activity' });
    const closeButton = within(dialog).getByRole('button', { name: 'Close download activity' });
    const trigger = screen.getByRole('button', { name: 'Open activity' });
    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(closeButton).toHaveFocus();

    fireEvent.click(closeButton);
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    expect(within(screen.getByRole('dialog', { name: 'Download activity' })).getByRole('button', { name: 'Close download activity' })).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Download activity' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('contains focus and exposes modal semantics for the mobile activity sheet', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    renderPanel(makeItem());

    const dialog = screen.getByRole('dialog', { name: 'Download activity' });
    const closeButton = within(dialog).getByRole('button', { name: 'Close download activity' });
    const removeButton = within(dialog).getByRole('button', { name: 'Cancel Track 1' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey: true });
    expect(removeButton).toHaveFocus();
    fireEvent.keyDown(removeButton, { key: 'Tab' });
    expect(closeButton).toHaveFocus();
  });
});
