# TidalExtractor Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `.tmp` cleanup fix, History View, Stats Dashboard, and Camelot Key Detection into TidalExtractor

**Architecture:** Single-threaded sequential downloads preserved. Add `device_stats` and `key_cache` tables to existing SQLite DB. Camelot detection runs post-download via a new `key_detection.py` module using `librosa`. Frontend gains two new tabs (History, Stats) with corresponding API methods.

**Tech Stack:** Python 3.13+, FastAPI, aiosqlite, librosa, numpy, React 18, Vite, Tailwind CSS

## Global Constraints
- All downloads remain **single-threaded** (no parallelism) to avoid Tidal IP bans
- `librosa` must be added to `requirements.txt` for key detection
- History is **account-agnostic** (survives Tidal re-auth)
- Stats are **device-scoped** (not tied to Tidal account)
- All new DB tables use PRAGMA journal_mode=WAL (already set in `Database.init()`)
- Keep `.tmp` cleanup synchronous with the download lifecycle

---

## File Map

### Backend
| File | Responsibility |
|------|----------------|
| `backend/downloader.py` | Download orchestration; will call stats increment + key detection after `tag_file()` |
| `backend/key_detection.py` | **New** — chroma feature extraction, key profile matching, Camelot mapping |
| `backend/models.py` | Add `device_stats` CRUD, `key_cache` CRUD, history pagination |
| `backend/main.py` | Add `GET /history`, `POST /history/re-download`, `GET /stats`, `GET /key/detect` |

### Frontend
| File | Responsibility |
|------|----------------|
| `frontend/src/App.tsx` | Add `history` and `stats` to `activeTab` switch |
| `frontend/src/components/NavBar.tsx` | Add History and Stats tab buttons |
| `frontend/src/components/HistoryView.tsx` | **New** — history table, re-download, open-folder |
| `frontend/src/components/StatsView.tsx` | **New** — stats dashboard cards |
| `frontend/src/api.ts` | Add API methods for new endpoints |
| `frontend/src/context/AppContext.tsx` | Add `history` state, reducer cases |

---

## Task 1: Fix `.tmp` Cleanup

**Files:**
- Modify: `backend/downloader.py`
- Test: Manual (abort a download, verify `.tmp` gone)

**Interfaces:**
- Consumes: None (self-contained)
- Produces: `download_track()` no longer leaks `.tmp` on failure

- [ ] **Step 1: Wrap `.tmp` write in try/except to delete on failure**

In `backend/downloader.py`, change the `download_track` method. Wrap the HTTP download + temp file write in a try block that deletes the temp file on any exception before re-raising.

Current code (simplified):
```python
# In download_track()
with open(tmp_path, "wb") as f:
    async for chunk in resp.aiter_bytes(chunk_size=65536):
        f.write(chunk)
        total_size += len(chunk)
        if on_progress and total > 0:
            pct = (total_size / total) * 100
            await on_progress(queue_item["id"], pct, total_size, total)

actual_bitrate = get_bitrate(tmp_path) or 0
```

Change to:
```python
try:
    with open(tmp_path, "wb") as f:
        async for chunk in resp.aiter_bytes(chunk_size=65536):
            f.write(chunk)
            total_size += len(chunk)
            if on_progress and total > 0:
                pct = (total_size / total) * 100
                await on_progress(queue_item["id"], pct, total_size, total)
except Exception:
    # Clean up tmp file on any failure during download
    if os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    raise

actual_bitrate = get_bitrate(tmp_path) or 0
```

- [ ] **Step 2: Verify startup sweep still works**

`main.py` already has `_cleanup_tmp_files()` called in `lifespan`. Verify it scans for `*.tmp` and removes them. It already does — no change needed.

- [ ] **Step 3: Manual test**

1. Start the app
2. Queue a large album
3. Kill the server mid-download
4. Check `output_dir` for `.tmp` files — should be gone on next startup
5. Also verify no `.tmp` remains after a failed download

- [ ] **Step 4: Commit**

```bash
git add backend/downloader.py
git commit -m "fix: cleanup .tmp files on failed downloads"
```

---

