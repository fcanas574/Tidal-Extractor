import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from './AppContext';
import type { AlbumResult, ArtistResult, QueueItem, ResolveResult, SearchResult, TrackResult } from '../api';

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
      <output data-testid="search-state">{JSON.stringify(state.search)}</output>
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

type AppSearchState = {
  query: string;
  type: string;
  filters: Record<string, unknown>;
  results: SearchResult | null;
  artist: ResolveResult | null;
  status: string;
  error: string | null;
  partialError: string | null;
  loadingMore: boolean;
};

function searchState() {
  return JSON.parse(screen.getByTestId('search-state').textContent || '{}') as AppSearchState;
}

const track: TrackResult = {
  id: 1,
  title: 'Track One',
  artist: 'Artist One',
  album: 'Album One',
  album_id: 20,
  duration: 180,
  quality: 'LOSSLESS',
  explicit: false,
  isrc: null,
  url: '',
  cover_url: null,
  bpm: null,
  key: null,
  key_scale: null,
};

const album: AlbumResult = {
  id: 20,
  name: 'Album One',
  artist: 'Artist One',
  num_tracks: 8,
  release_date: '2025-01-01',
  release_type: 'ALBUM',
  quality: 'LOSSLESS',
  cover_url: null,
};

const artist: ArtistResult = { id: 10, name: 'Artist One', image_url: null, bio: null };

function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    tracks: [],
    artists: [],
    albums: [],
    playlists: [],
    offset: 0,
    limit: 50,
    has_more: false,
    ...overrides,
  };
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

describe('search session persistence', () => {
  it('keeps committed search results when switching tabs', () => {
    renderHarness();

    const results = makeSearchResult({ tracks: [track] });
    dispatch({ type: 'SEARCH_STARTED', payload: { query: 'Track One', type: 'track', filters: {} } });
    dispatch({ type: 'SEARCH_SUCCEEDED', payload: results });
    const before = searchState();

    dispatch({ type: 'SET_TAB', payload: 'queue' });
    dispatch({ type: 'SET_TAB', payload: 'search' });

    expect(searchState()).toEqual(before);
  });

  it('merges only the selected typed page and removes duplicate ids', () => {
    renderHarness();

    dispatch({ type: 'SEARCH_SUCCEEDED', payload: makeSearchResult({ tracks: [track], artists: [artist] }) });
    dispatch({
      type: 'SEARCH_MORE_SUCCEEDED',
      payload: {
        type: 'track',
        result: makeSearchResult({
          tracks: [track, { ...track, id: 2, title: 'Track Two' }],
          artists: [{ ...artist, id: 11, name: 'Should Not Append' }],
          offset: 1,
          has_more: true,
        }),
      },
    });

    expect(searchState().results?.tracks.map((item) => item.id)).toEqual([1, 2]);
    expect(searchState().results?.artists).toEqual([artist]);
    expect(searchState().results?.offset).toBe(1);
    expect(searchState().results?.has_more).toBe(true);
  });

  it('restores the prior result view after closing artist detail', () => {
    renderHarness();

    const results = makeSearchResult({ tracks: [track] });
    const details: ResolveResult = {
      artist,
      top_tracks: [track],
      tracks: [],
      albums: [album],
      playlists: [],
    };
    dispatch({ type: 'SEARCH_SUCCEEDED', payload: results });
    dispatch({ type: 'OPEN_ARTIST', payload: details });
    expect(searchState().artist).toEqual(details);

    dispatch({ type: 'CLOSE_ARTIST' });

    expect(searchState().artist).toBeNull();
    expect(searchState().results).toEqual(results);
  });
});
