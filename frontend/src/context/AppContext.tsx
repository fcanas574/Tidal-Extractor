import { createContext, useContext, useReducer, Dispatch } from 'react';
import type {
  AuthStatus,
  AlbumDetailResult,
  ArtistTracksResult,
  HistoryItem,
  QueueItem,
  ResolveResult,
  SearchFilters,
  SearchResult,
  SearchType,
  Settings,
  TrackResult,
  WsMessage,
} from '../api';

export interface PreviewTrack {
  id: number;
  title: string;
  artist: string;
  artist_id: number | null;
  cover_url: string | null;
  key: string | null;
  camelot: string | null;
}

export interface Toast {
  id: string;
  type: 'info' | 'success' | 'error' | 'downloading';
  title: string;
  detail?: string;
  progress?: number;
  dismissAt?: number;
}

interface QueueMeta {
  revision: number;
  lastProgressAt: number | null;
  terminal?: { revision: number; status: 'complete' | 'failed' };
  optimisticAt?: number;
}

const OPTIMISTIC_QUEUE_TTL = 30_000;
const MAX_OPTIMISTIC_QUEUE_ITEMS = 50;

export type SearchStatus = 'idle' | 'loading' | 'success' | 'error';

type DetailStatus = 'loading' | 'success' | 'error';

export type CatalogDetail =
  | { kind: 'artist'; id: number; status: DetailStatus; data: ResolveResult | null; error: string | null; tracksStatus: DetailStatus }
  | { kind: 'album'; id: number; status: DetailStatus; data: AlbumDetailResult | null; error: string | null };

export interface SearchSession {
  query: string;
  type: SearchType;
  filters: SearchFilters;
  results: SearchResult | null;
  detail: CatalogDetail | null;
  status: SearchStatus;
  error: string | null;
  partialError: string | null;
  loadingMore: boolean;
}

export interface AppState {
  auth: AuthStatus;
  activeTab: 'search' | 'queue' | 'history' | 'stats';
  queue: QueueItem[];
  queueMeta: Record<number, QueueMeta>;
  settings: Settings;
  settingsPanelOpen: boolean;
  activityPanelOpen: boolean;
  wsConnected: boolean;
  toasts: Toast[];
  previewTrack: PreviewTrack | null;
  previewPlaying: boolean;
  requestedArtistId: number | null;
  history: HistoryItem[];
  historyLoading: boolean;
  stats: Record<string, number>;
  search: SearchSession;
}

