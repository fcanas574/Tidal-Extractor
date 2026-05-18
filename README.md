# TidalExtractor

A web-based Tidal music downloader with verified audio quality. Downloads tracks, albums, and playlists at the highest quality your subscription supports, with automatic bitrate verification to ensure you get what you pay for.

## Features

- **Quality-first downloads** — Two-phase fetch with quality fallback: probes presets top-down (HiRes Lossless → Lossless → High → Normal), downloads a sample, and verifies actual bitrate with ffprobe before committing
- **Track, album, and playlist support** — Search and download individual tracks, full albums, or entire playlists
- **Format conversion** — Convert to FLAC, MP3 (320kbps), or M4A/AAC (320kbps) via ffmpeg
- **Full metadata tagging** — Embeds title, artist, album, genre, year, label, ISRC, BPM, key, and cover art using mutagen
- **Real-time progress** — WebSocket-powered download progress with toast notifications
- **Session persistence** — Tidal OAuth session saved locally so you don't re-auth every launch
- **Quality cache** — Probed quality presets are cached per session to avoid redundant checks

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, tidalapi 0.8.11, SQLite, ffmpeg, mutagen |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Real-time | WebSocket (native) |

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **ffmpeg & ffprobe** — required for format conversion and bitrate verification
  ```bash
  # macOS
  brew install ffmpeg

  # Ubuntu/Debian
  sudo apt install ffmpeg
  ```
- **A Tidal account** (Free, HiFi, or HiFi Plus)

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/TidalExtractor.git
cd TidalExtractor

# Python dependencies
pip3 install -r requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Run the backend

From the **project root**:

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

### 3. Run the frontend

In a separate terminal:

```bash
cd frontend && npm run dev
```

### 4. Open the app

Navigate to [http://localhost:3000](http://localhost:3000). You'll be prompted to link your Tidal account via OAuth device flow on first visit.

## Configuration

Settings are accessible via the gear icon in the navigation bar:

| Setting | Options | Default |
|---------|---------|---------|
| Default Quality | HiRes Lossless, Lossless, High (320k), Normal (96k) | Lossless |
| Default Format | FLAC, MP3, M4A | FLAC |
| Output Directory | Any local path | `~/Music/TidalDownloads` |

Configuration is also stored in `config.yaml` at the project root and can be edited directly.

## Architecture

```
TidalExtractor/
├── backend/
│   ├── main.py          # FastAPI app, REST endpoints, WebSocket
│   ├── auth.py          # Tidal OAuth device-link flow
│   ├── search.py        # Search, album/playlist track listing
│   ├── downloader.py    # Download orchestrator, quality fallback
│   ├── quality.py       # ffprobe bitrate verification, presets
│   ├── converter.py     # ffmpeg format conversion
│   ├── tagger.py        # mutagen metadata embedding
│   ├── models.py        # SQLite database (queue, history, cache)
│   ├── config.py        # YAML config loader/saver
│   ├── ws.py            # WebSocket broadcast manager
│   └── tests/           # pytest test suite
├── frontend/
│   └── src/
│       ├── api.ts                  # Typed REST client
│       ├── App.tsx                 # Root component
│       ├── context/AppContext.tsx  # Global state (useReducer)
│       ├── hooks/useWebSocket.ts  # Auto-reconnecting WS hook
│       └── components/
│           ├── AuthGate.tsx        # OAuth device-link UI
│           ├── NavBar.tsx          # Navigation + settings icon
│           ├── SearchView.tsx      # Search + results
│           ├── QueueView.tsx       # Download queue + progress
│           ├── SettingsPanel.tsx   # Slide-out settings drawer
│           └── ToastContainer.tsx  # Download notifications
├── config.yaml          # User settings
├── requirements.txt     # Python dependencies
└── README.md
```

## Download Pipeline

```
Search → Add to Queue → Probe Quality (top-down fallback)
  → Download ~(500KB sample) → ffprobe verify bitrate
  → If bitrate meets threshold → Full download at that preset
  → If not → Try next lower preset → Repeat
  → Convert format (if not FLAC) → Tag metadata → Complete
```

## Running Tests

```bash
# Backend tests
cd TidalExtractor
pip3 install pytest pytest-asyncio
python3 -m pytest backend/tests/ -v

# Frontend tests
cd frontend
npm test
```

## Notes

- **FakinTheFunk misreports FLAC bitrate** — It samples instantaneous variable bitrate rather than overall average. A genuine 24-bit FLAC at ~1,790 kbps may show as 128-160 kbps in FakinTheFunk. This app uses ffprobe for accurate verification.
- **HiRes Lossless requires PKCE auth** — LOSSLESS and below use the standard BTS manifest. HiRes uses a different manifest type that requires PKCE-enabled OAuth.
- **Single-user design** — The app is designed for personal use with one Tidal account at a time.

## License

MIT
