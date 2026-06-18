import { createContext, useContext, useReducer, Dispatch } from 'react';
import type { AuthStatus, QueueItem, Settings, WsMessage, HistoryItem } from '../api';

export interface PreviewTrack {
  id: number;
  title: string;
  artist: string;
  cover_url: string | null;
}

export interface Toast {
  id: string;
  type: 'info' | 'success' | 'error' | 'downloading';
  title: string;
  detail?: string;
  progress?: number;
  dismissAt?: number;
}

export interface AppState {
  auth: AuthStatus;
  activeTab: 'search' | 'queue' | 'history';
  queue: QueueItem[];
  settings: Settings;
  settingsPanelOpen: boolean;
  wsConnected: boolean;
  toasts: Toast[];
  previewTrack: PreviewTrack | null;
  previewPlaying: boolean;
  history: HistoryItem[];
  historyLoading: boolean;
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
  | { type: 'ADD_TOAST'; payload: Toast }
  | { type: 'REMOVE_TOAST'; payload: string }
  | { type: 'UPDATE_TOAST'; payload: { id: string; progress?: number; detail?: string } }
  | { type: 'SET_PREVIEW'; payload: PreviewTrack }
  | { type: 'CLEAR_PREVIEW' }
  | { type: 'SET_PREVIEW_PLAYING'; payload: boolean }
  | { type: 'SET_HISTORY'; payload: HistoryItem[] }
  | { type: 'SET_HISTORY_LOADING'; payload: boolean };

const initialState: AppState = {
  auth: { authenticated: false, username: null },
  activeTab: 'search',
  queue: [],
  settings: { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads' },
  settingsPanelOpen: false,
  wsConnected: false,
  toasts: [],
  previewTrack: null,
  previewPlaying: false,
  history: [],
  historyLoading: false,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_AUTH':
      return { ...state, auth: action.payload };
    case 'SET_TAB':
      return { ...state, activeTab: action.payload };
    case 'SET_QUEUE':
      return { ...state, queue: action.payload };
    case 'UPDATE_QUEUE_ITEM':
      return {
        ...state,
        queue: state.queue.map((item) =>
          item.id === action.payload.id ? action.payload : item
        ),
      };
    case 'REMOVE_QUEUE_ITEM':
      return {
        ...state,
        queue: state.queue.filter((item) => item.id !== action.payload),
      };
    case 'SET_SETTINGS':
      return { ...state, settings: action.payload };
    case 'WS_MESSAGE': {
      const msg = action.payload;
      if (msg.type === 'progress') {
        const pct = (msg.pct as number) || 0;
        const item = state.queue.find((i) => String(i.id) === msg.id);
        const toastId = `dl-${msg.id}`;
        const existing = state.toasts.find((t) => t.id === toastId);
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'downloading', progress: pct }
              : item
          ),
          toasts: existing
            ? state.toasts.map((t) =>
                t.id === toastId
                  ? { ...t, progress: pct, detail: `${Math.round(pct)}%` }
                  : t
              )
            : [
                ...state.toasts,
                {
                  id: toastId,
                  type: 'downloading' as const,
                  title: item?.title || 'Downloading...',
                  detail: `${Math.round(pct)}%`,
                  progress: pct,
                },
              ],
        };
      }
      if (msg.type === 'complete') {
        const item = state.queue.find((i) => String(i.id) === msg.id);
        const toastId = `dl-${msg.id}`;
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'complete' as const, progress: 100 }
              : item
          ),
          toasts: [
            ...state.toasts.filter((t) => t.id !== toastId),
            {
              id: `done-${msg.id}`,
              type: 'success' as const,
              title: item?.title || 'Download complete',
              detail: 'Saved to output directory',
              dismissAt: Date.now() + 4000,
            },
          ],
        };
      }
      if (msg.type === 'error') {
        const item = state.queue.find((i) => String(i.id) === msg.id);
        const toastId = `dl-${msg.id}`;
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'failed', error: (msg.reason as string) || 'Unknown error' }
              : item
          ),
          toasts: [
            ...state.toasts.filter((t) => t.id !== toastId),
            {
              id: `err-${msg.id}`,
              type: 'error' as const,
              title: item?.title || 'Download failed',
              detail: (msg.reason as string) || 'Unknown error',
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
    case 'SET_HISTORY':
      return { ...state, history: action.payload, historyLoading: false };
    case 'SET_HISTORY_LOADING':
      return { ...state, historyLoading: action.payload };
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