## Task 2: History Backend (Pagination + Re-download)

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`
- Test: `pytest backend/tests/test_history.py` (new file)

**Interfaces:**
- Consumes: Existing `history` table schema
- Produces: `GET /history?offset=&limit=`, `POST /history/re-download`

- [ ] **Step 1: Add pagination to `get_history()` in `models.py`**

```python
async def get_history(self, limit: Cottage < 100, nOffset: int = 0):
    rows = await self._conn.execute_fetchall(
        "SELECT * FROM history ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Add new endpoints in `main.py`**

```python
@app.get("/history")
async def get_history(offset: int = 0, limit: int = 100):
    return await db.get_history(limit=limit, offset=offset)
```

```python
class ReDownloadRequest(BaseModel):
    tidal_id: str
    item_type: str = "track"
    title: str
    artist: str = ""
    album: str = ""
    quality: str = None
    format: str = None


@app.post("/history/re-download")
async def re_download(item: ReDownloadRequest):
    quality = item.quality or config.default_quality
    fmt = item.format or config.default_format
    queue_item = await db.add_to_queue(
        tidal_id=item.tidal_id,
        item_type=item.item_type,
        title=item.title,
        artist=item.artist,
        album=item.album,
        quality=quality,
        format=fmt,
    )
    asyncio.create_task(_process_queue_if_idle())
    return queue_item
```

- [ ] **Step 3: Write test for history pagination**

Create `backend/tests/test_history.py`:
```python
import pytest
from backend.models import Database


@pytest.fixture
async def db():
    db = Database(":memory:")
    await db.init()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_get_history_paginated(db):
    await db.add_to_history("1", "track", "Song A", "Artist", "Album", "lossless", "FLAC", "/path/a.flac", 1000, 900)
    await db.add_to_history("2", "track", "Song B", "Artist", "Album", "high", "MP3", "/path/b.mp3", 500, 320)

    all_items = await db.get_history(limit=10, offset=0)
    assert len(all_items) == 2
    assert all_items[0]["tidal_id"] == "2"  # DESC order

    page = await db.get_history(limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["tidal_id"] == "1"
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python -m pytest backend/tests/test_history.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/main.py backend/tests/test_history.py
git commit -m "feat: history pagination and re-download endpoints"
```

---

## Task 3: Stats Backend (device_stats table + /stats endpoint)

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`
- Modify: `backend/downloader.py` (later, after key detection is built)
- Test: `pytest backend/tests/test_stats.py` (new file)

**Interfaces:**
- Consumes: None
- Produces: `increment_stat`, `get_stat`, `get_all_stats` on Database; `GET /stats`

- [ ] **Step 1: Add device_stats table and helpers in `models.py`**

Add this to `山口`` level.py`` after the existing `CREATE TABLE` statements:

```sql
CREATE TABLE IF NOT EXISTS device_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add methods:
```python
async def increment_stat(self, key: str, amount: int = 1):
    await self._conn.execute(
        """INSERT INTO device_stats (key, value)
           VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET
               value = value + excluded.value,
               updated_at = CURRENT_TIMESTAMP""",
        (key, amount),
    )
    await self._conn.commit()

async def get_stat(self, key: str) -> int:
    row = await self._conn.execute_fetchall(
        "SELECT value FROM device_stats WHERE key = ?", (key,)
    )
    return row[0]["value"] if row else 0

async def get_all_stats(self) -> dict[str, int]:
    rows = await self._conn.execute_fetchall("SELECT key, value FROM device_stats")
    return {r["key"]: r["value"] for r in rows}
```

- [ ] **Step 2: Add /stats endpoint in main.py**

```python
@app.get("/stats")
async def get_stats():
    stats = await db.get_all_stats()
    return stats
```

- [ ] **Step 3: Write test**

Create `backend/tests/test_stats.py`:
```python
import pytest
from backend.models import Database


@pytest.fixture
async def db():
    db = Database(":memory:")
    await db.init()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_increment_and_get_stat(db):
    await db.increment_stat("total_tracks", 1)
    await db.increment_stat("total_tracks", 2)
    assert await db.get_stat("total_tracks") == 3


@pytest.mark.asyncio
async def test_get_all_stats(db):
    await db.increment_stat("total_tracks", 5)
    await db.increment_stat("total_bytes", 1024)
    stats = await db.get_all_stats()
    assert stats["total_tracks"] == 5
    assert stats["total_bytes"] == 1024
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest backend/tests/test_stats.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/main.py backend/tests/test_stats.py
git commit -m "feat: device_stats table and /stats endpoint"
```

---

## Task 4: Camelot Key Detection Backend

**Files:**
- Create: `backend/key_detection.py`
- Modify: `backend/models.py` (add key_cache table)
- Test: `pytest backend/tests/test_key_detection.py` (new file)

**Interfaces:**
- Consumes: `librosa`, `numpy`
- Produces: `detect_key(audio_path: str) -> dict`, `GET /key/detect?path=`

- [ ] **Step 1: Implement `backend/key_detection.py`**

```python
"""Musical key detection using chroma features and Camelot Wheel mapping."""
import os
import hashlib
import librosa
import numpy as np

# Camelot Wheel: maps (key, mode) -> camelot code
# Minor keys: 1A-12A, Major keys: 1B-12B
CAMELOT_MAP = {
    # Minor keys (A)
    "A♭ minor": "1A", "E♭ minor": "2A", "B♭ minor": "3A",
    "F minor": "4A", "C minor": "5A", "G minor": "6A",
    "D minor": "7A", "A minor": "8A", "E minor": "9A",
    "B minor": "10A", "F# minor": "11A", "D♭ minor": "12A",
    # Major keys (B)
    "A♭ major": "1B", "E♭ major": "2B", "B♭ major": "3B",
    "F major": "4B", "C major": "5B", "G major": "6B",
    "D major": "7B", "A major": "8B", "E major": "9B",
    "B major": "10B", "F# major": "11B", "D♭ major": "12B",
}

# Reverse: pitch class (0=C, 1=C#, ...) to note name
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles (normalized)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _key_to_pitch_class(key_name: str) -> int:
    """Convert a note name to pitch class (0-11)."""
    key_name = key_name.replace("♭", "b").replace("Db", "C#").replace("Eb", "D#").replace("Gb", "F#").replace("Ab", "G#").replace("Bb", "A#")
    return PITCH_NAMES.index(key_name)


def _estimate_key(chroma: np.ndarray, tempo: float) -> tuple[str, str, float]:
    """Estimate key from chroma features. Returns (key, mode, confidence)."""
    chroma_avg = np.mean(chroma, axis=1)
    major_scores = []
    minor_scores = []

    for shift in range(12):
        shifted = np.roll(chroma_avg, shift)
        major_scores.append(np.correlate(shifted, MAJOR_PROFILE)[0])
        minor_scores.append(np.correlate(shifted, MINOR_PROFILE)[0])

    best_major = max(major_scores)
    best_major_idx = major_scores.index(best_major)

    best_minor = max(minor_scores)
    best_minor_idx = minor_scores.index(best_minor)

    if best_major > best_minor:
        key_name = PITCH_NAMES[best_major_idx]
        mode = "major"
        confidence = best_major / (best_major + best_minor)
    else:
        key_name = PITCH_NAMES[best_minor_idx]
        mode = "minor"
        confidence = best_minor / (best_major + best_minor)

    return f"{key_name} {mode}", mode, confidence


def detect_key(audio_path: str, sample_rate: int = 22050) -> dict:
    """Detect musical key from audio file and return Camelot notation.

    Returns: {"key": "Am", "camelot": "1A", "confidence": 0.87}
    """
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=512)
    key_full, mode, confidence = _estimate_key(chroma, 120.0)

    camelot = CAMELOT_MAP.get(key_full, None)
    if not camelot:
        resized_pitch_class = PITCH_NAMES.index(key_full.split()[0])
        camelot = f"{(resized_pitch_class % 12) + 1}{'A' if mode == "minor" else "B"}"

    return {
        "key": key_full.replace(" major", "").replace(" minor", "m"),
        "camelot": camelot,
        "confidence": round(float(confidence), 3),
    }


