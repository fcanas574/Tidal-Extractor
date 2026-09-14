import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { QueueItem } from '../api';
import { AppProvider, useApp } from '../context/AppContext';
import { queue } from '../api';
import QueueView from './QueueView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, queue: { ...actual.queue, remove: vi.fn(), add: vi.fn(), removeBatch: vi.fn(), clearCompleted: vi.fn(), clearAll: vi.fn() } };
});

function makeItem(overrides: Partial<QueueItem> = {}): QueueItem {
  return { id: 1, tidal_id: 'track-1', item_type: 'track', title: 'Track 1', artist: 'Artist 1', album: 'Album 1', quality: 'high_lossless', format: 'FLAC', status: 'queued', progress: 0, error: null, revision: 1, ...overrides };
}

function Harness({ items }: { items: QueueItem[] }) {
  const { dispatch } = useApp();
  return <><button type="button" onClick={() => dispatch({ type: 'SET_QUEUE', payload: items })}>Set queue</button><QueueView /></>;
}

function renderQueue(items: QueueItem[]) {
  render(<AppProvider><Harness items={items} /></AppProvider>);
  act(() => { screen.getByRole('button', { name: 'Set queue' }).click(); });
}

afterEach(() => vi.clearAllMocks());

describe('QueueView', () => {
  it('groups queue items and collapses completed items by default', () => {
    renderQueue([
      makeItem({ id: 1, title: 'Active track', status: 'downloading', progress: 42 }),
      makeItem({ id: 2, title: 'Failed track', status: 'failed', error: 'Network error' }),
      makeItem({ id: 3, title: 'Completed track', status: 'complete', progress: 100 }),
    ]);

    expect(screen.getByRole('heading', { name: 'Active' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Completed/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Completed track')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Completed/ }));
    expect(screen.getByText('Completed track')).toBeInTheDocument();
  });

  it('confirms active cancellation and removes queued items directly', async () => {
    vi.mocked(queue.remove).mockResolvedValue({ ok: true });
    renderQueue([makeItem({ id: 1, title: 'Downloading track', status: 'downloading', progress: 20 }), makeItem({ id: 2, title: 'Queued track' })]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Downloading track' }));
    expect(screen.getByRole('button', { name: 'Cancel download' })).toBeInTheDocument();
    expect(queue.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Keep downloading' }));
    expect(screen.queryByRole('button', { name: 'Cancel download' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove Queued track' }));
    await act(async () => {});
    expect(queue.remove).toHaveBeenCalledWith(2);
  });

  it('keeps bulk selection available and confirms selected active work', () => {
    renderQueue([makeItem({ id: 1, title: 'Selected active', status: 'downloading' }), makeItem({ id: 2, title: 'Selected queued' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Select items' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all queue items' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove selected' }));
    expect(screen.getByText('Cancel active downloads too?')).toBeInTheDocument();
    expect(queue.removeBatch).not.toHaveBeenCalled();
  });
});
