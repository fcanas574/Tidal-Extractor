# Realtime Updates

TidalExtractor uses a native **WebSocket** for download progress, with a polling fallback.

## Backend (`ws.py` + `main.py`)

### `WebSocketManager`

```python
class WebSocketManager:
    active_connections: List[WebSocket]

    async connect(ws):       # accept + append
    def disconnect(ws):      # remove
    async broadcast(msg):    # json.dumps → send to all, prune failed
    async send_to(ws, msg):  # single-target
```

### Endpoint (`main.py:576`)

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()   # keep-alive; ignores content
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

The server reads incoming text purely to detect disconnects. Clients don't need to send anything.

### Broadcast Sites

| Trigger | Message |
|---------|---------|
| Download chunk (64KB) | `{type:'progress', id, pct, bytes, total}` |
| Download complete | `{type:'complete', id, path, size}` |
| Download failed | `{type:'error', id, reason}` |
| Quality probe success | `{type:'quality', id:'session', preset, bitrate}` |

## Frontend (`hooks/useWebSocket.ts`)

```typescript
const ws = new WebSocket(`${protocol}//${host}/ws`);
ws.onmessage = (e) => onMessageRef.current(JSON.parse(e.data));
ws.onclose = () => setTimeout(connect, 3000);   // auto-reconnect after 3s
```

- Uses a ref for the callback so the effect doesn't re-run on every render
- Reconnects indefinitely on close (3s backoff)
- URL derived from `window.location` — works behind the Vite proxy in dev

Messages flow: `ws.onmessage` → `onMessage` callback → `dispatch({type:'WS_MESSAGE', payload})` → reducer (see [[State Management]]).

## Polling Fallback (`App.tsx`)

```typescript
if (state.wsConnected) {
  setInterval(() => queue.list().then(SET_QUEUE), 5000);
}
```

Every 5s the frontend refetches the full queue. This reconciles any state the WebSocket might have missed (e.g., during reconnect gaps) and catches items whose downloads started server-side without a corresponding WS broadcast in the same session.

## Dev Proxy (`vite.config.ts`)

```javascript
proxy: {
  '/api': { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '') },
  '/ws':  { target: 'ws://localhost:8000', ws: true },
}
```

Frontend `api.ts` uses `BASE = '/api'`, so all REST calls go through the proxy. The WS hook connects to `/ws` on the same origin, also proxied.

## See Also

- [[Frontend useWebSocket]] · [[State Management]] · [[Backend ws]] · [[Frontend Vite Config]]
