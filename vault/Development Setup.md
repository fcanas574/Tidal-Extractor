# Development Setup

How to run, build, and test TidalExtractor locally.

**See:** [[Tech Stack]] · [[Configuration]] · [[Frontend Vite Config]]

## Prerequisites

- **Python 3.13+** (uses the `audioop_stub` shim for 3.13 compat — see [[Backend audioop_stub]])
- **Node.js 18+**
- **ffmpeg & ffprobe** — for conversion + bitrate verification
  ```bash
  brew install ffmpeg          # macOS
  sudo apt install ffmpeg      # Ubuntu/Debian
  ```
- **A Tidal account** (Free, HiFi, or HiFi Plus)
- **FreqBlog API key** (optional, in `.env` — enables fast key lookups)

## First-Time Setup

```bash
git clone --recurse-submodules <repo>
cd TidalExtractor

# Python deps
pip3 install -r requirements.txt

# Frontend deps
cd frontend && npm install && cd ..

# Optional: FreqBlog key
echo "FREQBLOG_API_KEY=your-key" > .env
```

> If you forgot `--recurse-submodules`, run `git submodule update --init --recursive` to fetch `backend/wavypy`.

## Running (two terminals)

### Backend (terminal 1)
```bash
# From project root:
python3 -m uvicorn backend.main:app --reload --port 8000
```
- Runs on `http://localhost:8000`
- `--reload` restarts on Python file changes
- On startup: inits DB, cleans tmp files, loads saved Tidal session if present

### Frontend (terminal 2)
```bash
cd frontend
npm run dev
```
- Runs on `http://localhost:3000`
- Proxies `/api` → `:8000` and `/ws` → `:8000` (see [[Frontend Vite Config]])

### Open the app
Navigate to `http://localhost:3000`. On first visit you'll be prompted to link your Tidal account via OAuth device flow.

## Testing

### Backend (pytest)
```bash
cd TidalExtractor
python3 -m pytest backend/tests/ -v
```

Test files (`backend/tests/`):
| File | Covers |
|------|--------|
| `test_auth.py` | AuthManager |
| `test_config.py` | AppConfig load/save |
| `test_converter.py` | convert_format |
| `test_downloader.py` | DownloadOrchestrator |
| `test_freqblog_api.py` | FreqBlog client |
| `test_history.py` | history CRUD |
| `test_key_detection.py` | Camelot map, file_hash, detect_key |
| `test_models.py` | Database CRUD |
| `test_quality.py` | get_bitrate, thresholds |
| `test_search.py` | search, scoring, URL parsing |
| `test_stats.py` | stats increment |
| `test_tagger.py` | tag_file per format |

> Note: `test_key_detection.py::test_detect_key_mocked` has a known failure (librosa mock issue) — unrelated to the Camelot logic which passes.

### Frontend (vitest)
```bash
cd frontend
npm test
```
Uses vitest + @testing-library/react + jsdom.

## Building the Frontend

```bash
cd frontend
npm run build     # tsc && vite build → dist/
npm run preview   # serve the production build locally
```

## Database

The active DB is `tidal_extractor.db` (SQLite, WAL mode). Sidecar files:
- `tidal_extractor.db-shm` — shared memory
- `tidal_extractor.db-wal` — write-ahead log

> ⚠️ `tidal.db` (0 bytes) also exists at root but is **not** used by the app. See [[Gotchas & Traps]].

To reset state: stop the server, delete `tidal_extractor.db*`, restart (tables recreate via `CREATE IF NOT EXISTS`).

## Common Dev Tasks

| Task | How |
|------|-----|
| Change default output dir | Edit `config.yaml` or use the Settings panel |
| Re-authenticate Tidal | Settings → Logout, then re-link |
| Clear download queue | Queue tab → "Clear All" |
| Clear all history/stats | Delete the DB file and restart |
| See FreqBlog hit rate | `GET /freqblog/stats` |

## See Also

- [[Tech Stack]] · [[Configuration]] · [[Frontend Vite Config]] · [[Gotchas & Traps]]
