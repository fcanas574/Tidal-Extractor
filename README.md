# TidalExtractor

A web-based Tidal music downloader with verified audio quality. Downloads tracks, albums, and playlists at the highest quality your subscription supports, with automatic bitrate verification to ensure you get what you pay for.

## Features

- **Quality-first downloads** — Two-phase fetch with quality fallback: probes presets top-down (HiRes Lossless → Lossless → High → Normal), downloads a sample, and verifies actual bitrate with ffprobe before committing
- **DJ Search Filters** — Filter tracks by BPM range (60-200), Camelot key (1A-12B), harmonic compatibility (±1 + relative major/minor), and curated genres (House, Techno, Trance, Drum & Bass, etc.)
- **Track, album, and playlist support** — Search and download individual tracks, full albums, or entire playlists
- **Format conversion** — Convert to FLAC, MP3 (320kbps), or M4A/AAC (320kbps) via ffmpeg
- **Full metadata tagging** — Embeds title, artist, album, genre, year, label, ISRC, BPM, key, and cover art using mutagen
- **Track preview with tri-band waveform** — Click-to-preview any search result with a Rekordbox-style 3-band waveform (lows/mids/highs), generated from actual audio analysis via wavypy
- **Real-time progress** — WebSocket-powered download progress with toast notifications
- **Session persistence** — Tidal OAuth session saved locally so you don't re-auth every launch
- **Quality cache** — Probed quality presets are cached per session to avoid redundant checks
- **Download History** — Browse all past downloads with re-download and open-folder actions
- **Device-wide Stats** — Track total tracks, storage used, and quality breakdown across all sessions
- **Camelot Key Detection** — Analyze audio waveform to detect musical key in Camelot notation, independent of Tidal metadata

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13+, FastAPI, tidalapi 0.8.11, SQLite, ffmpeg, mutagen, numpy, scipy, wavypy |
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

## DJ Filters

For DJs preparing sets, the Search tab includes harmonic mixing tools:

| Filter | Description |
|--------|-------------|
| **BPM Range** | Set minimum and maximum tempo (60-200 BPM) |
| **Camelot Key** | Select key (1A-12A, 1B-12B) to filter by exact match |
| **Compatible** | Toggle to include harmonically compatible keys (±1 number + relative major/minor) |
| **Genre** | Browse by genre without entering a search query (House, Techno, Trance, Drum & Bass, etc.) |

**Example workflow:** Select "House" from the genre dropdown, set BPM to 120-128, choose "8A" with Compatible enabled to find all tracks in 7A, 8A, 9A, or 8B — perfect for harmonic mixing.

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
│   ├── waveform.py      # wavypy integration, tri-band audio analysis
│   ├── audioop_stub.py  # Python 3.13+ audioop compatibility shim
│   ├── wavypy/          # wavypy waveform generator (submodule)
│   └── tests/           # pytest test suite
├── frontend/
│   └── src/
│       ├── api.ts                  # Typed REST client
│       ├── App.tsx                 # Root component
│       ├── context/AppContext.tsx  # Global state (useReducer)
│       ├── hooks/useWebSocket.ts  # Auto-reconnecting WS hook
│       └── components/
│           ├── AuthGate.tsx          # OAuth device-link UI
│           ├── NavBar.tsx            # Navigation + settings icon
│           ├── SearchView.tsx        # Search + results
│           ├── QueueView.tsx         # Download queue + progress
│           ├── SettingsPanel.tsx     # Slide-out settings drawer
│           ├── ToastContainer.tsx    # Download notifications
│           └── AudioPlayerFooter.tsx # Canvas tri-band waveform player
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
