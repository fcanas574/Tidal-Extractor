import { createContext, useContext, useReducer, Dispatch } from 'react';
import type { AuthStatus, QueueItem, Settings, WsMessage } from '../api';

export interface AppState {
  auth: AuthStatus;
  activeTab: 'search' | 'queue' | 'settings';
  queue: QueueItem[];
  settings: Settings;
  wsConnected: boolean;
}

type Action =
  | { type: 'SET_AUTH'; payload: AuthStatus }
  | { type: 'SET_TAB'; payload: AppState['activeTab'] }
  | { type: 'SET_QUEUE'; payload: QueueItem[] }
  | { type: 'UPDATE_QUEUE_ITEM'; payload: QueueItem }
  | { type: 'REMOVE_QUEUE_ITEM'; payload: number }
  | { type: 'SET_SETTINGS'; payload: Settings }
  | { type: 'WS_MESSAGE'; payload: WsMessage }
  | { type: 'SET_WS_CONNECTED'; payload: boolean };

const initialState: AppState = {
  auth: { authenticated: false, username: null },
  activeTab: 'search',
  queue: [],
  settings: { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads' },
  wsConnected: false,
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
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'downloading', progress: (msg.pct as number) || 0 }
              : item
          ),
        };
      }
      if (msg.type === 'complete') {
        return {
          ...state,
          queue: state.queue.filter((item) => String(item.id) !== msg.id),
        };
      }
      if (msg.type === 'error') {
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'failed', error: (msg.reason as string) || 'Unknown error' }
              : item
          ),
        };
      }
      return state;
    }
    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.payload };
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
