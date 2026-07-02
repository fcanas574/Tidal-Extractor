# Frontend: api.ts

**Role:** Typed REST client — every backend call goes through here. Defines all TypeScript interfaces that mirror backend response shapes.

**See:** [[API Reference]] · [[Backend search]] · [[Frontend AppContext]]

## Base

```typescript
const BASE = '/api';   // Vite proxy strips /api → localhost:8000

async function request<T>(path, opts?): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: {'Content-Type':'application/json'}, ...opts });
  if (!res.ok) throw new Error((await res.json().catch(()=>({detail: res.statusText}))).detail);
  return res.json();
}
```

Single error path: throws `Error(detail)` where detail comes from FastAPI's `HTTPException`.

## Interfaces

| Interface | Mirrors |
|-----------|---------|
| `TrackResult` | `format_track()` — incl. `bpm`, `key`, `key_scale` |
| `AlbumResult` | `format_album()` |
| `PlaylistResult` | `format_playlist()` |
| `ArtistResult` | `format_artist()` |
| `ResolveResult` | `resolve_url()` aggregate |
| `QueueItem` | `queue` table row (status union: queued/downloading/complete/failed) |
| `Settings` | `AppConfig.as_dict()` |
| `AuthStatus` | `auth_manager.get_status()` |
| `DeviceLink` | `get_device_link()` response |
| `HistoryItem` | `history` table row |
| `WsMessage` | WS payload (`type` union: progress/quality/complete/error/queue_update) |
| `WaveformData` | `bands {low,mid,high}`, `colors`, `duration` |

## API Namespaces

### `auth`
`getDeviceLink()`, `verifyDeviceLink()`, `getStatus()`, `logout()`

### `search`
```typescript
query(q, type='track', filters?: {
  offset?, limit?,
  bpmMin?, bpmMax?, key?, keyCompatible?, genre
})
```
URL-builds with `encodeURIComponent`. **Note:** param names map TS camelCase → snake_case (`bpmMin` → `bpm_min`).

Also: `albumTracks(id)`, `playlistTracks(id)`, `getCompatibleKeys(key)`

### `queue`
`list()`, `add(item)`, `remove(id)`, `removeBatch(ids)`, `clearCompleted()`, `clearAll()`

### `settings`
`get()`, `update(partial)`

### `quality`
`probe()`, `cache()`

### `stats`
`get()` → `Record<string, number>`

### `history`
`list(offset=0, limit=100)`, `reDownload(item)`

### `resolve`
`url(url)` → `ResolveResult`

### `preview`
`getUrl(trackId)` → `{stream_url, waveform, key, camelot, bpm}`

## Shape Sync Rule

`TrackResult` (frontend) **must** match `format_track()` output (backend `search.py`). When adding a field to one, update the other. The `bpm`/`key`/`key_scale` trio was added in lockstep for [[DJ Filters]].

## See Also

- [[API Reference]] · [[Frontend Vite Config]] · [[State Management]]