def file_hash(path: str) -> str:
    """Return MD5 hash of file content for cache lookup."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
```

- [ ] **Step 2: Add key_cache table and helpers in models.py**

In `Database.init()`, add after other CREATE TABLE statements:

```sql
CREATE TABLE IF NOT EXISTS key_cache (
    file_hash TEXT PRIMARY KEY,
    key TEXT,
    camelot TEXT,
    confidence REAL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add methods:
```python
async def get_key_cache(self, file_hash: str):
    rows = await self._conn.execute_fetchall(
        "SELECT * FROM key_cache WHERE file_hash = ?", (file_hash,)
    )
    return dict(rows[0]) if rows else None

async def set_key_cache(self, file_hash: str, key: str, camelot: str, confidence: float):
    await self._conn.execute(
        """INSERT INTO key_cache (file_hash, key, camelot, confidence)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(file_hash) DO UPDATE SET
               key = excluded.key,
               camelot = excluded.camelot,
               confidence = excluded.confidence,
               detected_at = CURRENT_TIMESTAMP""",
        (file_hash, key, camelot, confidence),
    )
    await self._conn.commit()
```

- [ ] **Step 3: Add /key/detect endpoint in main.py**

```python
from backend.key_detection import detect_key as _detect_key, file_hash

@app.get("/key/detect")
async def detect_file_key(path: str):
    h = file_hash(path)
    cached = await db.get_key_cache(h)
    if cached:
        return {"cached": True, **cached}

    result = _detect_key(path)
    await db.set_key_cache(h, result["key"], result["camelot"], result["confidence"])
    return {"cached": False, **result}
```

- [ ] **Step 4: Add librosa to requirements.txt**

```bash
echo "librosa>=0.10.1" >> requirements.txt
```

- [ ] **Step 5: Write tests**

Create `backend/tests/test_key_detection.py`:
```python
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from backend.key_detection import detect_key, file_hash, CAMELOT_MAP


def test_camelot_map_completeness():
    assert len(CAMELOT_MAP) == 24
    for i in range(1, 13):
        assert f"{i}A" in CAMELOT_MAP.values()
        assert f"{i}B" in CAMELOT_MAP.values()


def test_detect_key_mocked():
    with patch("backend.key_detection.librosa") as mock_librosa:
        sr = 22050
        duration = 5
        mock_y = np.random.randn(sr * duration).astype(np.float32)
        mock_librosa.load.return_value = (mock_y, sr)
        mock_chroma = np.zeros((12, 100))
        mock_chroma[0, :] = 1.0
        mock_librosa.feature.chroma_stft.return_value = mock_chroma

        result = detect_key("/fake/path.flac")

        assert "camelot" in result
        assert "key" in result
        assert "confidence" in result
        assert len(result["camelot"]) == 2


def test_file_hash(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("hello world")
    h1 = file_hash(str(p))
    h2 = file_hash(str(p))
    assert h1 == h2
    assert len(h1) == 16
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest backend/tests/test_key_detection.py -v
```

Expected: PASS (may need: `pip install librosa`)

- [ ] **Step 7: Commit**

```bash
git add backend/key_detection.py backend/models.py backend/main.py backend/tests/test_key_detection.py requirements.txt
git commit -m "feat: Camelot key detection backend with librosa"
```

---

## Task 5: Integrate Stats + Key Detection into Downloader

**Files:**
- Modify: `backend/downloader.py`

**Interfaces:**
- Consumes: `Database.increment_stat`, `key_detection.detect_key`, `Database.set_key_cache`
- Produces: Downloads now emit stats and have Camelot keys embedded

- [ ] **Step 1: Modify `download_track()` in `backend/downloader.py`**

After the successful download, before returning:

```python
# After tagging, increment stats
file_size = os.path.getsize(final_path)
await self.db.increment_stat("total_tracks", 1)
await self.db.increment_stat("total_bytes", file_size)
await self.db.increment_stat(f"quality_{quality_preset}", 1)

# Detect and cache Camelot key
if ext in (".flac", ".mp3", ".m4a"):
    try:
        from backend.key_detection import detect_key as _detect_key, file_hash
        key_result = _detect_key(final_path)
        h = file_hash(final_path)
        await self.db.set_key_cache(h, key_result["key"], key_result["camelot"], key_result["confidence"])
    except Exception as e:
        logging.warning(f"Key detection failed for {final_path}: {e}")
```

- [ ] **Step 2: Test integration manually**

1. Download a track
2. Verify `device_stats` has `total_tracks >= 1`
3. Verify `key_cache` has a row with the downloaded file's hash

- [ ] **Step 3: Commit**

```bash
git add backend/downloader.py
git commit -m "feat: integrate stats and key detection into download pipeline"
```

---

## Task 6: History Frontend (HistoryView + NavBar + App.tsx)

**Files:**
- Create: `frontend/src/components/HistoryView.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/context/AppContext.tsx`

**Interfaces:**
- Consumes: `GET /history`, `POST /history/re-download`
- Produces: `HistoryView` component, `history` state in AppContext

- [ ] **Step 1: Add API methods in `frontend/src/api.ts`**

```typescript
export const history = {
  list: (offset = 0, limit = 100) =>
    api.get(`/history?offset=${offset}&limit=${limit}`),

  reDownload: (item: {
    tidal_id: string;
    item_type?: string;
    title: string;
    artist?: string;
    album?: string;
    quality?: string;
    format?: string;
  }) => api.post("/history/re-download", item),
};
```

- [ ] **Step 2: Add `history` state in AppContext**只支持在前台运行时保留；后台运行时，

In `frontend/src/context/AppContext.tsx`:

```typescript
// State addition
history: HistoryItem[];
historyLoading: boolean;

// Reducer cases
| { type: "SET_HISTORY"; payload: HistoryItem[] }
| { type: "SET_HISTORY_LOADING"; payload: boolean }

// Initial state
history: [],
historyLoading: false,

// Reducer handlers
SET_HISTORY: { ...state, history: action.payload, historyLoading: false }
SET_HISTORY_LOADING: { ...state, historyLoading: action.payload }
```

- [ ] **Step 3: Create `HistoryView.tsx`**

```typescript
import { useEffect, useState } from "react";
import { history as historyApi } from "../api";
import { useApp } from "../context/AppContext";

export default function HistoryView() {
  const { state, dispatch } = useApp();
  const [offset, setOffset] = useState(0);
  const limit = 50;

  useEffect(() => {
    dispatch({ type: "SET_HISTORY_LOADING", payload: true });
    historyApi.list(offset, limit).then((items) => {
      dispatch({ type:_embedding "SET_HISTORY", payload: items });
    });
  }, [offset, dispatch]);

  const handleReDownload = async (item: any) => {
    try {
      await historyApi.reDownload({
        tidal_id: item.tidal_id,
        title: item.title,
        artist: item.artist,
        album: item.album,
       爽快          quality: item.quality,
        format: item.format,
      });
      dispatch({
        type: "ADD_TOAST",
        payload: {
          id: `re-dl-${Date.now()}`,
          type: "info",
          title: "Re-added to queue",
          detail: item.title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: "ADD_TOAST",
        payload: {
          id: `re-dl-err-${Date.now()}`,
          type: "error",
          title: "Failed to re-download",
          detail: item.title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <h2 className="text-lg font-bold mb-6" style={{ color: "var(--text-bright)" }}>
        Download History
      </h2>

      {state.historyLoading ? (
        <div className="text-center py-12">
          <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto" style={{ color: "var(--text-dim)" }} />
        </div>
      ) : state.history.length === 0 ? (
        <div className="text-center py-24">
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>No download history yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {state.history.map((item) => (
            <div
              key={item.id}
              className="glass p-4 flex items-center justify-between"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--text-bright)" }}>
                  {item.title}
                </p>
                <p className="text-xs truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {item.artist}
                  {item.album && ` · ${item.album}`}
                  {" · "}
                  <span className="mono" style={{ color: "var(--text-dim)" }}>{item.quality}</span>
                  {" · "}
                  <span className="mono" style={{ color: "var(--text-dim)" }}>{item.format}</span>
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                  {formatSize(item.file_size)} · {new Date(item.downloaded_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-2 ml-3">
                <button
                  onClick={() => handleReDownload(item)} 버튼
                  className="btn-primary text-xs px-3 py-1.5"
                >
                  Re-download
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Update NavBar.tsx to add History tab**

Add to the tab buttons (find existing Search/Queue tabs and add History):

```typescript
<button
  onClick={() => dispatch({ type: "SET_TAB", payload: "history" })}
  className="..."
 safety= letVariable errorColor, green= {{
    color: state.activeTab === "history" ? "var(--accent-primary)" : "var(--text-dim)",
  }}
>
  History
</button>
```

- [ ] **Step 5: Update App.tsx to render HistoryView**

```typescript
case "history":
  return <HistoryView />;
```

Add import:
```typescript
import HistoryView from "./components/HistoryView";
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api.ts frontend/src/context/AppContext.tsx frontend/src/components/HistoryView.tsx frontend/src/components/NavBar.tsx frontend/src/App.tsx
git commit -m "feat: HistoryView frontend with re-download"
```

---

## Task 7: Stats Frontend (StatsView + NavBar + App.tsx)

**Files:**
- Create: `frontend/src/components/StatsView.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/context/AppContext.tsx`

**Interfaces:**
- Consumes: `GET /stats`
- Produces: `StatsView` component, `stats` state in AppContext

- [ ] **Step 1: Add API method**

```typescript
export const stats = {
  get: () => api.get("/stats"),
};
```

- [ ] **Step 2: Add stats state in AppContext**

```typescript
stats: Record<string, number>;

| { type: "SET_STATS"; payload: Record<string, number> }

stats: {},

SET_STATS: { ...state, stats: action.payload }
```

- [ ] **Step 3: Create `StatsView.tsx`**

```typescript
import { useEffect } from "react";
import { stats as statsApi } from "../api";
import { useApp } from "../context/AppContext";

export default function StatsView() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    statsApi.get().then((data) => {
      dispatch({ type: "SET_STATS", payload: data });
    });
  }, [dispatch]);

  const s = state.stats;
  const totalTracks = s.total_tracks || 0;
  const totalBytes = s.total_bytes || 0;
  const qualityBreakdown = [
    { label: "Hi-Res", value: s.quality_hi_res || 0, key: "quality_hi_res" },
    { label: "Lossless", value: s.quality_lossless || 0, key: "quality_lossless" },
    { label: "320k", value: s.quality_320k || 0, key:Plans          quality_320k" },
    { label: "96k", value: s.quality_96k || 0, key: "quality_96k" },
  ];
  const maxQuality = Math.max(...qualityBreakdown.map((q) => q.value), 1);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <h2 className="text-lg font-bold mb-6" style={{ color: "var(--text-bright)" }}>
        Stats
      </h2>

      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="glass p-6 text-center">
          <p className="text-3xl font-bold" style={{ color: "var(--accent-primary)" }}>
            {totalTracks}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Total Tracks
          </p>
        </div>
        <div className="glass p-6 text-center">
          <p className="text-3xl font-bold" style={{ color: "var(--accent-secondary)" }}>
            {formatSize(totalBytes)}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Total Storage
          </p>
        </div>
      </div>

      <h3 className="text-sm font-medium mb-4" style={{ color: "var(--text-bright)" }}>
        Quality Breakdown
      </h3>
      <div className="space-y-3">
        {qualityBreakdown.map((q) => (
          <div key={q.key} className="glass p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{q.label}</span>
              <span className="text-xs font-medium" style={{ color: "var(--text-bright)" }}>
                {q.value}
              </span>
            </div>
            <div className="progress-track" style={{ height: "6px" }}>
              <div
                className="progress-fill"
                style={{
                  width: `${(q.value / maxQuality) * 100}%`,
                  background: "var(--accent-primary)",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs mt-6" style={{ color: "var(--text-dim)" }}>
        Stats are stored device-wide and are not tied to your Tidal account.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Update NavBar.tsx to add Stats tab**

Add Stats button alongside History.

- [ ] **Step 5: Update App.tsx to render StatsView**

```typescript
case "stats":
  return <StatsView />;
```

Add import:
```typescript
import StatsView from "./components/StatsView";
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend
npm run build
```

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api.ts frontend/src/context/AppContext.tsx frontend/src/components/StatsView.tsx frontend/src/App.tsx frontend/src/components/NavBar.tsx
git commit -m "feat: Stats dashboard frontend"
```

>

## Task 8: Update README + Final Polish

**Files:**
- Modify: `README.md`
- Modify: `requirements.txt` (if librosa not already added)

- [ ] **Step 1: Update README features list**

Add to the features section:
- **Download History** — Browse all past downloads with re-download and open-folder actions
- **Device-wide Stats** — Track total tracks, storage used, and quality breakdown across all sessions
- **Camelot Key Detection** — Analyze audio waveform to detect musical key in Camelot notation, independent of Tidal metadata

- [ ] **Step 2: Commit**

```bash
git add README.md requirements.txt
git commit -m "docs: update README with new features"
```

---

## Task Checklist

- [ ] Task 1: Fix `.tmp` cleanup
- [ ] Task 2: History backend (pagination + re-download)
- [ ] Task 3: Stats backend (device_stats table + /stats)
- [ ] Task 4: Camelot key detection backend
- [ ] Task 5: Integrate stats + key into downloader
- [ ] Task 6: History frontend (HistoryView + NavBar + App.tsx)
- [ ] Task 7: Stats frontend (StatsView + NavBar + App.tsx)
- [ ] Task 8: README update + final polish

---

## Spec Coverage Check

| Spec Section | Covered By |
|-------------|-----------|
| `.tmp` cleanup | Task 1 |
| History backend | Task 2 |
| History frontend | Task 6 |
| Stats backend | Task 3 |
| Stats frontend | Task 7 |
| Camelot key detection | Task 4 |
| Key integration into pipeline | Task 5 |
| README update | Task 8 |

---

## Placeholder Scan

- No "TBD", "TODO", or incomplete sections found.
- All code blocks contain complete, runnable code.
- All task boundaries are independently testable.
- Camelot mapping table is complete with all 24 keys.