type Action =
  | { type: 'SET_AUTH'; payload: AuthStatus }
  | { type: 'SET_TAB'; payload: AppState['activeTab'] }
  | { type: 'SET_QUEUE'; payload: QueueItem[] }
  | { type: 'UPDATE_QUEUE_ITEM'; payload: QueueItem }
  | { type: 'REMOVE_QUEUE_ITEM'; payload: number }
  | { type: 'SET_SETTINGS'; payload: Settings }
  | { type: 'WS_MESSAGE'; payload: WsMessage }
  | { type: 'SET_WS_CONNECTED'; payload: boolean }
  | { type: 'TOGGLE_SETTINGS_PANEL' }
  | { type: 'TOGGLE_ACTIVITY_PANEL' }
  | { type: 'ADD_TOAST'; payload: Toast }
  | { type: 'REMOVE_TOAST'; payload: string }
  | { type: 'UPDATE_TOAST'; payload: { id: string; progress?: number; detail?: string } }
  | { type: 'SET_PREVIEW'; payload: PreviewTrack }
  | { type: 'CLEAR_PREVIEW' }
  | { type: 'SET_PREVIEW_PLAYING'; payload: boolean }
  | { type: 'REQUEST_ARTIST_DETAIL'; payload: number }
  | { type: 'CONSUME_ARTIST_DETAIL_REQUEST'; payload: number }
  | { type: 'SET_HISTORY'; payload: HistoryItem[] }
  | { type: 'SET_HISTORY_LOADING'; payload: boolean }
  | { type: 'SET_STATS'; payload: Record<string, number> }
  | { type: 'SET_SEARCH_QUERY'; payload: string }
  | { type: 'SET_SEARCH_TYPE'; payload: SearchType }
  | { type: 'SET_SEARCH_FILTERS'; payload: SearchFilters }
  | { type: 'SEARCH_STARTED'; payload: { query: string; type: SearchType; filters: SearchFilters } }
  | { type: 'SEARCH_SUCCEEDED'; payload: SearchResult }
  | { type: 'SEARCH_FAILED'; payload: string }
  | { type: 'SEARCH_MORE_STARTED' }
  | { type: 'SEARCH_MORE_SUCCEEDED'; payload: { type: SearchType; result: SearchResult } }
  | { type: 'SEARCH_MORE_FAILED'; payload: string }
  | { type: 'DETAIL_STARTED'; payload: { kind: CatalogDetail['kind']; id: number } }
  | { type: 'DETAIL_SUCCEEDED'; payload:
      | { kind: 'artist'; id: number; data: ResolveResult; tracksStatus?: DetailStatus }
      | { kind: 'album'; id: number; data: AlbumDetailResult } }
  | { type: 'DETAIL_FAILED'; payload: { kind: CatalogDetail['kind']; id: number; error: string } }
  | { type: 'DETAIL_ARTIST_TRACKS_SUCCEEDED'; payload: { id: number; data: ArtistTracksResult } }
  | { type: 'DETAIL_ARTIST_TRACKS_FAILED'; payload: { id: number; error: string } }
  | { type: 'CLOSE_DETAIL' }
  | { type: 'CLEAR_SEARCH' };

