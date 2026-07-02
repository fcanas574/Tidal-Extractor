# API Reference

Complete inventory of REST + WebSocket endpoints. Base URL in dev: `http://localhost:8000` (frontend calls go through the `/api` Vite proxy).

**See:** [[Backend main]] · [[Frontend api]] · [[Realtime Updates]]

## Auth

| Method | Path | Body | Returns | Notes |
|--------|------|------|---------|-------|
| POST | `/auth/device-link` | — | `{url, code, expires_in}` | Starts OAuth device flow |
| POST | `/auth/device-link/verify` | — | `{authenticated: true}` | Blocks until user authorizes; 401 on fail |
| GET | `/auth/status` | — | `{authenticated, username}` | |
| POST | `/auth/logout` | — | `{authenticated: false}` | Deletes session file |

## Search

| Method | Path | Query | Returns |
|--------|------|-------|---------|
| GET | `/search` | `q, type=track, offset=0, limit=50, bpm_min?, bpm_max?, key?, key_compatible=false, genre?` | `{tracks[], albums[], playlists[]}` |
| GET | `/album/{album_id}/tracks` | — | `{tracks[]}` |
| GET | `/playlist/{playlist_id}/tracks` | — | `{tracks[]}` |
| GET | `/resolve` | `url` | `{artist?, top_tracks[], tracks[], albums[], playlists[]}` |

**`/search` notes:** Tidal has no native offset — backend fetches 500, scores, caches full list, slices `[offset:offset+limit]`. Filters applied to full set before slicing. 401 if not authenticated.

## Preview

| Method | Path | Returns | Notes |
|--------|------|---------|-------|
| GET | `/preview/{track_id}` | `{stream_url, waveform, key, camelot, bpm}` | Sets quality LOW; hybrid key detection (cache→FreqBlog→librosa) |

`waveform` shape: `{bands:{low,mid,high}, colors, duration}` or empty on failure.

## Queue

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/queue/add` | `AddToQueueRequest` | `QueueItem` |
| GET | `/queue` | — | `QueueItem[]` |
| DELETE | `/queue/{item_id}` | — | `{ok: true}` |
| DELETE | `/queue/completed` | — | `{removed: n}` |
| DELETE | `/queue/batch` | `{ids: int[]}` | `{removed: n}` |
| DELETE | `/queue/all` | — | `{removed: n}` (stops orchestrator) |

### `AddToQueueRequest`
```json
{ "tidal_id": "123", "item_type": "track",
  "title": "...", "artist": "...", "album": "...",
  "quality": "high_lossless", "format": "FLAC" }
```
`item_type` may be `track`, `album`, or `playlist` (albums/playlists get expanded server-side).

## History

| Method | Path | Query/Body | Returns |
|--------|------|------------|---------|
| GET | `/history` | `offset=0, limit=100` | `HistoryItem[]` |
| POST | `/history/re-download` | `ReDownloadRequest` | `QueueItem` |

## Settings

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/settings` | — | `{default_quality, default_format, output_dir}` |
| PUT | `/settings` | `UpdateSettingsRequest` | updated settings |

## Quality

| Method | Path | Returns | Notes |
|--------|------|---------|-------|
| POST | `/quality/probe` | `{preset, bitrate}` | Walks preset ladder, caches winner; 500 if all fail |
| GET | `/quality/cache` | `{preset, bitrate}` or `null` | Reads singleton cache row |

## Key Detection

| Method | Path | Query | Returns |
|--------|------|-------|---------|
| GET | `/key/detect` | `path` | `{cached, key, camelot, confidence, bpm?}` |
| GET | `/keys/compatible` | `key` (e.g. "8A") | `{key, compatible: [...]}` |

## Stats

| Method | Path | Returns |
|--------|------|---------|
| GET | `/stats` | `Record<string, number>` (total_tracks, total_bytes, quality_*) |
| GET | `/freqblog/stats` | `{hits, misses, errors, cache_hits, total_requests, hit_rate}` |

## WebSocket

| Path | Protocol | Direction |
|------|----------|-----------|
| `/ws` | WS | Server → Client (broadcast) |

Client connects, server reads incoming text only to detect disconnects. Messages:

| `type` | Fields |
|--------|--------|
| `progress` | `id, pct, bytes, total` |
| `complete` | `id, path, size` |
| `error` | `id, reason` |
| `quality` | `id:"session", preset, bitrate` |

## Status Codes

- `200` — success
- `401` — not authenticated (most endpoints gate on `auth_manager.is_authenticated`)
- `404` — preview unavailable / resolve not found
- `422` — unparseable Tidal URL (resolve)
- `500` — server error / quality probe failed all presets

## See Also

- [[Backend main]] · [[Frontend api]] · [[Data Model]]
