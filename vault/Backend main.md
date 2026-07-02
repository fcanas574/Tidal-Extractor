# Backend: main.py

**Role:** FastAPI application — all REST endpoints, the WebSocket endpoint, app lifespan, and module-level singletons. ~584 lines. This is the orchestrator of orchestrators.

**See:** [[System Design]] · [[API Reference]] · [[Request Lifecycle]]

## Module-Level Singletons

```python
config = AppConfig()                    # loads config.yaml
db = Database()                         # not yet connected until lifespan
auth_manager = AuthManager()
ws_manager = WebSocketManager()
orchestrator: DownloadOrchestrator = None   # set after auth
```

### In-Memory State
```python
freqblog_stats = { hits, misses, errors, cache_hits }   # reset on restart
_search_results_cache: dict[str, list[dict]] = {}        # {query}:{type} → full track list
```

## Lifespan (`main.py:64`)

`@asynccontextmanager`:
1. `await db.init()` — open connection, create tables, run ALTER migrations
2. `_cleanup_tmp_files(config.output_dir)` — purge stale `.tmp`
3. `auth_manager.load_saved_session()` → if OK, build + bind orchestrator
4. `yield` (app runs)
5. `await db.close()`

## CORS

```python
allow_origins = ["http://localhost:3000", "http://localhost:5173"]
allow_credentials = True
allow_methods = ["*"]; allow_headers = ["*"]
```

## Helper: `filter_tracks_by_dj_metadata()` (`main.py:124`)

Pure-Python filter applied to search results:
- Expands key → `get_compatible_keys(key)` if `key_compatible=True`
- BPM range: skips tracks with `bpm is None`; enforces `bpm_min`/`bpm_max`
- Key: skips tracks missing `key` or `key_scale`; converts via `convert_to_camelot()` and checks membership

**Order matters:** filters run on the *full cached result set* BEFORE pagination slicing.

## Endpoint Groups

| Group | Endpoints | Detail |
|-------|-----------|--------|
| **Auth** | `POST /auth/device-link`, `POST /auth/device-link/verify`, `GET /auth/status`, `POST /auth/logout` | [[Auth Flow]] |
| **Search** | `GET /search`, `GET /album/{id}/tracks`, `GET /playlist/{id}/tracks`, `GET /resolve` | [[Search Subsystem]] |
| **Preview** | `GET /preview/{track_id}` | Stream URL + waveform + key detection |
| **Queue** | `POST /queue/add`, `GET /queue`, `DELETE /queue/{id}`, `DELETE /queue/completed`, `DELETE /queue/batch`, `DELETE /queue/all` | [[Request Lifecycle]] |
| **History** | `GET /history`, `POST /history/re-download` | |
| **Settings** | `GET /settings`, `PUT /settings` | [[Backend config]] |
| **Quality** | `POST /quality/probe`, `GET /quality/cache` | [[Quality Verification]] |
| **Key Detection** | `GET /key/detect`, `GET /keys/compatible` | [[Key Detection]] |
| **Stats** | `GET /stats`, `GET /freqblog/stats` | Device totals + FreqBlog hit rate |
| **WebSocket** | `WS /ws` | [[Realtime Updates]] |

Full signatures: [[API Reference]].

## Key Endpoint Details

### `/search` (`main.py:169`)
- Accepts `offset`, `limit` (default 50), `bpm_min/max`, `key`, `key_compatible`, `genre`
- **Tidal doesn't support offset natively** → backend always fetches 500, scores, caches full list, then slices
- Cache key: `"{search_query}:{type}"` (filters NOT in key — applied per-request)
- Top 5 of the page get `enrich_tracks()` for full_title/version

### `/preview/{track_id}` (`main.py:268`)
- Sets quality to `LOW` temporarily to save bandwidth
- Gets stream URL, computes waveform (`get_waveform_cached`)
- `_detect_preview_key()` — hybrid: cache → FreqBlog API → local librosa analysis
- Returns `{stream_url, waveform, key, camelot, bpm}`

### `_detect_preview_key()` (`main.py:293`)
1. Check `key_cache` table by `preview_key_{track_id}`
2. If miss, try FreqBlog API (`lookup_track_metadata`) — fast, no audio download
3. If miss, download full preview stream to tmp, run `detect_key()` (librosa)
4. Cache result (including BPM)
5. Updates `freqblog_stats` counters

### `/quality/probe` (`main.py:502`)
Delegates to `orchestrator.probe_quality()`, broadcasts result over WS, caches in DB.

## Request Bodies (Pydantic)

- `AddToQueueRequest` — `tidal_id, item_type, title, artist, album, quality, format`
- `ReDownloadRequest` — same shape as AddToQueue
- `BatchRemoveRequest` — `{ ids: list[int] }`
- `UpdateSettingsRequest` — `default_quality, default_format, output_dir`

## Logging Config

```python
logging.basicConfig(level=DEBUG)
getLogger("backend.freqblog").setLevel(DEBUG)
getLogger("backend.main").setLevel(INFO)
```

> ⚠️ Root level is DEBUG — verbose. May want INFO in production.

## See Also

- [[Backend downloader]] · [[Backend search]] · [[Backend models]] · [[API Reference]]
