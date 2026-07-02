# Frontend: useWebSocket.ts

**Role:** Auto-reconnecting WebSocket hook. Bridges server pushes into the React state layer.

**See:** [[Realtime Updates]] · [[Frontend AppContext]]

## Signature

```typescript
function useWebSocket(onMessage: (msg: WsMessage) => void): React.RefObject<WebSocket | null>
```

## Implementation

```typescript
const wsRef = useRef<WebSocket | null>(null);
const onMessageRef = useRef(onMessage);
onMessageRef.current = onMessage;    # keep latest callback without re-running effect

const connect = useCallback(() => {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onmessage = (e) => {
    try { onMessageRef.current(JSON.parse(e.data)); }
    catch { /* ignore non-JSON */ }
  };
  ws.onclose = () => setTimeout(connect, 3000);   # reconnect after 3s

  wsRef.current = ws;
}, []);

useEffect(() => {
  connect();
  return () => wsRef.current?.close();
}, [connect]);

return wsRef;
```

## Key Design Decisions

### 1. Ref for the callback
`onMessageRef` holds the latest `onMessage` without being in the effect's dependency array. This means the WebSocket is opened **once** per mount, even as the callback identity changes across renders (e.g., when `dispatch` wrapper is recreated).

### 2. Reconnect on close
`ws.onclose` schedules a reconnect after 3s. No exponential backoff — fixed delay. Reconnects indefinitely.

### 3. URL from `window.location`
Uses the current host/protocol, so it works identically in dev (via Vite proxy on `:3000`) and prod. The `/ws` path is proxied to `:8000` in dev (see [[Frontend Vite Config]]).

### 4. Silent JSON parse failures
Non-JSON messages are ignored (the server only sends JSON, but this guards against proxies injecting HTML error pages).

## Usage in App.tsx

```typescript
const handleWsMessage = useCallback((msg: WsMessage) => {
  dispatch({ type: 'WS_MESSAGE', payload: msg });
}, [dispatch]);
useWebSocket(handleWsMessage);
```

Every WS message becomes a `WS_MESSAGE` action. The reducer then branches on `msg.type` (see [[Frontend AppContext]]).

## What's NOT Here

- **No `wsConnected` dispatch from this hook.** The `wsConnected` flag in state is set elsewhere (the hook doesn't currently fire `onopen`/`onclose` callbacks into state). The 5s polling in `App.tsx` is gated on `state.wsConnected`, so that flag's source matters — verify if wiring changes.

## See Also

- [[Realtime Updates]] · [[Frontend AppContext]] · [[Backend ws]]


---

## Update (2026-06-29): `wsConnected` Now Wired

The hook now dispatches `SET_WS_CONNECTED`:
- `ws.onopen` → `SET_WS_CONNECTED true`
- `ws.onclose` → `SET_WS_CONNECTED false` (then schedules the 3s reconnect, as before)
- `ws.onerror` → `SET_WS_CONNECTED false`

**Why it matters:** `App.tsx`'s 5s queue-poll reconciler is gated on `state.wsConnected`. Before this, the flag was initialized `false` and never changed, so the poll never ran and the queue was only fetched once on mount.

The hook now pulls `dispatch` from `useApp()` (it's a stable identity from `useReducer`, so `connect`'s `useCallback` dep on `dispatch` is safe — won't churn the effect).