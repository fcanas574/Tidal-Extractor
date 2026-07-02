# Backend: ws.py

**Role:** `WebSocketManager` — manages active WS connections and broadcasts messages to all clients.

**See:** [[Realtime Updates]] · [[Backend main]]

## Class: `WebSocketManager`

```python
class WebSocketManager:
    active_connections: List[WebSocket] = []
```

## Methods

### `connect(websocket)`
```python
await websocket.accept()
active_connections.append(websocket)
```

### `disconnect(websocket)`
Removes from list if present. Safe to call on an already-removed connection.

### `broadcast(message: dict)` → all clients
```python
data = json.dumps(message)
disconnected = []
for connection in active_connections:
    try:
        await connection.send_text(data)
    except Exception:
        disconnected.append(connection)
for conn in disconnected:
    disconnect(conn)          # prune dead connections
```

Two-phase: collect failures first, then disconnect — avoids mutating the list during iteration.

### `send_to(websocket, message: dict)` → single client
Sends to one connection; disconnects it on failure. (Currently unused — all sends go through `broadcast`.)

## Integration

- Instantiated as `ws_manager` singleton in `main.py`
- `@app.websocket("/ws")` calls `connect()` on entry, `disconnect()` on `WebSocketDisconnect`
- `download_track`'s progress callback calls `ws_manager.broadcast()` for `progress`/`complete`/`error`
- `probe_quality` success broadcasts `{type:'quality', id:'session', preset, bitrate}`

## Message Protocol

All messages are JSON objects with a `type` field:

| type | fields | source |
|------|--------|--------|
| `progress` | `id, pct, bytes, total` | download chunk |
| `complete` | `id, path, size` | download done |
| `error` | `id, reason` | download failed |
| `quality` | `id, preset, bitrate` | probe success |

See [[Realtime Updates]] for the frontend handling.

## See Also

- [[Realtime Updates]] · [[Backend main]] · [[Frontend useWebSocket]]
