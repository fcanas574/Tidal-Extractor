# System Design

High-level architecture of TidalExtractor.

## Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                       Browser (localhost:3000)                    │
│  React 18 + TS  ·  Vite dev server proxies /api + /ws → :8000    │
│                                                                  │
│  AppContext (useReducer)  ←──── WebSocket messages ────┐         │
│       │                                                │         │
│       ├── SearchView  ──► /search, /resolve            │         │
│       ├── QueueView   ──► /queue/*                     │         │
│       ├── HistoryView ──► /history, /history/re-download│        │
│       ├── StatsView   ──► /stats                       │         │
│       └── AudioPlayerFooter ──► /preview/{id}          │         │
└────────────────────────────────────────────────────────┼────────┘
                         │ REST (fetch)                   │
                         ▼                                │
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Backend (localhost:8000)                     │
│                                                                  │
│  Singletons (module-level):                                      │
│    config: AppConfig   db: Database   auth_manager: AuthManager  │
│    ws_manager: WebSocketManager   orchestrator: DownloadOrchestrator │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │  Auth       │  │  Search      │  │  DownloadOrchestrator   │  │
│  │  /auth/*    │  │  /search     │  │  /queue, /history       │  │
│  │             │  │  /resolve    │  │  process_queue() loop   │  │
│  │             │  │  /preview    │  │                         │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘  │
│         │                │                       │                │
│         ▼                ▼                       ▼                │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    SQLite (tidal_extractor.db)            │    │
│  │  queue · history · device_stats · quality_cache · key_cache │  │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  External calls:                                                 │
│    • tidalapi  → Tidal API (search, streams, metadata)           │
│    • freqblog  → api.freqblog.com/lookup                         │
│    • ffmpeg/ffprobe → format conversion + bitrate verify         │
│    • librosa   → local key/BPM analysis                          │
│    • wavypy (subprocess) → tri-band waveform                     │
└─────────────────────────────────────────────────────────────────┘
```

## Key Architectural Decisions

### 1. Module-level singletons (not DI)
`main.py` instantiates `config`, `db`, `auth_manager`, `ws_manager` at import time. The `orchestrator` is created lazily *after* auth succeeds (during lifespan or device-link verify). Endpoints access these globals directly.

**Implication:** Stateful, single-process design. Not horizontally scalable, but appropriate for a single-user local tool.

### 2. Single aiosqlite connection
`Database` opens one connection in `init()` (lifespan), enables WAL, and reuses it for all queries. No connection pool — relies on SQLite's serialized writes.

### 3. Background task per queue add
`POST /queue/add` inserts the row, then fires `asyncio.create_task(_process_queue_if_idle())`. The orchestrator's `_running` flag prevents concurrent processing loops; it processes items sequentially until the queue drains.

### 4. In-memory caches
Two module-level dicts live in `main.py`:
- `_search_results_cache` — full search result lists keyed by `{query}:{type}` for pagination
- `freqblog_stats` — hit/miss/error counters (reset on restart)

These do **not** persist across restarts. See [[Gotchas & Traps]].

### 5. Sync-blocking work offloaded to threads
All tidalapi, ffmpeg, librosa, and wavypy calls are synchronous. They're wrapped in `asyncio.to_thread(...)` to avoid blocking the event loop.

### 6. WebSocket for download progress, polling for queue state
Downloads push `progress`/`complete`/`error` over `/ws`. The frontend *also* polls `GET /queue` every 5s as a fallback reconciliation (see `App.tsx`).

## Lifespan Lifecycle (`main.py:64-73`)

```
startup:
  await db.init()                      # open connection, create tables, migrations
  _cleanup_tmp_files(config.output_dir)  # remove stale *.tmp from crashes
  if auth_manager.load_saved_session(): # try tidal-session.json
      orchestrator = DownloadOrchestrator(...)
      orchestrator.set_session(...)

shutdown:
  await db.close()
```

## Cross-Cutting Concerns

| Concern | Approach |
|---------|----------|
| **Auth gating** | Most endpoints check `auth_manager.is_authenticated` → 401 if false |
| **Error handling** | Try/except per endpoint, raises `HTTPException` with detail string |
| **Logging** | `logging.basicConfig(level=DEBUG)`; `freqblog` logger at DEBUG, `main` at INFO |
| **CORS** | Allows `localhost:3000` + `localhost:5173`, all methods/headers, credentials |
| **Tmp cleanup** | Stale `.tmp` download files purged on startup |

## See Also

- [[Request Lifecycle]] — Step-by-step download flow
- [[API Reference]] — Endpoint inventory
- [[Data Model]] — SQLite schema
- [[Realtime Updates]] — WebSocket protocol
