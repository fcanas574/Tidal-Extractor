import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from './AppContext';
import type { QueueItem } from '../api';

type AppDispatch = ReturnType<typeof useApp>['dispatch'];

let dispatchRef: AppDispatch | undefined;

function Harness() {
  const { state, dispatch } = useApp();
  dispatchRef = dispatch;
  const item = state.queue[0];

  return (
    <>
      <output data-testid="queue-state">{JSON.stringify(item ?? null)}</output>
      <output data-testid="queue-count">{state.queue.length}</output>
      <output data-testid="queue-meta">{JSON.stringify(state.queueMeta)}</output>
      <output data-testid="toast-state">{JSON.stringify(state.toasts.map(({ id, type }) => ({ id, type })))}</output>
    </>
  );
}

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
    revision: 0,
    ...overrides,
  };
}

function renderHarness() {
  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  );
}

function dispatch(action: Parameters<AppDispatch>[0]) {
  act(() => dispatchRef?.(action));
}

function queueState() {
  return JSON.parse(screen.getByTestId('queue-state').textContent || 'null') as QueueItem | null;
}

function queueMeta() {
  return JSON.parse(screen.getByTestId('queue-meta').textContent || '{}') as Record<string, { revision: number; lastProgressAt: number | null }>;
}

function toastState() {
  return JSON.parse(screen.getByTestId('toast-state').textContent || '[]') as { id: string; type: string }[];
}

afterEach(() => {
  vi.useRealTimers();
  dispatchRef = undefined;
});

describe('AppContext queue reconciliation', () => {
  it('keeps newer WS progress over a stale poll and accepts a newer snapshot', () => {
    renderHarness();

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ status: 'downloading', progress: 20, revision: 2 })] });
    dispatch({ type: 'WS_MESSAGE', payload: { type: 'progress', id: '1', pct: 60, revision: 3 } });
    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ title: 'Stale title', status: 'downloading', progress: 30, revision: 2 })] });

    expect(queueState()).toMatchObject({ title: 'Track 1', progress: 60, revision: 3, status: 'downloading' });

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ title: 'Fresh title', status: 'downloading', progress: 70, revision: 4 })] });
    expect(queueState()).toMatchObject({ title: 'Fresh title', progress: 70, revision: 4 });
  });

  it('guards progress monotonically, records freshness, and creates no progress toast', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    renderHarness();

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ status: 'downloading', progress: 10, revision: 1 })] });
    expect(queueMeta()['1'].lastProgressAt).toBe(1000);

    vi.setSystemTime(2000);
    dispatch({ type: 'WS_MESSAGE', payload: { type: 'progress', id: '1', pct: 20, revision: 2 } });
    expect(queueState()).toMatchObject({ progress: 20, revision: 2 });
    expect(queueMeta()['1'].lastProgressAt).toBe(2000);
    expect(toastState()).toEqual([]);

    vi.setSystemTime(3000);
    dispatch({ type: 'WS_MESSAGE', payload: { type: 'progress', id: '1', pct: 15, revision: 3 } });
    expect(queueState()).toMatchObject({ progress: 20, revision: 3 });
    expect(queueMeta()['1'].lastProgressAt).toBe(2000);
  });

  it('deduplicates terminal notifications for the same queue revision', () => {
    renderHarness();

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ status: 'downloading', progress: 90, revision: 4 })] });
    dispatch({ type: 'WS_MESSAGE', payload: { type: 'complete', id: '1', revision: 5 } });
    dispatch({ type: 'WS_MESSAGE', payload: { type: 'complete', id: '1', revision: 5 } });

    expect(queueState()).toMatchObject({ status: 'complete', progress: 100, revision: 5 });
    expect(toastState()).toEqual([{ id: 'done-1', type: 'success' }]);

    dispatch({ type: 'WS_MESSAGE', payload: { type: 'error', id: '1', revision: 4, reason: 'late failure' } });
    expect(toastState()).toEqual([{ id: 'done-1', type: 'success' }]);
  });

  it('keeps deliberate re-downloads with distinct database ids', () => {
    renderHarness();

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ status: 'complete', revision: 1 })] });
    dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: makeItem({ id: 2, status: 'queued', revision: 1 }) });

    expect(screen.getByTestId('queue-count')).toHaveTextContent('2');
  });

  it('keeps a locally added item through a stale REST snapshot and reconciles it when it appears', () => {
    renderHarness();

    dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: makeItem({ status: 'queued', revision: 1 }) });
    dispatch({ type: 'SET_QUEUE', payload: [] });
    expect(queueState()).toMatchObject({ id: 1, status: 'queued' });

    dispatch({ type: 'SET_QUEUE', payload: [makeItem({ title: 'Server title', status: 'downloading', progress: 12, revision: 2 })] });
    expect(queueState()).toMatchObject({ title: 'Server title', status: 'downloading', progress: 12, revision: 2 });

    dispatch({ type: 'SET_QUEUE', payload: [] });
    expect(screen.getByTestId('queue-count')).toHaveTextContent('0');
  });
});
