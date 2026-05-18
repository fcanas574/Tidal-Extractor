# TidalExtractor — Design Spec

## Overview

Web-based Tidal music downloader with Python backend and React frontend. Downloads songs, playlists, and albums at user-selected quality with post-download bitrate verification to solve the issue of tracks being delivered at lower quality than advertised (128-160kbps instead of lossless).

## Architecture

Three-layer architecture: React SPA → FastAPI → Download Engine

### React Frontend (localhost:3000)
- Search & Browse screen
- Download Queue screen with real-time progress
- Settings screen (quality, format, output directory, auth status)
- Communicates via REST + WebSocket

### FastAPI Backend (localhost:8000)
- REST endpoints for auth, search, queue, settings, history
- WebSocket for live download progress and quality updates
- Orchestrates download pipeline

### Download Engine
- tidalapi for stream URLs and metadata
- ffprobe for bitrate verification
- ffmpeg for format conversion
- mutagen for metadata tagging

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Download approach | Two-phase fetch with quality fallback | Empirically verifies actual bitrate; falls back gracefully |
| Frontend | React SPA | Rich interactive UI with real-time WebSocket progress |
| Backend | FastAPI | Async-native, built-in WebSocket, concurrent-ready |
| Auth | OAuth device link flow | No password handling, secure, user-friendly |
| Users | Single user | Personal project, simplifies architecture |
| Queue | Sequential | Avoids Tidal rate limiting |
| Formats | User-selectable (FLAC, MP3, M4A) | Storage management flexibility for DJs |
| Metadata | Extended (artist, title, album, track#, cover, genre, year, label, ISRC, BPM, key) | DJ-friendly |
| File organization | Flat for singles, folder for playlists/albums | Simple with sensible grouping |
| Verification | Built-in bitrate check (ffprobe) | Detects quality discrepancies post-download |

## Download Pipeline — Approach C: Two-Phase Fetch with Quality Fallback

### Phase 1: Quality Discovery (once per session)
1. On first download, probe quality presets top-down: `HI_RES` → `LOSSLESS` → `HIGH` → `NORMAL`
2. Request stream URL at each preset via tidalapi
3. Download first ~500KB of the stream (enough for ffprobe to read codec headers and bitrate)
4. Run ffprobe on the partial file to check actual bitrate
5. Compare against expected thresholds:
   - FLAC: ~900+ kbps
   - M4A 320kbps
   - MP3 320kbps
   - MP3 128kbps
6. Use the first preset that delivers expected bitrate
7. Cache the winning preset for the rest of the session

### Phase 2: Download & Process (per track)
1. **Fetch stream** — Request URL at cached quality preset via tidalapi
2. **Download to temp** — Stream to `.tmp` file, report progress via WebSocket
3. **Verify quality** — ffprobe the temp file, compare bitrate against expected range
4. **Convert format** — If user wants MP3/M4A, transcode via ffmpeg (skip if FLAC requested and source is FLAC)
5. **Tag metadata** — Embed extended metadata via mutagen (artist, title, album, track#, cover art, genre, year, label, ISRC, BPM, key)
6. **Move to output** — Rename from temp, place in correct directory, log to SQLite

## Error Handling

| Scenario | Response |
|----------|----------|
| All quality presets fail | Mark as failed in queue, show error with details, offer retry |
| Format conversion fails | Keep original FLAC, log error, notify user |
| Download interrupted | Delete partial .tmp file, re-queue automatically |
| Token expires mid-download | Refresh OAuth token, resume current download |
| Disk full | Pre-flight disk space check before download, warn user |
| Track unavailable | Skip with reason, continue queue, log to history |

## Frontend Design

### Screens
1. **Search & Browse** — search bar, track/album/playlist tab filters, result cards with metadata and one-click add-to-queue
2. **Download Queue** — sequential list with live progress bars, quality preset badge, status (queued/downloading/complete/failed), cancel button
3. **Settings** — default quality, default format, output directory, OAuth connection status

### Component Tree
```
App
├── AuthGate (OAuth device link flow, blocks until authenticated)
├── NavBar (Search | Queue | Settings tabs)
├── SearchView
│   ├── SearchBar
│   ├── ResultsList (track/album/playlist cards)
│   └── ItemActions (download, add to queue)
├── QueueView
│   ├── QueueItem (progress bar, status, cancel)
│   └── QualityIndicator (detected preset badge)
└── SettingsView
    ├── AuthStatus (connected account info)
    ├── QualityDefaults
    └── OutputConfig
```

State management: React Context + useReducer (sufficient for single-user app, no external state library).

## API Design

### REST Endpoints
- `POST /auth/device-link` — initiate OAuth device link flow
- `GET /auth/status` — check auth state
- `GET /search?q=&type=` — search tracks/albums/playlists
- `POST /queue/add` — add item to download queue
- `GET /queue` — list current queue
- `DELETE /queue/{id}` — remove/cancel queue item
- `GET /history` — download history
- `GET /settings` — get settings
- `PUT /settings` — update settings

### WebSocket (`/ws`)
```json
{"type": "progress", "id": "...", "pct": 45, "bytes": 4200000, "total": 9800000}
{"type": "quality", "id": "...", "preset": "LOSSLESS", "bitrate": 1011}
{"type": "complete", "id": "...", "path": "/Music/track.flac", "size": 27000000}
{"type": "error", "id": "...", "reason": "all_quality_presets_failed"}
{"type": "queue_update", "items": [...]}
```

## Data Storage

- **SQLite** — download queue, history, quality preset cache per session
- **YAML config** (`config.yaml`) — default quality, default format, output directory
- **Filesystem** — downloaded tracks, temp conversion files, OAuth token cache

## Project Structure

```
TidalExtractor/
├── backend/
│   ├── main.py          # FastAPI app entry point
│   ├── auth.py          # OAuth device link flow
│   ├── search.py        # Tidal search endpoints
│   ├── downloader.py    # Download orchestrator + sequential queue
│   ├── quality.py       # Quality probe + verification (ffprobe)
│   ├── tagger.py        # Metadata embedding (mutagen)
│   ├── converter.py     # Format conversion (ffmpeg)
│   ├── models.py        # SQLite models (queue, history, cache)
│   └── ws.py            # WebSocket manager
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── AuthGate.tsx
│   │   │   ├── NavBar.tsx
│   │   │   ├── SearchView.tsx
│   │   │   ├── QueueView.tsx
│   │   │   └── SettingsView.tsx
│   │   └── hooks/
│   │       └── useWebSocket.ts
│   └── package.json
├── requirements.txt
└── config.yaml
```

## Testing

- **Backend**: pytest for download pipeline, quality probe, metadata tagging (mocked tidalapi, real ffprobe/mutagen)
- **Frontend**: Vitest + React Testing Library for components
- **Manual validation**: Compare downloaded track bitrates against FakinTheFunk results

## Dependencies

### Backend (Python)
- fastapi, uvicorn
- tidalapi
- ffmpeg-python (ffmpeg wrapper)
- mutagen (metadata tagging)
- websockets
- aiosqlite (async SQLite)
- pyyaml

### Frontend (Node)
- react, react-dom
- typescript
- Vite (build tool)
- TailwindCSS (styling)

### System
- ffmpeg + ffprobe (must be installed on host)