const initialState: AppState = {
  auth: { authenticated: false, username: null },
  activeTab: 'search',
  queue: [],
  queueMeta: {},
  settings: { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads', waveform_color: '3band' },
  settingsPanelOpen: false,
  activityPanelOpen: false,
  wsConnected: false,
  toasts: [],
  previewTrack: null,
  previewPlaying: false,
  requestedArtistId: null,
  history: [],
  historyLoading: false,
  stats: {},
  search: {
    query: '',
    type: 'track',
    filters: {},
    results: null,
    detail: null,
    status: 'idle',
    error: null,
    partialError: null,
    loadingMore: false,
  },
};

type TerminalStatus = 'complete' | 'failed';

function revisionOf(item: QueueItem) {
  return Number.isFinite(item.revision) ? item.revision : 0;
}

function progressOf(item: QueueItem) {
  return Number.isFinite(item.progress) ? item.progress : 0;
}

function isTerminal(status: QueueItem['status']): status is TerminalStatus {
  return status === 'complete' || status === 'failed';
}

function reconcileItem(
  current: QueueItem | undefined,
  incoming: QueueItem,
  previousMeta: QueueMeta | undefined,
): { item: QueueItem; meta: QueueMeta } {
  const incomingRevision = revisionOf(incoming);
  const currentRevision = Math.max(previousMeta?.revision ?? 0, current ? revisionOf(current) : 0);

  if (current && incomingRevision < currentRevision) {
    return { item: current, meta: previousMeta ?? { revision: currentRevision, lastProgressAt: null } };
  }

  let item = { ...incoming, revision: Math.max(incomingRevision, currentRevision) };
  if (current) {
    const sameLegacyRevision = incomingRevision === 0 && currentRevision === 0;
    const currentTerminal = isTerminal(current.status);

    // Legacy rows have no ordering signal. Preserve terminal state and the
    // greatest observed progress instead of trusting response arrival order.
    if (sameLegacyRevision && currentTerminal) item = { ...current };

    if (progressOf(current) > progressOf(item)) {
      item = { ...item, progress: current.progress };
    }
  }

  const previousProgress = current ? progressOf(current) : -1;
  const lastProgressAt = previousMeta?.lastProgressAt ?? null;
  const progressAdvanced = progressOf(item) > previousProgress;
  const meta: QueueMeta = {
    revision: item.revision,
    lastProgressAt:
      item.status === 'downloading' && (lastProgressAt === null || progressAdvanced)
        ? Date.now()
        : lastProgressAt,
    terminal: previousMeta?.terminal,
  };

  return { item, meta };
}

function mergeQueueSnapshot(state: AppState, incomingItems: QueueItem[]): Pick<AppState, 'queue' | 'queueMeta'> {
  const queueMeta: Record<number, QueueMeta> = {};
  const incomingIds = new Set(incomingItems.map((item) => item.id));
  const now = Date.now();
  const optimisticItems = state.queue
    .filter((item) => {
      const meta = state.queueMeta[item.id];
      return !incomingIds.has(item.id)
        && meta?.optimisticAt !== undefined
        && now - meta.optimisticAt < OPTIMISTIC_QUEUE_TTL;
    })
    .slice(-MAX_OPTIMISTIC_QUEUE_ITEMS);
  const queueItems = incomingItems.map((incoming) => {
    const current = state.queue.find((item) => item.id === incoming.id);
    const result = reconcileItem(current, incoming, state.queueMeta[incoming.id]);
    queueMeta[incoming.id] = result.meta;
    return result.item;
  });

  for (const item of optimisticItems) {
    queueItems.push(item);
    queueMeta[item.id] = state.queueMeta[item.id];
  }

  return { queue: queueItems, queueMeta };
}

function mergeSearchItems<T extends { id: number | string }>(current: T[], incoming: T[]) {
  const merged = [...current];
  const seen = new Set(current.map((item) => String(item.id)));
  for (const item of incoming) {
    const id = String(item.id);
    if (seen.has(id)) continue;
    seen.add(id);
    merged.push(item);
  }
  return merged;
}

function appendSearchPage(
  current: SearchResult | null,
  incoming: SearchResult,
  type: SearchType,
): SearchResult {
  if (!current) return incoming;
  const page = {
    offset: incoming.offset,
    limit: incoming.limit,
    has_more: incoming.has_more,
  };

  switch (type) {
    case 'track':
      return { ...current, tracks: mergeSearchItems(current.tracks, incoming.tracks), ...page };
    case 'artist':
      return { ...current, artists: mergeSearchItems(current.artists, incoming.artists), ...page };
    case 'album':
      return { ...current, albums: mergeSearchItems(current.albums, incoming.albums), ...page };
    case 'playlist':
      return { ...current, playlists: mergeSearchItems(current.playlists, incoming.playlists), ...page };
  }
}

function mergeCatalogMetadataPatch(current: TrackResult, patch: TrackResult): TrackResult {
  return {
    ...current,
    bpm: current.bpm ?? patch.bpm,
    key: current.key ?? patch.key,
    bpm_source: current.bpm_source ?? patch.bpm_source,
    key_source: current.key_source ?? patch.key_source,
    camelot: patch.camelot ?? current.camelot,
    open_key: patch.open_key ?? current.open_key,
    key_label: patch.key_label ?? current.key_label,
    genre: patch.genre ?? current.genre,
    bpm_alt: patch.bpm_alt ?? current.bpm_alt,
    bpm_confidence: patch.bpm_confidence ?? current.bpm_confidence,
    key_confidence: patch.key_confidence ?? current.key_confidence,
    key_int: patch.key_int ?? current.key_int,
    mode: patch.mode ?? current.mode,
    source: patch.source ?? current.source,
    genre_source: patch.genre_source ?? current.genre_source,
    metadata_status: patch.metadata_status ?? current.metadata_status,
  };
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_AUTH':
      return { ...state, auth: action.payload };
    case 'SET_TAB':
      return { ...state, activeTab: action.payload };
    case 'SET_QUEUE': {
      return { ...state, ...mergeQueueSnapshot(state, action.payload) };
    }
    case 'UPDATE_QUEUE_ITEM': {
      const current = state.queue.find((item) => item.id === action.payload.id);
      const result = reconcileItem(current, action.payload, state.queueMeta[action.payload.id]);
      const nextMeta = { ...result.meta, optimisticAt: Date.now() };
      return {
        ...state,
        queue: current
          ? state.queue.map((item) => item.id === action.payload.id ? result.item : item)
          : [...state.queue, result.item],
        queueMeta: { ...state.queueMeta, [action.payload.id]: nextMeta },
      };
    }
    case 'REMOVE_QUEUE_ITEM':
      return {
        ...state,
        queue: state.queue.filter((item) => item.id !== action.payload),
        queueMeta: Object.fromEntries(
          Object.entries(state.queueMeta).filter(([id]) => Number(id) !== action.payload)
        ),
      };
    case 'SET_SETTINGS':
      return { ...state, settings: action.payload };
    case 'WS_MESSAGE': {
      const msg = action.payload;
      if (msg.type === 'catalog_metadata') {
        const results = state.search.results;
        if (!results) return state;

        const patches = new Map(msg.tracks.map((track) => [track.id, track]));
        let updated = false;
        const tracks = results.tracks.map((track) => {
          const patch = patches.get(track.id);
          if (!patch) return track;
          updated = true;
          return mergeCatalogMetadataPatch(track, patch);
        });
        if (!updated) return state;

        return {
          ...state,
          search: {
            ...state.search,
            results: { ...results, tracks, metadata_pending: false },
          },
        };
      }
      if (msg.type === 'progress') {
        const item = state.queue.find((candidate) => String(candidate.id) === msg.id);
        if (!item) return state;

        const meta = state.queueMeta[item.id];
        const currentRevision = Math.max(meta?.revision ?? 0, revisionOf(item));
        const messageRevision = typeof msg.revision === 'number' ? msg.revision : currentRevision;
        if (messageRevision < currentRevision || (isTerminal(item.status) && messageRevision <= currentRevision)) {
          return state;
        }

        const rawPct = typeof msg.pct === 'number' ? msg.pct : Number(msg.pct) || 0;
        const pct = Math.max(0, Math.min(100, rawPct));
        const nextProgress = Math.max(progressOf(item), pct);
        const progressAdvanced = nextProgress > progressOf(item);
        const nextRevision = Math.max(currentRevision, messageRevision);
        const nextItem: QueueItem = {
          ...item,
          status: 'downloading',
          progress: nextProgress,
          revision: nextRevision,
        };
        const nextMeta: QueueMeta = {
          revision: nextRevision,
          lastProgressAt: progressAdvanced ? Date.now() : (meta?.lastProgressAt ?? Date.now()),
          terminal: meta?.terminal,
        };
        return {
          ...state,
          queue: state.queue.map((candidate) => candidate.id === item.id ? nextItem : candidate),
          queueMeta: { ...state.queueMeta, [item.id]: nextMeta },
        };
      }
      if (msg.type === 'complete') {
        const item = state.queue.find((candidate) => String(candidate.id) === msg.id);
        if (!item) return state;
        const meta = state.queueMeta[item.id];
        const currentRevision = Math.max(meta?.revision ?? 0, revisionOf(item));
        const messageRevision = typeof msg.revision === 'number' ? msg.revision : currentRevision;
        if (messageRevision < currentRevision) return state;

        const terminal = { revision: Math.max(currentRevision, messageRevision), status: 'complete' as const };
        if (meta?.terminal?.revision === terminal.revision && meta.terminal.status === terminal.status) return state;
        const nextItem = { ...item, status: 'complete' as const, progress: 100, error: null, revision: terminal.revision };
        return {
          ...state,
          queue: state.queue.map((candidate) => candidate.id === item.id ? nextItem : candidate),
          queueMeta: {
            ...state.queueMeta,
            [item.id]: { ...meta, revision: terminal.revision, lastProgressAt: meta?.lastProgressAt ?? null, terminal },
          },
          toasts: [
                ...state.toasts.filter((toast) => toast.id !== `dl-${msg.id}` && toast.id !== `done-${msg.id}`),
                {
                  id: `done-${msg.id}`,
                  type: 'success' as const,
                  title: item.title || 'Download complete',
                  detail: 'Saved to output directory',
                  dismissAt: Date.now() + 4000,
                },
              ],
        };
      }
      if (msg.type === 'error') {
        const item = state.queue.find((candidate) => String(candidate.id) === msg.id);
        if (!item) return state;
        const meta = state.queueMeta[item.id];
        const currentRevision = Math.max(meta?.revision ?? 0, revisionOf(item));
        const messageRevision = typeof msg.revision === 'number' ? msg.revision : currentRevision;
        if (messageRevision < currentRevision) return state;

        const terminal = { revision: Math.max(currentRevision, messageRevision), status: 'failed' as const };
        if (meta?.terminal?.revision === terminal.revision && meta.terminal.status === terminal.status) return state;
        const reason = (msg.reason as string) || 'Unknown error';
        const nextItem = { ...item, status: 'failed' as const, error: reason, revision: terminal.revision };
        return {
          ...state,
          queue: state.queue.map((candidate) => candidate.id === item.id ? nextItem : candidate),
          queueMeta: {
            ...state.queueMeta,
            [item.id]: { ...meta, revision: terminal.revision, lastProgressAt: meta?.lastProgressAt ?? null, terminal },
          },
          toasts: [
                ...state.toasts.filter((toast) => toast.id !== `dl-${msg.id}` && toast.id !== `err-${msg.id}`),
                {
                  id: `err-${msg.id}`,
                  type: 'error' as const,
                  title: item.title || 'Download failed',
                  detail: reason,
                  dismissAt: Date.now() + 6000,
                },
              ],
        };
      }
      return state;
    }
    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.payload };
    case 'TOGGLE_SETTINGS_PANEL':
      return { ...state, settingsPanelOpen: !state.settingsPanelOpen };
    case 'TOGGLE_ACTIVITY_PANEL':
      return { ...state, activityPanelOpen: !state.activityPanelOpen };
    case 'ADD_TOAST':
      return {
        ...state,
        toasts: [
          ...state.toasts,
          {
            ...action.payload,
            dismissAt: action.payload.dismissAt ?? Date.now() + 4000,
          },
        ],
      };
    case 'REMOVE_TOAST':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.payload) };
    case 'UPDATE_TOAST':
      return {
        ...state,
        toasts: state.toasts.map((t) =>
          t.id === action.payload.id
            ? { ...t, ...action.payload }
            : t
        ),
      };
    case 'SET_PREVIEW':
      return { ...state, previewTrack: action.payload, previewPlaying: true };
    case 'CLEAR_PREVIEW':
      return { ...state, previewTrack: null, previewPlaying: false };
    case 'SET_PREVIEW_PLAYING':
      return { ...state, previewPlaying: action.payload };
    case 'REQUEST_ARTIST_DETAIL':
      return { ...state, activeTab: 'search', requestedArtistId: action.payload };
    case 'CONSUME_ARTIST_DETAIL_REQUEST':
      return state.requestedArtistId === action.payload
        ? { ...state, requestedArtistId: null }
        : state;
    case 'SET_HISTORY':
      return { ...state, history: action.payload, historyLoading: false };
    case 'SET_HISTORY_LOADING':
      return { ...state, historyLoading: action.payload };
    case 'SET_STATS':
      return { ...state, stats: action.payload };
    case 'SET_SEARCH_QUERY':
      return { ...state, search: { ...state.search, query: action.payload } };
    case 'SET_SEARCH_TYPE':
      return { ...state, search: { ...state.search, type: action.payload } };
    case 'SET_SEARCH_FILTERS':
      return { ...state, search: { ...state.search, filters: action.payload } };
    case 'SEARCH_STARTED':
      return {
        ...state,
        search: {
          ...state.search,
          query: action.payload.query,
          type: action.payload.type,
          filters: action.payload.filters,
          detail: null,
          status: 'loading',
          error: null,
          partialError: null,
          loadingMore: false,
        },
      };
    case 'SEARCH_SUCCEEDED':
      return {
        ...state,
        search: {
          ...state.search,
          results: action.payload,
          detail: null,
          status: 'success',
          error: null,
          partialError: null,
          loadingMore: false,
        },
      };
    case 'SEARCH_FAILED':
      return {
        ...state,
        search: {
          ...state.search,
          status: 'error',
          error: action.payload,
          loadingMore: false,
        },
      };
    case 'SEARCH_MORE_STARTED':
      return {
        ...state,
        search: { ...state.search, loadingMore: true, partialError: null },
      };
    case 'SEARCH_MORE_SUCCEEDED':
      return {
        ...state,
        search: {
          ...state.search,
          results: appendSearchPage(state.search.results, action.payload.result, action.payload.type),
          status: 'success',
          partialError: null,
          loadingMore: false,
        },
      };
    case 'SEARCH_MORE_FAILED':
      return {
        ...state,
        search: { ...state.search, partialError: action.payload, loadingMore: false },
      };
    case 'DETAIL_STARTED':
      return {
        ...state,
        search: {
          ...state.search,
          detail: action.payload.kind === 'artist'
            ? { kind: 'artist', id: action.payload.id, status: 'loading', data: null, error: null, tracksStatus: 'loading' }
            : { kind: 'album', id: action.payload.id, status: 'loading', data: null, error: null },
        },
      };
    case 'DETAIL_SUCCEEDED': {
      const current = state.search.detail;
      if (!current || current.kind !== action.payload.kind || current.id !== action.payload.id) return state;
      const nextDetail = action.payload.kind === 'album' && current.kind === 'album'
        ? { ...current, status: 'success' as const, data: action.payload.data, error: null }
        : action.payload.kind === 'artist' && current.kind === 'artist'
          ? { ...current, status: 'success' as const, data: action.payload.data, error: null, tracksStatus: action.payload.tracksStatus ?? 'loading' }
          : null;
      if (!nextDetail) return state;
      return {
        ...state,
        search: {
          ...state.search,
          detail: nextDetail,
          status: 'success',
          error: null,
        },
      };
    }
    case 'DETAIL_ARTIST_TRACKS_SUCCEEDED': {
      const current = state.search.detail;
      if (!current || current.kind !== 'artist' || current.id !== action.payload.id || !current.data) return state;
      const errors = { ...current.data.errors, ...action.payload.data.errors };
      return {
        ...state,
        search: {
          ...state.search,
          detail: {
            ...current,
            tracksStatus: 'success',
            data: {
              ...current.data,
              tracks: action.payload.data.tracks,
              errors: Object.keys(errors).length > 0 ? errors : undefined,
            },
          },
        },
      };
    }
    case 'DETAIL_ARTIST_TRACKS_FAILED': {
      const current = state.search.detail;
      if (!current || current.kind !== 'artist' || current.id !== action.payload.id || !current.data) return state;
      return {
        ...state,
        search: {
          ...state.search,
          detail: {
            ...current,
            tracksStatus: 'error',
            data: {
              ...current.data,
              errors: { ...current.data.errors, tracks: action.payload.error },
            },
          },
        },
      };
    }
    case 'DETAIL_FAILED': {
      const current = state.search.detail;
      if (!current || current.kind !== action.payload.kind || current.id !== action.payload.id) return state;
      return {
        ...state,
        search: {
          ...state.search,
          detail: { ...current, status: 'error', error: action.payload.error },
          status: 'success',
        },
      };
    }
    case 'CLOSE_DETAIL':
      return { ...state, search: { ...state.search, detail: null } };
    case 'CLEAR_SEARCH':
      return {
        ...state,
        search: {
          ...state.search,
          query: '',
          results: null,
          detail: null,
          status: 'idle',
          error: null,
          partialError: null,
          loadingMore: false,
        },
      };
    default:
      return state;
  }
}

const AppContext = createContext<{
  state: AppState;
  dispatch: Dispatch<Action>;
} | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
