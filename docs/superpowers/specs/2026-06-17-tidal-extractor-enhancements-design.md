# TidalExtractor Enhancements Design Spec

**Date:** 2026-06-17
**Scope:** Bug fix + three new features for TidalExtractor
**Author:** Claude (issue #design-discussion)
**Status:** Approved

---

## 1. Executive Summary

This spec covers four interrelated changes to TidalExtractor:
1. **Fix stale `.tmp` file cleanup** — ensure failed/cancelled downloads always remove partial files.
2. **History View tab** — surface the existing `history` SQLite table in the UI with re-download and open-folder actions.
3. **Stats Dashboard** — device-wide persistent stats (tracks, bytes, quality breakdown) that survive Tidal account re-authentication.
4. **Camelot Key Detection** — post-download musical key analysis via chroma features, mapped to Camelot Wheel notation, embedded in file metadata.

All features remain single-threaded (sequential downloads only) to avoid Tidal IP bans.

---

## 2. Section 1: `.tmp` Cleanup (Sequential Download Safety)

### Problem
`download_track()` in `backend Namenam=backend/downloader.py` leaves a `.tmp` partial file when a download fails or is cancelled. The cleanup in `finally` is not guaranteed to execute in all paths.

### Solution
1. **Guaranteed cleanup**: Wrap the download stream transfer in a `try/finally` block that always `os.unlink(tmp_path)`.
2. **Startup sweep**: On FastAPI startup (`lifespan`), scan the `output_dir` for `.tmp` files and remove them.
3. **Cancellation safety**: Use a simple flag check in the main loop so that stopping the orchestrator doesn't leave dangling temp files mid-transfer.

### Files changed
- `backend/downloader.py` — add `try/finally` around the `tmp_path` write
- `backend/main.py` — startup sweep (already present in `_cleanup_tmp_files`, verify it's robust)

---

## 3. Section 2: History View (Frontend + Backend)

### Backend

New and existing endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/history` | Paginated history list (add `offset`/`limit` params) |
| `POST` | `/history/re-download` | Re-queue a history item with same quality/format |
| `GET`  | `/history/file-path` | Return `file_path` for a given history ID |

**Database changes**: None — `history` table already exists.

### Frontend

- New tab **"History"** added to `NavBar` (third tab: Search, Queue, **History**).
- Shows a table with columns:
  - **Title / Artist**
  - **Quality / Format**
  - **File Size**
  - **Download Date**
  - **Actions**: *Re-download*, *Open Folder*, *Delete from history*
- **Re-download** button creates a new `queue` entry with the same `tidal_id`, `quality`, `format`.
- **Open Folder** triggers browser OS file open (or shell if electron) — for now, frontend opens a `file://` URL or copies path.

### Key decision
History is **account-agnostic** — the `history` table stores no Tidal user identifier. This means switching accounts keeps history visible. This is intentional and documented in the README.

---

## 4. Section 3: Stats Dashboard (Device-Wide)

### Database

Create new table `device_stats`:

```sql
CREATE TABLE IF NOT EXISTS device_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Counter keys:
- `total_tracks`
- `total_albums`
- `total_playlists`
- `total_bytes`
- `quality_hi_res`
- `quality_lossless`
- `quality_320k`
- `quality_96k`

Create helper methods in `backend/models.py`:
- `Molecule model_increment_stat(self, key, amount=1)`
- `Molecule model_get_stat(self, key)`
- `Molecule model_get_all_stats(self)`

### Backend

- `GET /stats` → returns aggregated stats from `device_stats` table.
- On every successful download in `downloader.py`, increment the relevant counters (track vs album, quality used, file size added).

### Frontend

- New **"Stats"** tab in `NavBar`.
- Simple cards:
  - Total tracks downloaded
  - Total storage used (human-readable: MB / GB)
  - Breakdown: Hi-Res / Lossless / 320k / 96k
- CSS-only bar chart for quality distribution.

### Key decision
Stats are **device-scoped** and survive Tidal account re-authentication. This is front-page UI copy: "Stats are stored device-wide and are not tied to your Tidal account."

---

## 5. Section 4: Camelot Key Detection

### Goal
Detect the musical key **from the audio waveform** using chroma analysis, then translate to Camelot Wheel notation. This is independent of Tidal's `key` metadata.

### Backend

**New module: `backend/key_detection.py`**

```python
def detect_key(audio_path: str) -> dict:
    """
    Returns {"key": "Am", "camelot": "1A", "confidence": 0.87}
    """
```

**Algorithm (Approach A — pure Python / librosa)**
1. Load audio with `librosa`.
2. Compute chroma features.
3. Apply key profile matching (Krumhansl-Schmuckler or Temperley) to estimate key.
4. Map estimated key to **Camelot Wheel notation**:

| Key | Camelot | | Key | Camelot |
| --- | --- | --- | --- | --- |
| A♭ minor | 1A | | A♭ major | 1B |
| E♭ minor | 2A | | B major | 2B |
| B♭ minor | 3A | | F# major | 3B |
| ... (full mapping in implementation) ...
| G major | 7B | | E major | 5B |

**Table: `key_cache`**
```sql
CREATE TABLE IF NOT EXISTS key_cache (
    file_hash TEXT PRIMARY KEY,
    key TEXT,
    camelot TEXT,
    confidence REAL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Endpoint**
- `GET /key/detect?path=<file_path>` → runs detection or returns cached result.

**Integration point**
- Run `detect_key()` **after** `tag_file()` in the download pipeline (`downloader.py`).
- Embed both `key` and `camelot` into file metadata:
  - FLAC: VORBIS_COMMENT `KEY`, `CAMELOT`
  - MP3: ID3 `TKEY`, `TXXX:CAMELOT`
  - M4A: `----:com.apple.iTunes:key`, `----:com.apple.iTunes:camelot`

### Frontend

- Show a small **Camelot badge** (e.g., `1A`) in the History list item.
- Show a tooltip/hint: `1A → 1B or 8A` (compatibility for DJ mixing) on hover.
- Optionally filter History by Camelot key (future scope).

---

## 6. Architecture Overview

```
┌─────────────────────────────────────────────┐
│              Frontend (React + Vite)          │
│   Search │ Queue │ History │ Stats │ Settings│
│                                               │
│   History: table + re-download + open-folder  │
│   Stats:   cards + bar chart (device-wide)    │
│   Player:  Camelot badge on preview           │
└──────────────┬────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│               FastAPI Backend                  │
│  ┌─────────────┐  ┌──────────────────┐      │
│  │  .tmp fix   │  │  Camelot engine  │      │
│  │  + sweep  │  │  (librosa)       │      │
│  └─────────────┘  └──────────────────┘      │
│                                               │
│  /history → paginated list                    │
│  /history/re-download → re-queue              │
│  /stats   → device_stats aggregation          │
│  /key/detect → detect or cache                │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              SQLite (aiosqlite)                │
│                                               │
│  history     (exists)  account-agnostic      │
│  queue       (exists)  download queue          │
│  device_stats  NEW     device-wide counters  │
│  key_cache     NEW     file_hash → key/camelot│
└─────────────────────────────────────────────┘
```

---

## 7. Files Changed / New

### Backend
| File | Change |
|------|--------|
| `backend/downloader.py` | Add `.tmp` finally; call `key_detection.detect_key()` after `tag_file()`; increment `device_stats` on success |
| `backend/key_detection.py` | **New** — chroma analysis + Camelot mapping |
| `backend/models.py` | Add `increment_stat`, `get_stat`, `get_all_stats`, `key_cache` CRUD |
| `backend/main.py` | New endpoints: `/history/paginated`, `/stats`, `/key/detect` |
| `backend/search.py` | No change |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Add `history` and `stats` tabs |
| `frontend/src/components/NavBar.tsx` | Add tab buttons |
| `frontend/src/components/HistoryView.tsx` | **New** — history table + actions |
| `frontend/src/components/StatsView.tsx` | **New** — stats dashboard cards |
| `frontend/src/api.ts` | Add new API methods |

### Docs
| File | Change |
|------|--------|
| `README.md` | Update features list |
| `requirements.txt` | Add `librosa` and `numpy` (if not already) |

---

## 8. Testing Plan

- **Unit tests** for `key_detection.py`: feed known-key audio files, assert Camelot output.
- **Integration test** for stats: download a track, verify `device_stats` incremented.
- **Manual test** for `.tmp` cleanup: abort a download mid-way, verify `.tmp` removed.
- **Manual test** for history re-download: click re-download, verify new queue item with same settings.

---

## 9. Open Questions / None

All questions resolved during brainstorming. No remaining ambiguities.

---

## 10. Approval

- [x] Section 1: `.tmp` Cleanup — Approved
- [x] Section 2: History View — Approved
- [x] Section 3: Stats Dashboard — Approved
- [x] Section 4: Camelot Key Detection — Approved
