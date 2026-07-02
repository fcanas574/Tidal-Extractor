# State Management

The frontend uses **React Context + useReducer** — no Redux, no Zustand. All global state lives in a single reducer.

## The Store (`context/AppContext.tsx`)

### `AppState`

```typescript
interface AppState {
  auth: AuthStatus;              // { authenticated, username }
  activeTab: 'search' | 'queue' | 'history' | 'stats';
  queue: QueueItem[];
  settings: Settings;            // { default_quality, default_format, output_dir }
  settingsPanelOpen: boolean;
  wsConnected: boolean;
  toasts: Toast[];
  previewTrack: PreviewTrack | null;
  previewPlaying: boolean;
  history: HistoryItem[];
  historyLoading: boolean;
  stats: Record<string, number>;
}
```

### Actions (19 total)

| Action | Purpose |
|--------|---------|
| `SET_AUTH` | Auth status from `/auth/status` |
| `SET_TAB` | Switch active view |
| `SET_QUEUE` | Replace entire queue (from poll or WS reconcile) |
| `UPDATE_QUEUE_ITEM` / `REMOVE_QUEUE_ITEM` | Surgical queue edits |
| `SET_SETTINGS` | Settings from `/settings` |
| `WS_MESSAGE` | **The important one** — dispatches WS payloads into state mutations |
| `SET_WS_CONNECTED` | Connection flag from hook |
| `TOGGLE_SETTINGS_PANEL` | Drawer open/close |
| `ADD_TOAST` / `REMOVE_TOAST` / `UPDATE_TOAST` | Toast queue |
| `SET_PREVIEW` / `CLEAR_PREVIEW` / `SET_PREVIEW_PLAYING` | Audio player footer |
| `SET_HISTORY` / `SET_HISTORY_LOADING` | History list |
| `SET_STATS` | Stats dashboard |

## WebSocket Message Handling (`WS_MESSAGE` reducer)

The reducer branches on `msg.type`:

### `progress`
```
queue: map item → status='downloading', progress=pct
toasts: update existing 'dl-{id}' toast progress, OR create new 'downloading' toast
```

### `complete`
```
queue: map item → status='complete', progress=100
toasts: remove 'dl-{id}', add 'done-{id}' success toast (dismissAt +4s)
```

### `error`
```
queue: map item → status='failed', error=reason
toasts: remove 'dl-{id}', add 'err-{id}' error toast (dismissAt +6s)
```

## Initialization (`App.tsx`)

```typescript
// On mount:
settings.get().then(s => dispatch SET_SETTINGS)
queue.list().then(items => dispatch SET_QUEUE)

// While WS connected, poll queue every 5s as reconciliation:
setInterval(() => queue.list().then(SET_QUEUE), 5000)
```

The 5s poll is a **fallback** — WebSocket is the primary update channel. Polling catches any missed broadcasts.

## Keyboard Shortcuts (`App.tsx`)

| Key | Action | Condition |
|-----|--------|-----------|
| `Space` | Toggle preview play/pause | Only when `previewTrack` set; ignored in inputs |
| `Escape` | Clear preview | Only when `previewTrack` set; ignored in inputs |

Space dispatches a custom DOM event `preview-toggle-play` that `AudioPlayerFooter` listens for (decoupled from context).

## Component State (local)

Most view-specific state is local `useState`, not in the global store:
- **SearchView** — `query`, `searchType`, `results`, `bpmMin/Max`, `selectedKey`, `keyCompatible`, `selectedGenre`, `loadedCount`, `hasMore`, `loadingMore`, `artistResult`
- **SettingsPanel** — local form state, commits via `settings.update()`
- **AudioPlayerFooter** — audio element ref, canvas ref, play state, current time

This keeps the global store focused on cross-cutting concerns (auth, queue, toasts, preview, history, stats).

## See Also

- [[Frontend AppContext]] · [[Realtime Updates]] · [[Frontend useWebSocket]] · [[Components]]
