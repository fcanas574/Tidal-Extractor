import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HistoryItem, QueueItem } from '../api';
import { history } from '../api';
import { AppProvider, useApp } from '../context/AppContext';
import HistoryView from './HistoryView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    history: { ...actual.history, list: vi.fn(), reDownload: vi.fn() },
  };
});

function makeHistoryItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    id: 1,
    tidal_id: 'tidal-1',
    item_type: 'track',
    title: 'Night Drive',
    artist: 'Aster Vale',
    album: 'After Hours',
    quality: 'high_lossless',
    format: 'FLAC',
    file_size: 12_582_912,
    downloaded_at: '2026-05-18T12:00:00Z',
    ...overrides,
  };
}

function makeQueueItem(): QueueItem {
  return {
    id: 22,
    tidal_id: 'tidal-1',
    item_type: 'track',
    title: 'Night Drive',
    artist: 'Aster Vale',
    album: 'After Hours',
    quality: 'high_lossless',
    format: 'FLAC',
    status: 'queued',
    progress: 0,
    error: null,
    revision: 1,
  };
}

function HistoryHarness() {
  const { state } = useApp();
  return <><span aria-label="Queue item count">{state.queue.length}</span><HistoryView /></>;
}

function renderHistory() {
  return render(<AppProvider><HistoryHarness /></AppProvider>);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

afterEach(() => vi.clearAllMocks());

describe('HistoryView', () => {
  it('shows loading and then the empty state', async () => {
    const response = deferred<HistoryItem[]>();
    vi.mocked(history.list).mockReturnValue(response.promise);
    renderHistory();

    expect(screen.getByRole('status')).toHaveTextContent('Loading download history');
    await act(async () => response.resolve([]));
    expect(await screen.findByText('No download history yet.')).toBeInTheDocument();
  });

  it('offers retry after a failed load', async () => {
    vi.mocked(history.list)
      .mockRejectedValueOnce(new Error('Offline'))
      .mockResolvedValueOnce([makeHistoryItem()]);
    renderHistory();

    expect(await screen.findByRole('alert')).toHaveTextContent('Offline');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Night Drive')).toBeInTheDocument();
    expect(history.list).toHaveBeenCalledTimes(2);
  });

  it('opens an inspector for selected history metadata without inventing absent fields', async () => {
    vi.mocked(history.list).mockResolvedValue([
      makeHistoryItem({
        title: 'A title long enough to test that a compact history row stays usable without changing the source value',
        album: null,
      }),
    ]);
    renderHistory();

    const title = 'A title long enough to test that a compact history row stays usable without changing the source value';
    expect(await screen.findByText(title)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: `Details for ${title}` }));

    const inspector = screen.getByRole('complementary', { name: 'History inspector' });
    expect(inspector).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    expect(within(inspector).getByText('Aster Vale')).toBeInTheDocument();
    expect(within(inspector).queryByText('After Hours')).not.toBeInTheDocument();
    expect(within(inspector).queryByText(/artwork|file path|unknown album/i)).not.toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toHaveAttribute('id', 'history-inspector-title'));
    expect(screen.getByRole('button', { name: '← Back to history' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '← Back to history' }));
    await waitFor(() => expect(screen.getByRole('button', { name: `Details for ${title}` })).toHaveFocus());
    expect(screen.queryByRole('complementary', { name: 'History inspector' })).not.toBeInTheDocument();
  });

  it('keeps re-download pending, success, and retryable error states', async () => {
    vi.mocked(history.list).mockResolvedValue([makeHistoryItem()]);
    const pending = deferred<QueueItem>();
    vi.mocked(history.reDownload).mockReturnValueOnce(pending.promise).mockRejectedValueOnce(new Error('Network unavailable'));
    renderHistory();
    await screen.findByText('Night Drive');

    fireEvent.click(screen.getByRole('button', { name: 'Re-download' }));
    expect(screen.getByRole('button', { name: 'Adding…' })).toBeDisabled();
    await act(async () => pending.resolve(makeQueueItem()));
    expect(await screen.findByText('Added to queue')).toBeInTheDocument();
    expect(screen.getByLabelText('Queue item count')).toHaveTextContent('1');

    fireEvent.click(screen.getByRole('button', { name: 'Re-download' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again');
    expect(screen.getByRole('button', { name: 'Retry re-download' })).toBeEnabled();
    expect(await screen.findByText('Night Drive')).toBeInTheDocument();
    await waitFor(() => expect(history.reDownload).toHaveBeenCalledTimes(2));
  });
});
