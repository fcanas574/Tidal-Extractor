# Frontend: AppContext.tsx

**Role:** Global state store via React Context + useReducer. The single source of truth for cross-cutting app state.

**See:** [[State Management]] · [[Frontend api]] · [[Realtime Updates]]

This note documents the module structure. For the *conceptual* model and reducer behavior, see [[State Management]].

## Exports

### Types
- `PreviewTrack` — `{ id, title, artist, cover_url, key, camelot }`
- `Toast` — `{ id, type: 'info'|'success'|'error'|'downloading', title, detail?, progress?, dismissAt? }`
- `AppState` — the full store shape (19 fields)
- `Action` — discriminated union of 19 action types

### `AppProvider({ children })`
Wraps the app. Creates `[state, dispatch] = useReducer(reducer, initialState)` and provides via Context.

### `useApp()` → `{ state, dispatch }`
Hook to access store. Throws if used outside `AppProvider`.

## Reducer Structure

19 cases. The `WS_MESSAGE` case is by far the most complex — it branches on `msg.type`:

```
WS_MESSAGE:
  if msg.type === 'progress':
      update queue item (status='downloading', progress=pct)
      upsert toast 'dl-{id}' (create as 'downloading' if missing)
  if msg.type === 'complete':
      update queue item (status='complete', progress=100)
      remove 'dl-{id}' toast, add 'done-{id}' success (dismiss +4s)
  if msg.type === 'error':
      update queue item (status='failed', error=reason)
      remove 'dl-{id}' toast, add 'err-{id}' error (dismiss +6s)
  else: return state  # no-op for 'quality', 'queue_update'
```

Toast auto-dismiss times: success 4s, error 6s (via `dismissAt`).

## Initial State

```typescript
{
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
  stats: {},
}
```

> ⚠️ The default `output_dir` here (`~/Music/TidalDownloads`) differs from the committed `config.yaml` (`~/Downloads`). The real value arrives via `settings.get()` on mount, which overwrites this. See [[Configuration]].

## Design Notes

- **No middleware / no thunks** — actions are plain objects, reducer is pure
- **No persistence** — state resets on full page reload (rehydrated from API on mount)
- **WS messages funnel through one action** (`WS_MESSAGE`) rather than many — keeps the action enum small
- **Toasts live in global state** so any component can dispatch them

## See Also

- [[State Management]] (conceptual) · [[Frontend useWebSocket]] · [[Components]]
