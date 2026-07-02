# Tech Stack

## Backend (Python 3.13+)

| Concern | Tech | Notes |
|---------|------|-------|
| Web framework | **FastAPI** 0.115.6 | Async, lifespan-managed, Pydantic models |
| ASGI server | **uvicorn[standard]** 0.34.0 | `--reload` in dev |
| Tidal client | **tidalapi** 0.8.11 | OAuth device flow, session persistence |
| Database | **SQLite** via **aiosqlite** 0.20.0 | WAL mode, async access |
| Audio I/O | **ffmpeg** + **ffprobe** | Conversion + bitrate verification (subprocess) |
| Metadata | **mutagen** 1.47.0 | FLAC/MP3/M4A tagging, key/Camelot embedding |
| Config | **PyYAML** 6.0.2 | `config.yaml` at project root |
| HTTP client | **httpx** 0.28.1 + **requests** 2.32.3 | Async stream downloads; cover art fetch |
| Audio analysis | **librosa** ≥0.10.1, **numpy** 2.2.6, **scipy** 1.15.3 | Chroma features, tempo estimation |
| Waveform | **pydub** 0.25.1 + **wavypy** (git submodule) | Tri-band waveform generation |
| Env loading | **python-dotenv** | Loads `FREQBLOG_API_KEY` from `.env` |
| Testing | **pytest** 8.3.4, **pytest-asyncio** 0.24.0 | `backend/tests/` |

## Frontend (React 18 + TypeScript)

| Concern | Tech | Notes |
|---------|------|-------|
| UI library | **React** 18.3 | Function components, hooks |
| Language | **TypeScript** 5.6 | Strict typing for API + state |
| Bundler | **Vite** 6 | Dev server on `:3000`, proxies `/api` + `/ws` → `:8000` |
| Styling | **Tailwind CSS** 3.4 + PostCSS + autoprefixer | Utility-first |
| State | **useReducer + Context** | Global `AppContext`, no Redux |
| Realtime | Native **WebSocket** | Auto-reconnect hook |
| Testing | **Vitest** 2.1 + @testing-library/react | `npm test` |

## Realtime

- **WebSocket (native)** — FastAPI `@app.websocket("/ws")`, custom `WebSocketManager` for broadcast

## External Services

- **Tidal API** — via tidalapi library (OAuth device flow)
- **FreqBlog API** — `api.freqblog.com/lookup` for BPM/key/Camelot metadata (requires `FREQBLOG_API_KEY`)

## Tooling & Submodules

- **wavypy** — git submodule at `backend/wavypy/` (from GabrielJuliao/wavypy), used for waveform generation
- **audioop_stub** — `backend/audioop_stub.py`, compatibility shim for Python 3.13+ (removes the `audioop` stdlib module)

## Dev Ports

| Service | Port |
|---------|------|
| Backend (uvicorn) | 8000 |
| Frontend (vite) | 3000 |
| Frontend (alt) | 5173 |

CORS allows origins `localhost:3000` and `localhost:5173`.
