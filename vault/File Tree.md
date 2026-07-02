# File Tree

Source layout of `/Users/felipecanas/Projects/TidalExtractor`. Each module maps to a dedicated note in this vault.

## Root

```
TidalExtractor/
├── README.md                 # Project documentation (canonical feature list)
├── requirements.txt          # Pinned Python deps
├── config.yaml               # User settings (quality, format, output_dir)
├── .env                      # FREQBLOG_API_KEY (gitignored)
├── .gitmodules               # Declares backend/wavypy submodule
├── tidal-session.json        # Persisted Tidal OAuth session (gitignored)
├── tidal_extractor.db        # Main SQLite DB (queue, history, stats, caches)
├── tidal_extractor.db-shm    # SQLite WAL shared memory
├── tidal_extractor.db-wal    # SQLite WAL log
└── tidal.db                  # Empty/placeholder (unused — see note)
```

> ⚠️ `tidal.db` exists at root (0 bytes, May 21) but the active DB is `tidal_extractor.db`. See [[Gotchas & Traps]].

## `backend/`

| File | Responsibility | Note |
|------|----------------|------|
| `__init__.py` | Package marker | |
| `main.py` | FastAPI app, all REST endpoints, WebSocket endpoint, lifespan, global singletons | [[Backend main]] |
| `auth.py` | `AuthManager` — OAuth device-link flow, session load/save/logout | [[Backend auth]] |
| `config.py` | `AppConfig` — YAML config loader/saver with defaults | [[Backend config]] |
| `search.py` | Tidal search, album/playlist listing, URL parsing, scoring, enrichment | [[Backend search]] |
| `downloader.py` | `DownloadOrchestrator` — quality probe, download, convert, tag, queue processing | [[Backend downloader]] |
| `quality.py` | `get_bitrate()` (ffprobe), `bitrate_meets_threshold()`, quality presets | [[Backend quality]] |
| `converter.py` | `convert_format()` — ffmpeg format conversion | [[Backend converter]] |
| `tagger.py` | `tag_file()`, `tag_key()` — mutagen metadata for FLAC/MP3/M4A | [[Backend tagger]] |
| `models.py` | `Database` — async SQLite (aiosqlite), schema, all CRUD methods | [[Backend models]] |
| `ws.py` | `WebSocketManager` — connect/disconnect/broadcast | [[Backend ws]] |
| `waveform.py` | `build_waveform()`, wavypy subprocess integration, tri-band RMS | [[Backend waveform]] |
| `key_detection.py` | `detect_key()` (librosa chroma), Camelot mapping, `convert_to_camelot()`, `get_compatible_keys()` | [[Backend key_detection]] |
| `freqblog.py` | `lookup_track_metadata()` — FreqBlog API client | [[Backend freqblog]] |
| `audioop_stub.py` | Python 3.13+ `audioop` shim for pydub compatibility | [[Backend audioop_stub]] |
| `wavypy/` | Git submodule — waveform generator (from GabrielJuliao/wavypy) | |
| `tests/` | pytest suite (auth, config, converter, downloader, freqblog, history, key_detection, models, quality, search, stats, tagger) | [[Development Setup]] |

## `frontend/src/`

| File | Responsibility | Note |
|------|----------------|------|
| `main.tsx` | React entry point | |
| `App.tsx` | Root component, view router, keyboard shortcuts, WS wiring | |
| `api.ts` | Typed REST client + all TypeScript interfaces | [[Frontend api]] |
| `index.css` | Tailwind + custom styles (DJ filter bar, badges, animations) | |
| `context/AppContext.tsx` | Global state via useReducer + WS message handler | [[Frontend AppContext]] |
| `hooks/useWebSocket.ts` | Auto-reconnecting WebSocket hook | [[Frontend useWebSocket]] |
| `components/AuthGate.tsx` | OAuth device-link UI (shows URL + code) | [[Components]] |
| `components/NavBar.tsx` | Navigation tabs + settings gear icon | |
| `components/SearchView.tsx` | Search header, genre selector, filter bar, results, "Load More" | |
| `components/QueueView.tsx` | Download queue with live progress bars | |
| `components/HistoryView.tsx` | History list with re-download + open-folder | |
| `components/StatsView.tsx` | Device-wide stats dashboard | |
| `components/SettingsPanel.tsx` | Slide-out settings drawer | |
| `components/ToastContainer.tsx` | Download notification toasts | |
| `components/AudioPlayerFooter.tsx` | Canvas tri-band waveform preview player | |
| `components/ArtistView.tsx` | Artist detail view (top tracks + albums) | |

## `docs/`

Design specs and implementation plans, organized under `docs/superpowers/`:
- `specs/` — Design documents per feature (see [[Design Specs]])
- `plans/` — Step-by-step implementation plans (see [[Design Specs]])

## `handoff/`

Session handoff documents capturing feature completion state. See [[Work Log]].

## Build/Config files

| File | Purpose |
|------|---------|
| `frontend/vite.config.ts` | Dev server `:3000`, `/api` + `/ws` proxy to `:8000` | [[Frontend Vite Config]] |
| `frontend/package.json` | Scripts: `dev`, `build` (`tsc && vite build`), `preview`, `test` (vitest) |
| `frontend/tailwind.config.*` | Tailwind theme + content globs |
| `frontend/postcss.config.*` | PostCSS with tailwindcss + autoprefixer |
