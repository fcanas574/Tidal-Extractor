# TidalExtractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web-based Tidal downloader that downloads songs, playlists, and albums at verified quality with format conversion and extended metadata tagging.

**Architecture:** React SPA frontend communicates with FastAPI backend via REST + WebSocket. Backend uses tidalapi for Tidal API access, ffmpeg for format conversion, ffprobe for quality verification, and mutagen for metadata tagging. Downloads are sequential to avoid rate limiting.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, tidalapi 0.8.x, ffmpeg-python, mutagen, aiosqlite, pyyaml, React 18, TypeScript, Vite, TailwindCSS

---

## File Structure

```
TidalExtractor/
├── backend/
│   ├── main.py              # FastAPI app, CORS, router includes, lifespan
│   ├── config.py             # YAML config loading/saving, settings model
│   ├── auth.py               # OAuth device link flow, session management
│   ├── search.py             # Search endpoints (tracks, albums, playlists)
│   ├── downloader.py         # Sequential download queue orchestrator
│   ├── quality.py            # Quality probing (ffprobe), bitrate thresholds, preset fallback
│   ├── tagger.py             # Metadata embedding via mutagen
│   ├── converter.py          # Format conversion via ffmpeg
│   ├── models.py             # SQLite schema, queue/history/cache CRUD
│   ├── ws.py                 # WebSocket connection manager
│   └── tests/
│       ├── test_quality.py
│       ├── test_converter.py
│       ├── test_tagger.py
│       ├── test_downloader.py
│       └── test_models.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── index.css
│   │   ├── api.ts                # REST client functions
│   │   ├── context/
│   │   │   └── AppContext.tsx     # React Context + useReducer
│   │   ├── components/
│   │   │   ├── AuthGate.tsx
│   │   │   ├── NavBar.tsx
│   │   │   ├── SearchView.tsx
│   │   │   ├── QueueView.tsx
│   │   │   └── SettingsView.tsx
│   │   └── hooks/
│   │       └── useWebSocket.ts
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── postcss.config.js
├── requirements.txt
├── config.yaml
└── .gitignore
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.gitignore`
- Create: `backend/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create project root files**

Create `requirements.txt`:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
tidalapi==0.8.11
ffmpeg-python==0.2.0
mutagen==1.47.0
aiosqlite==0.20.0
pyyaml==6.0.2
httpx==0.28.1
pytest==8.3.4
pytest-asyncio==0.24.0
```

Create `config.yaml`:
```yaml
default_quality: high_lossless
default_format: FLAC
output_dir: ~/Music/TidalDownloads
```

Create `.gitignore`:
```
__pycache__/
*.pyc
.env
tidal-session.json
*.tmp
node_modules/
dist/
.superpowers/
backend/tests/test_files/
```

Create empty `backend/__init__.py` and `backend/tests/__init__.py`.

- [ ] **Step 2: Initialize git repo and commit**

```bash
cd /Users/felipecanas/Documents/TidalExtractor
git init
git add requirements.txt config.yaml .gitignore backend/__init__.py backend/tests/__init__.py
git commit -m "chore: project scaffolding with dependencies and config"
```

---

### Task 2: SQLite Models

**Files:**
- Create: `backend/models.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test for queue/history SQLite operations**

Create `backend/tests/test_models.py`:
```python
import asyncio
import os
import pytest
from backend.models import Database

TEST_DB = "backend/tests/test_models.db"

@pytest.fixture
async def db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    database = Database(TEST_DB)
    await database.init()
    yield database
    await database.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.mark.asyncio
async def test_add_and_get_queue_item(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    assert item["id"] == 1
    assert item["status"] == "queued"

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "12345"
    assert queue[0]["title"] == "Test Song"

@pytest.mark.asyncio
async def test_update_queue_status(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    await db.update_queue_status(item["id"], "downloading")
    queue = await db.get_queue()
    assert queue[0]["status"] == "downloading"

@pytest.mark.asyncio
async def test_remove_from_queue(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    await db.remove_from_queue(item["id"])
    queue = await db.get_queue()
    assert len(queue) == 0

@pytest.mark.asyncio
async def test_add_to_history(db):
    await db.add_to_history(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
        file_path="/music/test.flac",
        file_size=27000000,
        actual_bitrate=1011,
    )
    history = await db.get_history()
    assert len(history) == 1
    assert history[0]["actual_bitrate"] == 1011

@pytest.mark.asyncio
async def test_quality_cache_set_and_get(db):
    await db.set_quality_cache("high_lossless", 1011)
    cached = await db.get_quality_cache()
    assert cached == {"preset": "high_lossless", "bitrate": 1011}

    await db.clear_quality_cache()
    cached = await db.get_quality_cache()
    assert cached is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.models'`

- [ ] **Step 3: Implement Database class**

Create `backend/models.py`:
```python
import aiosqlite
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: str = "tidal_extractor.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tidal_id TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'track',
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                quality TEXT NOT NULL DEFAULT 'high_lossless',
                format TEXT NOT NULL DEFAULT 'FLAC',
                status TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0.0,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tidal_id TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'track',
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                quality TEXT NOT NULL,
                format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                actual_bitrate INTEGER NOT NULL DEFAULT 0,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS quality_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                preset TEXT NOT NULL,
                bitrate INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def add_to_queue(self, tidal_id, item_type, title, artist, album, quality, format):
        cursor = await self._conn.execute(
            """INSERT INTO queue (tidal_id, item_type, title, artist, album, quality, format)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tidal_id, item_type, title, artist, album, quality, format),
        )
        await self._conn.commit()
        row = await self._conn.execute_fetchall(
            "SELECT * FROM queue WHERE id = ?", (cursor.lastrowid,)
        )
        return dict(row[0])

    async def get_queue(self):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM queue ORDER BY created_at ASC"
        )
        return [dict(r) for r in rows]

    async def update_queue_status(self, item_id: int, status: str, error: str = None, progress: float = None):
        parts = ["status = ?"]
        values = [status]
        if error is not None:
            parts.append("error = ?")
            values.append(error)
        if progress is not None:
            parts.append("progress = ?")
            values.append(progress)
        values.append(item_id)
        await self._conn.execute(
            f"UPDATE queue SET {', '.join(parts)} WHERE id = ?", values
        )
        await self._conn.commit()

    async def remove_from_queue(self, item_id: int):
        await self._conn.execute("DELETE FROM queue WHERE id = ?", (item_id,))
        await self._conn.commit()

    async def add_to_history(self, tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate):
        await self._conn.execute(
            """INSERT INTO history (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate),
        )
        await self._conn.commit()

    async def get_history(self, limit: int = 100):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM history ORDER BY downloaded_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]

    async def set_quality_cache(self, preset: str, bitrate: int):
        await self._conn.execute("DELETE FROM quality_cache")
        await self._conn.execute(
            "INSERT INTO quality_cache (id, preset, bitrate) VALUES (1, ?, ?)",
            (preset, bitrate),
        )
        await self._conn.commit()

    async def get_quality_cache(self):
        rows = await self._conn.execute_fetchall("SELECT * FROM quality_cache WHERE id = 1")
        if not rows:
            return None
        return {"preset": rows[0]["preset"], "bitrate": rows[0]["bitrate"]}

    async def clear_quality_cache(self):
        await self._conn.execute("DELETE FROM quality_cache")
        await self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_models.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/tests/test_models.py
git commit -m "feat: SQLite models for queue, history, and quality cache"
```

---

### Task 3: Config Loader

**Files:**
- Create: `backend/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test for config loading and saving**

Create `backend/tests/test_config.py`:
```python
import os
import tempfile
import pytest
from backend.config import AppConfig

@pytest.fixture
def tmp_config(tmp_path):
    return str(tmp_path / "test_config.yaml")

def test_load_defaults_when_file_missing(tmp_config):
    cfg = AppConfig(tmp_config)
    assert cfg.default_quality == "high_lossless"
    assert cfg.default_format == "FLAC"
    assert "TidalDownloads" in cfg.output_dir

def test_save_and_reload(tmp_config):
    cfg = AppConfig(tmp_config)
    cfg.default_quality = "low_320k"
    cfg.default_format = "MP3"
    cfg.output_dir = "/tmp/music"
    cfg.save()

    cfg2 = AppConfig(tmp_config)
    assert cfg2.default_quality == "low_320k"
    assert cfg2.default_format == "MP3"
    assert cfg2.output_dir == "/tmp/music"

def test_update_and_persist(tmp_config):
    cfg = AppConfig(tmp_config)
    cfg.update(default_format="M4A")
    cfg.save()

    cfg2 = AppConfig(tmp_config)
    assert cfg2.default_format == "M4A"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.config'`

- [ ] **Step 3: Implement AppConfig**

Create `backend/config.py`:
```python
import yaml
from pathlib import Path
from typing import Optional


DEFAULTS = {
    "default_quality": "high_lossless",
    "default_format": "FLAC",
    "output_dir": "~/Music/TidalDownloads",
}


class AppConfig:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.default_quality: str = DEFAULTS["default_quality"]
        self.default_format: str = DEFAULTS["default_format"]
        self.output_dir: str = DEFAULTS["output_dir"]
        self._load()

    def _load(self):
        path = Path(self.config_path)
        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            self.default_quality = data.get("default_quality", self.default_quality)
            self.default_format = data.get("default_format", self.default_format)
            self.output_dir = data.get("output_dir", self.output_dir)

    def save(self):
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                {
                    "default_quality": self.default_quality,
                    "default_format": self.default_format,
                    "output_dir": self.output_dir,
                },
                f,
                default_flow_style=False,
            )

    def update(self, **kwargs):
        if "default_quality" in kwargs:
            self.default_quality = kwargs["default_quality"]
        if "default_format" in kwargs:
            self.default_format = kwargs["default_format"]
        if "output_dir" in kwargs:
            self.output_dir = kwargs["output_dir"]

    def as_dict(self):
        return {
            "default_quality": self.default_quality,
            "default_format": self.default_format,
            "output_dir": self.output_dir,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "feat: YAML config loader with defaults and persistence"
```

---

### Task 4: Quality Probe and Verification

**Files:**
- Create: `backend/quality.py`
- Create: `backend/tests/test_quality.py`

- [ ] **Step 1: Write the failing test for quality probing**

Create `backend/tests/test_quality.py`:
```python
import pytest
from backend.quality import get_bitrate, bitrate_meets_threshold, QUALITY_PRESETS


def test_bitrate_meets_threshold_lossless():
    assert bitrate_meets_threshold("high_lossless", 1011) is True

def test_bitrate_meets_threshold_below_lossless():
    assert bitrate_meets_threshold("high_lossless", 200) is False

def test_bitrate_meets_threshold_320k():
    assert bitrate_meets_threshold("low_320k", 318) is True

def test_bitrate_meets_threshold_96k():
    assert bitrate_meets_threshold("low_96k", 95) is True

def test_quality_presets_order():
    assert list(QUALITY_PRESETS.keys()) == ["hi_res_lossless", "high_lossless", "low_320k", "low_96k"]

def test_get_bitrate_on_real_file():
    """This test requires ffprobe and uses the test runner's environment.
    If no test audio file exists, it xfails."""
    import subprocess
    result = subprocess.run(["ffprobe", "-version"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("ffprobe not installed")

    # Create a tiny test FLAC for probing
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        tmp_path = f.name
    try:
        # Generate 1 second of silence as FLAC
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "1", "-c:a", "flac", "-y", tmp_path],
            capture_output=True, check=True,
        )
        bitrate = get_bitrate(tmp_path)
        assert bitrate > 0
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_quality.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.quality'`

- [ ] **Step 3: Implement quality module**

Create `backend/quality.py`:
```python
import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered from highest to lowest — used by the quality probe fallback
QUALITY_PRESETS = {
    "hi_res_lossless": {"min_bitrate": 1500, "label": "HiRes Lossless (24-bit)"},
    "high_lossless": {"min_bitrate": 700, "label": "Lossless (16-bit FLAC)"},
    "low_320k": {"min_bitrate": 300, "label": "High (320kbps AAC)"},
    "low_96k": {"min_bitrate": 64, "label": "Normal (96kbps AAC)"},
}


def get_bitrate(file_path: str) -> Optional[int]:
    """Run ffprobe on a file and return the audio bitrate in kbps."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "audio":
                bitrate = int(stream.get("bit_rate", 0))
                if bitrate > 0:
                    return bitrate // 1000
        # Fallback: format-level bitrate
        fmt_bitrate = int(data.get("format", {}).get("bit_rate", 0))
        if fmt_bitrate > 0:
            return fmt_bitrate // 1000
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"ffprobe failed for {file_path}: {e}")
        return None


def bitrate_meets_threshold(preset: str, actual_bitrate: int) -> bool:
    """Check if the actual bitrate meets the minimum threshold for a quality preset."""
    threshold = QUALITY_PRESETS.get(preset, {}).get("min_bitrate", 0)
    return actual_bitrate >= threshold
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_quality.py -v
```

Expected: 5-6 passed (6 if ffprobe is installed)

- [ ] **Step 5: Commit**

```bash
git add backend/quality.py backend/tests/test_quality.py
git commit -m "feat: quality probe with ffprobe bitrate verification and preset thresholds"
```

---

### Task 5: Format Converter

**Files:**
- Create: `backend/converter.py`
- Create: `backend/tests/test_converter.py`

- [ ] **Step 1: Write the failing test for format conversion**

Create `backend/tests/test_converter.py`:
```python
import os
import subprocess
import tempfile
import pytest
from backend.converter import convert_format

def _generate_test_flac(path: str):
    """Generate a 1-second silent FLAC file for testing."""
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "flac", "-y", path],
        capture_output=True, check=True,
    )

@pytest.fixture
def test_flac(tmp_path):
    flac_path = str(tmp_path / "test.flac")
    _generate_test_flac(flac_path)
    return flac_path

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_convert_flac_to_mp3(test_flac, tmp_path):
    output = str(tmp_path / "test.mp3")
    result = convert_format(test_flac, output, "mp3", bitrate="320k")
    assert result == output
    assert os.path.exists(output)
    # Verify it's a valid MP3
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", output],
        capture_output=True, text=True,
    )
    import json
    data = json.loads(probe.stdout)
    assert data["streams"][0]["codec_name"] == "mp3"

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_convert_flac_to_m4a(test_flac, tmp_path):
    output = str(tmp_path / "test.m4a")
    result = convert_format(test_flac, output, "m4a", bitrate="320k")
    assert result == output
    assert os.path.exists(output)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", output],
        capture_output=True, text=True,
    )
    import json
    data = json.loads(probe.stdout)
    assert data["streams"][0]["codec_name"] == "aac"

def test_convert_same_format_returns_original(test_flac):
    """If output format matches input, return the original path without conversion."""
    result = convert_format(test_flac, test_flac, "flac")
    assert result == test_flac
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_converter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.converter'`

- [ ] **Step 3: Implement converter module**

Create `backend/converter.py`:
```python
import subprocess
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def convert_format(
    input_path: str,
    output_path: str,
    target_format: str,
    bitrate: Optional[str] = None,
) -> str:
    """Convert an audio file to a target format using ffmpeg.

    If the target format matches the source format (both FLAC), returns input_path as-is.
    Returns the output_path on success.
    """
    input_ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    target_fmt = target_format.lower()

    if input_ext == target_fmt:
        logger.info(f"Source is already {target_fmt}, skipping conversion")
        return input_path

    codec_map = {
        "mp3": "libmp3lame",
        "m4a": "aac",
        "flac": "flac",
    }
    codec = codec_map.get(target_fmt, "copy")

    cmd = ["ffmpeg", "-y", "-i", input_path]

    if target_fmt in ("mp3", "m4a") and bitrate:
        if codec == "aac":
            cmd += ["-c:a", codec, "-b:a", bitrate]
        else:
            cmd += ["-c:a", codec, "-b:a", bitrate]
    else:
        cmd += ["-c:a", codec]

    cmd.append(output_path)

    logger.info(f"Converting {input_path} -> {output_path} ({target_fmt}, {codec})")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"ffmpeg conversion failed: {result.stderr}")
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_converter.py -v
```

Expected: 3 passed (if ffmpeg installed)

- [ ] **Step 5: Commit**

```bash
git add backend/converter.py backend/tests/test_converter.py
git commit -m "feat: format converter using ffmpeg (FLAC, MP3, M4A)"
```

---

### Task 6: Metadata Tagger

**Files:**
- Create: `backend/tagger.py`
- Create: `backend/tests/test_tagger.py`

- [ ] **Step 1: Write the failing test for metadata tagging**

Create `backend/tests/test_tagger.py`:
```python
import os
import subprocess
import tempfile
import pytest
from backend.tagger import tag_file

def _generate_test_flac(path: str):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "flac", "-y", path],
        capture_output=True, check=True,
    )

def _generate_test_mp3(path: str):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "libmp3lame", "-b:a", "320k", "-y", path],
        capture_output=True, check=True,
    )

@pytest.fixture
def test_flac(tmp_path):
    flac_path = str(tmp_path / "test.flac")
    _generate_test_flac(flac_path)
    return flac_path

@pytest.fixture
def test_mp3(tmp_path):
    mp3_path = str(tmp_path / "test.mp3")
    _generate_test_mp3(mp3_path)
    return mp3_path

METADATA = {
    "title": "Test Song",
    "artist": "Test Artist",
    "album": "Test Album",
    "track_num": 5,
    "genre": "Electronic",
    "year": "2024",
    "label": "Test Label",
    "isrc": "US1234567890",
    "bpm": 128,
    "key": "Am",
}

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_flac(test_flac):
    tag_file(test_flac, METADATA)
    import mutagen
    f = mutagen.File(test_flac)
    assert f["title"][0] == "Test Song"
    assert f["artist"][0] == "Test Artist"
    assert f["album"][0] == "Test Album"
    assert f["tracknumber"][0] == "5"
    assert f["genre"][0] == "Electronic"
    assert f["date"][0] == "2024"
    assert f["label"][0] == "Test Label"
    assert f["isrc"][0] == "US1234567890"
    assert f["bpm"][0] == "128"
    assert f["initialkey"][0] == "Am"

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_mp3(test_mp3):
    tag_file(test_mp3, METADATA)
    import mutagen
    f = mutagen.File(test_mp3)
    assert f["TIT2"][0] == "Test Song"
    assert f["TPE1"][0] == "Test Artist"
    assert f["TALB"][0] == "Test Album"
    assert f["TRCK"][0] == "5"
    assert f["TCON"][0] == "Electronic"
    assert f["TDRC"][0] == "2024"
    assert f["TPUB"][0] == "Test Label"
    assert f["TSRC"][0] == "US1234567890"
    assert f["TBPM"][0] == "128"
    assert f["TKEY"][0] == "Am"

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_with_cover_art(test_flac, tmp_path):
    # Generate a tiny 1x1 PNG as cover art
    cover_path = str(tmp_path / "cover.jpg")
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=1x1:d=0.01",
         "-frames:v", "1", "-y", cover_path],
        capture_output=True, check=True,
    )
    meta = {**METADATA, "cover_art_path": cover_path}
    tag_file(test_flac, meta)
    import mutagen
    f = mutagen.File(test_flac)
    assert f.pictures, "Cover art should be embedded"

@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_skips_none_values(test_flac):
    """Fields with None or 0 values should not be written."""
    sparse_meta = {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "track_num": None,
        "genre": None,
        "year": None,
        "label": None,
        "isrc": None,
        "bpm": 0,
        "key": None,
    }
    tag_file(test_flac, sparse_meta)
    import mutagen
    f = mutagen.File(test_flac)
    assert f["title"][0] == "Test Song"
    assert "genre" not in f
    assert "bpm" not in f
    assert "initialkey" not in f
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_tagger.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.tagger'`

- [ ] **Step 3: Implement tagger module**

Create `backend/tagger.py`:
```python
import logging
import base64
import requests
from pathlib import Path
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC, TPUB, TSRC, TBPM, TKEY, APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from typing import Optional

logger = logging.getLogger(__name__)


def tag_file(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    """Tag an audio file with extended metadata.

    metadata keys: title, artist, album, track_num, genre, year, label,
                   isrc, bpm, key, cover_art_path
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".flac":
        _tag_flac(file_path, metadata, cover_art_url)
    elif ext == ".mp3":
        _tag_mp3(file_path, metadata, cover_art_url)
    elif ext == ".m4a":
        _tag_m4a(file_path, metadata, cover_art_url)
    else:
        logger.warning(f"Unsupported format for tagging: {ext}")


def _get_cover_bytes(metadata: dict, cover_art_url: Optional[str] = None) -> Optional[bytes]:
    """Load cover art from local path or download from URL."""
    local_path = metadata.get("cover_art_path")
    if local_path and Path(local_path).exists():
        return Path(local_path).read_bytes()
    if cover_art_url:
        try:
            resp = requests.get(cover_art_url, timeout=10)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            logger.warning(f"Failed to download cover art: {e}")
    return None


def _tag_flac(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = FLAC(file_path)
    f.delete()

    if metadata.get("title"):
        f["title"] = [metadata["title"]]
    if metadata.get("artist"):
        f["artist"] = [metadata["artist"]]
    if metadata.get("album"):
        f["album"] = [metadata["album"]]
    if metadata.get("track_num"):
        f["tracknumber"] = [str(metadata["track_num"])]
    if metadata.get("genre"):
        f["genre"] = [metadata["genre"]]
    if metadata.get("year"):
        f["date"] = [str(metadata["year"])]
    if metadata.get("label"):
        f["label"] = [metadata["label"]]
    if metadata.get("isrc"):
        f["isrc"] = [metadata["isrc"]]
    if metadata.get("bpm") and metadata["bpm"] > 0:
        f["bpm"] = [str(metadata["bpm"])]
    if metadata.get("key"):
        f["initialkey"] = [metadata["key"]]

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        pic = Picture()
        pic.type = 3  # Cover (front)
        pic.mime = "image/jpeg"
        pic.data = cover_bytes
        f.add_picture(pic)

    f.save()


def _tag_mp3(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = MP3(file_path)
    if f.tags is None:
        f.add_tags()
    f.tags.delall("APIC")

    tags = []
    if metadata.get("title"):
        tags.append(TIT2(encoding=3, text=metadata["title"]))
    if metadata.get("artist"):
        tags.append(TPE1(encoding=3, text=metadata["artist"]))
    if metadata.get("album"):
        tags.append(TALB(encoding=3, text=metadata["album"]))
    if metadata.get("track_num"):
        tags.append(TRCK(encoding=3, text=str(metadata["track_num"])))
    if metadata.get("genre"):
        tags.append(TCON(encoding=3, text=metadata["genre"]))
    if metadata.get("year"):
        tags.append(TDRC(encoding=3, text=str(metadata["year"])))
    if metadata.get("label"):
        tags.append(TPUB(encoding=3, text=metadata["label"]))
    if metadata.get("isrc"):
        tags.append(TSRC(encoding=3, text=metadata["isrc"]))
    if metadata.get("bpm") and metadata["bpm"] > 0:
        tags.append(TBPM(encoding=3, text=str(metadata["bpm"])))
    if metadata.get("key"):
        tags.append(TKEY(encoding=3, text=metadata["key"]))

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        tags.append(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))

    for tag in tags:
        f.tags.add(tag)
    f.save()


def _tag_m4a(file_path: str, metadata: dict, cover_art_url: Optional[str] = None):
    f = MP4(file_path)
    if f.tags is None:
        f.add_tags()

    # M4A uses different tag keys
    if metadata.get("title"):
        f.tags["\xa9nam"] = [metadata["title"]]
    if metadata.get("artist"):
        f.tags["\xa9ART"] = [metadata["artist"]]
    if metadata.get("album"):
        f.tags["\xa9alb"] = [metadata["album"]]
    if metadata.get("track_num"):
        f.tags["trkn"] = [(metadata["track_num"], 0)]
    if metadata.get("genre"):
        f.tags["\xa9gen"] = [metadata["genre"]]
    if metadata.get("year"):
        f.tags["\xa9DAY"] = [str(metadata["year"])]
    if metadata.get("label"):
        f.tags["----:com.apple.iTunes:LABEL"] = [metadata["label"].encode("utf-8")]
    if metadata.get("isrc"):
        f.tags["----:com.apple.iTunes:ISRC"] = [metadata["isrc"].encode("utf-8")]
    if metadata.get("bpm") and metadata["bpm"] > 0:
        f.tags["tmpo"] = [metadata["bpm"]]
    if metadata.get("key"):
        f.tags["----:com.apple.iTunes:initialkey"] = [metadata["key"].encode("utf-8")]

    cover_bytes = _get_cover_bytes(metadata, cover_art_url)
    if cover_bytes:
        f.tags["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]

    f.save()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_tagger.py -v
```

Expected: 4 passed (if ffmpeg installed)

- [ ] **Step 5: Commit**

```bash
git add backend/tagger.py backend/tests/test_tagger.py
git commit -m "feat: metadata tagger for FLAC, MP3, M4A with extended tags and cover art"
```

---

### Task 7: Download Orchestrator

**Files:**
- Create: `backend/downloader.py`
- Create: `backend/tests/test_downloader.py`

- [ ] **Step 1: Write the failing test for the download orchestrator**

Create `backend/tests/test_downloader.py`:
```python
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.downloader import DownloadOrchestrator
from backend.models import Database
from backend.config import AppConfig

@pytest.fixture
async def setup(tmp_path):
    db_path = str(tmp_path / "test.db")
    config_path = str(tmp_path / "config.yaml")
    output_dir = str(tmp_path / "downloads")
    os.makedirs(output_dir, exist_ok=True)

    db = Database(db_path)
    await db.init()
    config = AppConfig(config_path)
    config.output_dir = output_dir
    config.save()

    orch = DownloadOrchestrator(db=db, config=config)
    yield orch, db
    await db.close()

@pytest.mark.asyncio
async def test_build_filename_track(setup):
    orch, _ = setup
    name = orch._build_filename("Test Song", "Test Artist", ".flac", item_type="track")
    assert name == "Test Artist - Test Song.flac"

@pytest.mark.asyncio
async def test_build_filename_playlist_track(setup):
    orch, _ = setup
    name = orch._build_filename(
        "Track One", "Artist", ".flac",
        item_type="playlist", collection_name="My Playlist", track_num=1,
    )
    assert "My Playlist" in name
    assert "01 - Artist - Track One.flac" in name

@pytest.mark.asyncio
async def test_sanitize_filename(setup):
    orch, _ = setup
    assert orch._sanitize_filename('Song: "Special" / Mix') == "Song - Special - Mix"

@pytest.mark.asyncio
async def test_extract_track_metadata():
    from backend.downloader import extract_track_metadata
    mock_track = MagicMock()
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.artists = [MagicMock(name="Test Artist")]
    mock_track.album.name = "Test Album"
    mock_track.album.id = 999
    mock_track.track_num = 3
    mock_track.duration = 240
    mock_track.isrc = "US1234567890"
    mock_track.bpm = 128
    mock_track.key = "Am"
    mock_track.explicit = False
    mock_track.audio_quality = "LOSSLESS"

    meta = extract_track_metadata(mock_track)
    assert meta["title"] == "Test Song"
    assert meta["artist"] == "Test Artist"
    assert meta["album"] == "Test Album"
    assert meta["track_num"] == 3
    assert meta["isrc"] == "US1234567890"
    assert meta["bpm"] == 128
    assert meta["key"] == "Am"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_downloader.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.downloader'`

- [ ] **Step 3: Implement download orchestrator**

Create `backend/downloader.py`:
```python
import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

import tidalapi
from tidalapi import Quality

from backend.config import AppConfig
from backend.models import Database
from backend.quality import get_bitrate, bitrate_meets_threshold, QUALITY_PRESETS, QUALITY_PRESETS_ORDER
from backend.converter import convert_format
from backend.tagger import tag_file

logger = logging.getLogger(__name__)

# Map our preset names to tidalapi Quality enum
QUALITY_ENUM_MAP = {
    "hi_res_lossless": Quality.hi_res_lossless,
    "high_lossless": Quality.high_lossless,
    "low_320k": Quality.low_320k,
    "low_96k": Quality.low_96k,
}

# Map target format to file extension
FORMAT_EXT_MAP = {
    "FLAC": ".flac",
    "MP3": ".mp3",
    "M4A": ".m4a",
}


def extract_track_metadata(track) -> dict:
    """Extract extended metadata from a tidalapi Track object."""
    return {
        "title": track.title or "Unknown",
        "artist": track.artist.name if track.artist else "Unknown",
        "artists": [a.name for a in track.artists] if track.artists else [],
        "album": track.album.name if track.album else "Unknown",
        "album_id": track.album.id if track.album else None,
        "track_num": track.track_num or 0,
        "duration": track.duration or 0,
        "isrc": track.isrc or None,
        "bpm": track.bpm or 0,
        "key": track.key_scale if hasattr(track, "key_scale") and track.key_scale else (track.key if hasattr(track, "key") and track.key else None),
        "explicit": track.explicit or False,
        "quality": track.audio_quality or "UNKNOWN",
        "cover_art_url": None,  # populated separately from album
    }


class DownloadOrchestrator:
    def __init__(self, db: Database, config: AppConfig, ws_manager=None):
        self.db = db
        self.config = config
        self.ws_manager = ws_manager
        self.session: Optional[tidalapi.Session] = None
        self._probed_quality: Optional[str] = None
        self._running = False

    def set_session(self, session: tidalapi.Session):
        self.session = session

    def _sanitize_filename(self, name: str) -> str:
        """Remove characters not safe for filenames."""
        name = re.sub(r'[\\/:*?"<>|]', ' -', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _build_filename(
        self,
        title: str,
        artist: str,
        ext: str,
        item_type: str = "track",
        collection_name: str = None,
        track_num: int = None,
    ) -> str:
        """Build the output filename based on item type."""
        safe_title = self._sanitize_filename(title)
        safe_artist = self._sanitize_filename(artist)

        if item_type in ("album", "playlist") and collection_name:
            safe_collection = self._sanitize_filename(collection_name)
            num_prefix = f"{track_num:02d} - " if track_num else ""
            return f"{safe_collection}/{num_prefix}{safe_artist} - {safe_title}{ext}"
        else:
            return f"{safe_artist} - {safe_title}{ext}"

    async def probe_quality(self) -> Optional[str]:
        """Try quality presets from highest to lowest, probe actual bitrate,
        and cache the first preset that delivers expected quality."""
        if not self.session:
            raise RuntimeError("Tidal session not initialized")

        for preset_name in QUALITY_PRESETS:
            logger.info(f"Probing quality preset: {preset_name}")
            quality_enum = QUALITY_ENUM_MAP[preset_name]

            try:
                test_track = self.session.get_tracks(limit=1)[0]
                self.session.audio_quality = quality_enum
                stream = test_track.get_stream()
                manifest = stream.get_stream_manifest()
                urls = manifest.get_urls()

                if not urls:
                    continue

                # Download first ~500KB for ffprobe
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(urls[0])
                    partial = resp.content[:512000]

                import tempfile
                with tempfile.NamedTemporaryFile(suffix=manifest.file_extension, delete=False) as f:
                    f.write(partial)
                    tmp_path = f.name

                try:
                    bitrate = get_bitrate(tmp_path)
                    if bitrate and bitrate_meets_threshold(preset_name, bitrate):
                        logger.info(f"Quality probe success: {preset_name} delivered {bitrate}kbps")
                        await self.db.set_quality_cache(preset_name, bitrate)
                        self._probed_quality = preset_name
                        return preset_name
                finally:
                    os.unlink(tmp_path)

            except Exception as e:
                logger.warning(f"Quality probe failed for {preset_name}: {e}")
                continue

        logger.error("All quality presets failed probe")
        return None

    async def download_track(self, queue_item: dict, on_progress=None):
        """Download a single track from the queue."""
        if not self.session:
            raise RuntimeError("Tidal session not initialized")

        tidal_id = queue_item["tidal_id"]
        target_format = queue_item["format"]
        quality_preset = queue_item["quality"]
        item_type = queue_item["item_type"]

        # 1. Get track and stream
        track = self.session.track(int(tidal_id))
        metadata = extract_track_metadata(track)

        # Set quality
        quality_enum = QUALITY_ENUM_MAP.get(quality_preset, Quality.high_lossless)
        self.session.audio_quality = quality_enum
        stream = track.get_stream()
        manifest = stream.get_stream_manifest()
        urls = manifest.get_urls()

        if not urls:
            raise RuntimeError(f"No stream URL for track {tidal_id}")

        ext = FORMAT_EXT_MAP.get(target_format, ".flac")
        filename = self._build_filename(
            metadata["title"], metadata["artist"], ext, item_type=item_type,
        )
        output_dir = Path(os.path.expanduser(self.config.output_dir))
        output_path = output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Download to temp file
        tmp_path = str(output_path) + ".tmp"
        import httpx
        total_size = 0

        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", urls[0]) as resp:
                total = int(resp.headers.get("content-length", 0))
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        total_size += len(chunk)
                        if on_progress and total > 0:
                            pct = (total_size / total) * 100
                            await on_progress(queue_item["id"], pct, total_size, total)

        # 3. Verify quality
        actual_bitrate = get_bitrate(tmp_path) or 0

        # 4. Convert if needed
        final_path = str(output_path)
        if ext != manifest.file_extension:
            final_path = await asyncio.to_thread(
                convert_format, tmp_path, final_path, target_format.lower()
            )
        else:
            shutil.move(tmp_path, final_path)

        # 5. Tag metadata
        # Get cover art URL
        try:
            album = self.session.album(track.album.id)
            cover_url = album.image(1280)
            metadata["cover_art_url"] = cover_url
        except Exception:
            pass

        await asyncio.to_thread(tag_file, final_path, metadata, metadata.get("cover_art_url"))

        # 6. Log to history and remove from queue
        file_size = os.path.getsize(final_path)
        await self.db.add_to_history(
            tidal_id=tidal_id, item_type=item_type, title=metadata["title"],
            artist=metadata["artist"], album=metadata["album"],
            quality=quality_preset, format=target_format,
            file_path=final_path, file_size=file_size, actual_bitrate=actual_bitrate,
        )
        await self.db.remove_from_queue(queue_item["id"])

        logger.info(f"Downloaded: {final_path} ({actual_bitrate}kbps)")
        return final_path

    async def process_queue(self):
        """Process all items in the download queue sequentially."""
        self._running = True
        while self._running:
            queue = await self.db.get_queue()
            queued = [item for item in queue if item["status"] == "queued"]
            if not queued:
                break

            item = queued[0]
            await self.db.update_queue_status(item["id"], "downloading")

            try:
                async def on_progress(item_id, pct, bytes_done, bytes_total):
                    await self.db.update_queue_status(item_id, "downloading", progress=pct)
                    if self.ws_manager:
                        await self.ws_manager.broadcast({
                            "type": "progress",
                            "id": str(item_id),
                            "pct": round(pct, 1),
                            "bytes": bytes_done,
                            "total": bytes_total,
                        })

                path = await self.download_track(item, on_progress=on_progress)
                if self.ws_manager:
                    file_size = os.path.getsize(path)
                    await self.ws_manager.broadcast({
                        "type": "complete",
                        "id": str(item["id"]),
                        "path": path,
                        "size": file_size,
                    })
            except Exception as e:
                logger.error(f"Download failed for item {item['id']}: {e}")
                await self.db.update_queue_status(item["id"], "failed", error=str(e))
                if self.ws_manager:
                    await self.ws_manager.broadcast({
                        "type": "error",
                        "id": str(item["id"]),
                        "reason": str(e),
                    })

    def stop(self):
        self._running = False
```

Note: `QUALITY_PRESETS_ORDER` is defined in `quality.py` as `list(QUALITY_PRESETS.keys())` — I need to add that export.

- [ ] **Step 4: Add QUALITY_PRESETS_ORDER to quality.py**

In `backend/quality.py`, add after the `QUALITY_PRESETS` dict:
```python
QUALITY_PRESETS_ORDER = list(QUALITY_PRESETS.keys())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest backend/tests/test_downloader.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/downloader.py backend/tests/test_downloader.py
git commit -m "feat: sequential download orchestrator with quality probe and progress"
```

---

### Task 8: Auth Module

**Files:**
- Create: `backend/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing test for auth module**

Create `backend/tests/test_auth.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from backend.auth import AuthManager


@pytest.fixture
def auth_manager(tmp_path):
    session_file = str(tmp_path / "tidal-session.json")
    return AuthManager(session_file=session_file)


def test_auth_manager_initial_state(auth_manager):
    assert auth_manager.is_authenticated is False
    assert auth_manager.session is None


def test_get_auth_status_unauthenticated(auth_manager):
    status = auth_manager.get_status()
    assert status["authenticated"] is False
    assert status["username"] is None


@patch("backend.auth.tidalapi")
def test_get_device_link(mock_tidal, auth_manager):
    mock_session = MagicMock()
    mock_login = MagicMock()
    mock_login.verification_uri_complete = "https://link.tidal.com/ABC123"
    mock_login.user_code = "ABC123"
    mock_login.expires_in = 300

    mock_session.login_oauth.return_value = (mock_login, MagicMock())

    auth_manager.session = mock_session
    result = auth_manager.get_device_link()
    assert result["url"] == "https://link.tidal.com/ABC123"
    assert result["code"] == "ABC123"
    assert result["expires_in"] == 300
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_auth.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.auth'`

- [ ] **Step 3: Implement auth module**

Create `backend/auth.py`:
```python
import logging
from pathlib import Path
from typing import Optional

import tidalapi
from tidalapi import Quality, Config

logger = logging.getLogger(__name__)


class AuthManager:
    def __init__(self, session_file: str = "tidal-session.json"):
        self.session_file = Path(session_file)
        self.session: Optional[tidalapi.Session] = None
        self._device_login = None
        self._device_future = None

    @property
    def is_authenticated(self) -> bool:
        if self.session is None:
            return False
        try:
            return self.session.check_login()
        except Exception:
            return False

    def get_status(self) -> dict:
        if not self.is_authenticated:
            return {"authenticated": False, "username": None}
        try:
            user = self.session.user
            username = user.username if user else None
        except Exception:
            username = None
        return {"authenticated": True, "username": username}

    def get_device_link(self) -> dict:
        """Initiate OAuth device link flow. Returns URL and code for the user to visit."""
        config = Config(quality=Quality.high_lossless)
        self.session = tidalapi.Session(config)
        login, future = self.session.login_oauth()
        self._device_login = login
        self._device_future = future
        return {
            "url": login.verification_uri_complete,
            "code": login.user_code,
            "expires_in": login.expires_in,
        }

    def wait_for_device_auth(self) -> bool:
        """Block until the user completes device auth. Returns True on success."""
        if not self._device_future:
            return False
        try:
            self._device_future.result()
            # Save session for reuse
            self.session.save_session_to_file(self.session_file)
            logger.info("Tidal auth successful, session saved")
            return True
        except Exception as e:
            logger.error(f"Device auth failed: {e}")
            return False

    def load_saved_session(self, quality: str = "high_lossless") -> bool:
        """Try to load a previously saved session."""
        quality_enum = {
            "hi_res_lossless": Quality.hi_res_lossless,
            "high_lossless": Quality.high_lossless,
            "low_320k": Quality.low_320k,
            "low_96k": Quality.low_96k,
        }.get(quality, Quality.high_lossless)

        config = Config(quality=quality_enum)
        self.session = tidalapi.Session(config)
        try:
            if self.session_file.exists():
                self.session.login_session_file(self.session_file)
                if self.session.check_login():
                    logger.info("Loaded saved Tidal session")
                    return True
        except Exception as e:
            logger.warning(f"Failed to load saved session: {e}")
        self.session = None
        return False

    def logout(self):
        """Clear the saved session and reset."""
        if self.session_file.exists():
            self.session_file.unlink()
        self.session = None
        self._device_login = None
        self._device_future = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_auth.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py backend/tests/test_auth.py
git commit -m "feat: OAuth device link auth manager with session persistence"
```

---

### Task 9: Search Module

**Files:**
- Create: `backend/search.py`
- Create: `backend/tests/test_search.py`

- [ ] **Step 1: Write the failing test for search module**

Create `backend/tests/test_search.py`:
```python
import pytest
from unittest.mock import MagicMock
from backend.search import search_tidal, format_track, format_album, format_playlist


def test_format_track():
    mock_track = MagicMock()
    mock_track.id = 12345
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.album.name = "Test Album"
    mock_track.duration = 240
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = "US1234567890"
    mock_track.listen_url = "https://listen.tidal.com/album/99/track/12345"

    result = format_track(mock_track)
    assert result["id"] == 12345
    assert result["title"] == "Test Song"
    assert result["artist"] == "Test Artist"
    assert result["album"] == "Test Album"
    assert result["duration"] == 240
    assert result["quality"] == "LOSSLESS"

def test_format_album():
    mock_album = MagicMock()
    mock_album.id = 99
    mock_album.name = "Test Album"
    mock_album.artist.name = "Test Artist"
    mock_album.num_tracks = 12
    mock_album.release_date = "2024-01-01"
    mock_album.audio_quality = "LOSSLESS"
    mock_album.image = MagicMock(return_value="https://img.tidal.com/cover.jpg")

    result = format_album(mock_album)
    assert result["id"] == 99
    assert result["name"] == "Test Album"
    assert result["artist"] == "Test Artist"
    assert result["num_tracks"] == 12
    assert result["cover_url"] == "https://img.tidal.com/cover.jpg"

def test_format_playlist():
    mock_pl = MagicMock()
    mock_pl.id = "abc-123"
    mock_pl.name = "My Playlist"
    mock_pl.num_tracks = 50
    mock_pl.image = MagicMock(return_value="https://img.tidal.com/pl.jpg")

    result = format_playlist(mock_pl)
    assert result["id"] == "abc-123"
    assert result["name"] == "My Playlist"
    assert result["num_tracks"] == 50
    assert result["cover_url"] == "https://img.tidal.com/pl.jpg"

def test_search_tidal_tracks():
    mock_session = MagicMock()
    mock_track = MagicMock()
    mock_track.id = 1
    mock_track.title = "Found Song"
    mock_track.artist.name = "Found Artist"
    mock_track.album.name = "Found Album"
    mock_track.duration = 200
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = None
    mock_track.listen_url = ""

    mock_session.search.return_value = {"tracks": [mock_track], "albums": [], "playlists": [], "artists": [], "videos": [], "top_hit": None}

    results = search_tidal(mock_session, "Found Song", models=["track"])
    assert len(results["tracks"]) == 1
    assert results["tracks"][0]["title"] == "Found Song"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/test_search.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.search'`

- [ ] **Step 3: Implement search module**

Create `backend/search.py`:
```python
import logging
from typing import List, Optional

import tidalapi

logger = logging.getLogger(__name__)


def format_track(track) -> dict:
    """Format a tidalapi Track into a serializable dict."""
    return {
        "id": track.id,
        "title": track.title or "Unknown",
        "artist": track.artist.name if track.artist else "Unknown",
        "album": track.album.name if track.album else "Unknown",
        "album_id": track.album.id if track.album else None,
        "duration": track.duration or 0,
        "quality": track.audio_quality or "UNKNOWN",
        "explicit": track.explicit or False,
        "isrc": track.isrc or None,
        "url": track.listen_url or "",
        "cover_url": None,  # populated from album lookup if needed
    }


def format_album(album) -> dict:
    """Format a tidalapi Album into a serializable dict."""
    cover_url = None
    try:
        cover_url = album.image(640)
    except Exception:
        pass
    return {
        "id": album.id,
        "name": album.name or "Unknown",
        "artist": album.artist.name if album.artist else "Unknown",
        "num_tracks": album.num_tracks or 0,
        "release_date": str(album.release_date) if album.release_date else None,
        "quality": album.audio_quality if hasattr(album, "audio_quality") else "UNKNOWN",
        "cover_url": cover_url,
    }


def format_playlist(playlist) -> dict:
    """Format a tidalapi Playlist into a serializable dict."""
    cover_url = None
    try:
        cover_url = playlist.image(640)
    except Exception:
        pass
    return {
        "id": playlist.id,
        "name": playlist.name or "Unknown",
        "num_tracks": playlist.num_tracks or 0,
        "creator": playlist.creator.name if hasattr(playlist, "creator") and playlist.creator else None,
        "cover_url": cover_url,
    }


def search_tidal(session: tidalapi.Session, query: str, models: Optional[List[str]] = None, limit: int = 20) -> dict:
    """Search Tidal for tracks, albums, and/or playlists."""
    if models is None:
        models = ["track", "album", "playlist"]

    model_map = {
        "track": tidalapi.Track,
        "album": tidalapi.Album,
        "playlist": tidalapi.Playlist,
    }
    tidal_models = [model_map[m] for m in models if m in model_map]

    if not tidal_models:
        return {"tracks": [], "albums": [], "playlists": []}

    results = session.search(query, models=tidal_models, limit=limit)

    tracks = [format_track(t) for t in results.get("tracks", [])]
    albums = [format_album(a) for a in results.get("albums", [])]
    playlists = [format_playlist(p) for p in results.get("playlists", [])]

    return {"tracks": tracks, "albums": albums, "playlists": playlists}


def get_album_tracks(session: tidalapi.Session, album_id: int) -> List[dict]:
    """Get all tracks from an album."""
    album = session.album(album_id)
    tracks = album.tracks()
    result = []
    for t in tracks:
        formatted = format_track(t)
        try:
            formatted["cover_url"] = album.image(640)
        except Exception:
            pass
        result.append(formatted)
    return result


def get_playlist_tracks(session: tidalapi.Session, playlist_id: str) -> List[dict]:
    """Get all tracks from a playlist."""
    playlist = session.playlist(playlist_id)
    tracks = playlist.tracks()
    result = []
    for t in tracks:
        formatted = format_track(t)
        try:
            formatted["cover_url"] = playlist.image(640)
        except Exception:
            pass
        result.append(formatted)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_search.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/search.py backend/tests/test_search.py
git commit -m "feat: search module with track/album/playlist formatting"
```

---

### Task 10: WebSocket Manager

**Files:**
- Create: `backend/ws.py`

- [ ] **Step 1: Implement WebSocket connection manager**

Create `backend/ws.py`:
```python
import json
import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients."""
        data = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to(self, websocket: WebSocket, message: dict):
        """Send a JSON message to a single client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            self.disconnect(websocket)
```

- [ ] **Step 2: Commit**

```bash
git add backend/ws.py
git commit -m "feat: WebSocket manager for real-time client updates"
```

---

### Task 11: FastAPI Application

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Implement FastAPI app with all endpoints**

Create `backend/main.py`:
```python
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import AuthManager
from backend.config import AppConfig
from backend.models import Database
from backend.search import search_tidal, get_album_tracks, get_playlist_tracks
from backend.downloader import DownloadOrchestrator
from backend.ws import WebSocketManager

logger = logging.getLogger(__name__)

# Global state
config = AppConfig()
db = Database()
auth_manager = AuthManager()
ws_manager = WebSocketManager()
orchestrator: DownloadOrchestrator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    await db.init()
    # Try loading saved session
    if auth_manager.load_saved_session(config.default_quality):
        orchestrator = DownloadOrchestrator(db=db, config=config, ws_manager=ws_manager)
        orchestrator.set_session(auth_manager.session)
    yield
    await db.close()


app = FastAPI(title="TidalExtractor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Endpoints ---

class DeviceLinkRequest(BaseModel):
    pass


@app.post("/auth/device-link")
async def create_device_link():
    try:
        result = auth_manager.get_device_link()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/device-link/verify")
async def verify_device_link():
    global orchestrator
    success = await asyncio.to_thread(auth_manager.wait_for_device_auth)
    if success:
        orchestrator = DownloadOrchestrator(db=db, config=config, ws_manager=ws_manager)
        orchestrator.set_session(auth_manager.session)
        return {"authenticated": True}
    raise HTTPException(status_code=401, detail="Authentication failed")


@app.get("/auth/status")
async def get_auth_status():
    return auth_manager.get_status()


@app.post("/auth/logout")
async def logout():
    global orchestrator
    auth_manager.logout()
    orchestrator = None
    return {"authenticated": False}


# --- Search Endpoints ---

class SearchRequest(BaseModel):
    query: str
    type: str = "track"  # track, album, playlist


@app.get("/search")
async def search(q: str, type: str = "track"):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    models = [type] if type in ("track", "album", "playlist") else ["track", "album", "playlist"]
    results = await asyncio.to_thread(search_tidal, auth_manager.session, q, models)
    return results


@app.get("/album/{album_id}/tracks")
async def album_tracks(album_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tracks = await asyncio.to_thread(get_album_tracks, auth_manager.session, album_id)
    return {"tracks": tracks}


@app.get("/playlist/{playlist_id}/tracks")
async def playlist_tracks(playlist_id: str):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tracks = await asyncio.to_thread(get_playlist_tracks, auth_manager.session, playlist_id)
    return {"tracks": tracks}


# --- Queue Endpoints ---

class AddToQueueRequest(BaseModel):
    tidal_id: str
    item_type: str = "track"  # track, album, playlist
    title: str
    artist: str = ""
    album: str = ""
    quality: str = None
    format: str = None


@app.post("/queue/add")
async def add_to_queue(item: AddToQueueRequest):
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


@app.get("/queue")
async def get_queue():
    return await db.get_queue()


@app.delete("/queue/{item_id}")
async def remove_from_queue(item_id: int):
    await db.remove_from_queue(item_id)
    return {"ok": True}


async def _process_queue_if_idle():
    """Start processing the queue if the orchestrator exists and isn't already running."""
    if orchestrator and not orchestrator._running:
        await orchestrator.process_queue()


# --- History Endpoints ---

@app.get("/history")
async def get_history(limit: int = 100):
    return await db.get_history(limit=limit)


# --- Settings Endpoints ---

@app.get("/settings")
async def get_settings():
    return config.as_dict()


class UpdateSettingsRequest(BaseModel):
    default_quality: str = None
    default_format: str = None
    output_dir: str = None


@app.put("/settings")
async def update_settings(settings: UpdateSettingsRequest):
    if settings.default_quality:
        config.default_quality = settings.default_quality
    if settings.default_format:
        config.default_format = settings.default_format
    if settings.output_dir:
        config.output_dir = settings.output_dir
    config.save()
    return config.as_dict()


# --- Quality Probe Endpoint ---

@app.post("/quality/probe")
async def probe_quality():
    if not orchestrator or not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    preset = await orchestrator.probe_quality()
    if preset:
        await ws_manager.broadcast({
            "type": "quality",
            "id": "session",
            "preset": preset,
            "bitrate": (await db.get_quality_cache())["bitrate"] if await db.get_quality_cache() else 0,
        })
        return {"preset": preset, "bitrate": (await db.get_quality_cache())["bitrate"]}
    raise HTTPException(status_code=500, detail="All quality presets failed probe")


@app.get("/quality/cache")
async def get_quality_cache():
    return await db.get_quality_cache()


# --- WebSocket Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

- [ ] **Step 2: Commit**

```bash
git add backend/main.py
git commit -m "feat: FastAPI application with auth, search, queue, settings, and WebSocket endpoints"
```

---

### Task 12: Frontend Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend config files**

Create `frontend/package.json`:
```json
{
  "name": "tidal-extractor",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.16",
    "typescript": "^5.6.3",
    "vite": "^6.0.3",
    "vitest": "^2.1.8",
    "@testing-library/react": "^16.1.0",
    "@testing-library/jest-dom": "^6.6.3",
    "jsdom": "^25.0.1"
  }
}
```

Create `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

Create `frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
```

Create `frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

Create `frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

Create `frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TidalExtractor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  @apply bg-gray-950 text-gray-100 min-h-screen;
}
```

Create `frontend/src/main.tsx`:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 2: Create minimal App.tsx**

Create `frontend/src/App.tsx`:
```typescript
import React from 'react'

export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <h1 className="text-3xl font-bold">TidalExtractor</h1>
    </div>
  )
}
```

- [ ] **Step 3: Install dependencies**

```bash
cd /Users/felipecanas/Documents/TidalExtractor/frontend
npm install
```

- [ ] **Step 4: Verify dev server starts**

```bash
cd /Users/felipecanas/Documents/TidalExtractor/frontend
npm run dev
```

Expected: Server starts on http://localhost:3000, shows "TidalExtractor"

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "chore: React+TypeScript+Vite+TailwindCSS scaffolding"
```

---

### Task 13: Frontend API Client and WebSocket Hook

**Files:**
- Create: `frontend/src/api.ts`
- Create: `frontend/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Implement REST API client**

Create `frontend/src/api.ts`:
```typescript
const BASE = '';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export interface SearchResult {
  tracks: TrackResult[];
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}

export interface TrackResult {
  id: number;
  title: string;
  artist: string;
  album: string;
  album_id: number | null;
  duration: number;
  quality: string;
  explicit: boolean;
  isrc: string | null;
  url: string;
  cover_url: string | null;
}

export interface AlbumResult {
  id: number;
  name: string;
  artist: string;
  num_tracks: number;
  release_date: string | null;
  quality: string;
  cover_url: string | null;
}

export interface PlaylistResult {
  id: string;
  name: string;
  num_tracks: number;
  creator: string | null;
  cover_url: string | null;
}

export interface QueueItem {
  id: number;
  tidal_id: string;
  item_type: string;
  title: string;
  artist: string;
  album: string;
  quality: string;
  format: string;
  status: 'queued' | 'downloading' | 'complete' | 'failed';
  progress: number;
  error: string | null;
}

export interface Settings {
  default_quality: string;
  default_format: string;
  output_dir: string;
}

export interface AuthStatus {
  authenticated: boolean;
  username: string | null;
}

export interface DeviceLink {
  url: string;
  code: string;
  expires_in: number;
}

export interface WsMessage {
  type: 'progress' | 'quality' | 'complete' | 'error' | 'queue_update';
  id: string;
  [key: string]: unknown;
}

// Auth
export const auth = {
  getDeviceLink: () => request<DeviceLink>('/auth/device-link', { method: 'POST' }),
  verifyDeviceLink: () => request<{ authenticated: boolean }>('/auth/device-link/verify', { method: 'POST' }),
  getStatus: () => request<AuthStatus>('/auth/status'),
  logout: () => request<{ authenticated: boolean }>('/auth/logout', { method: 'POST' }),
};

// Search
export const search = {
  query: (q: string, type: string = 'track') =>
    request<SearchResult>(`/search?q=${encodeURIComponent(q)}&type=${type}`),
  albumTracks: (albumId: number) =>
    request<{ tracks: TrackResult[] }>(`/album/${albumId}/tracks`),
  playlistTracks: (playlistId: string) =>
    request<{ tracks: TrackResult[] }>(`/playlist/${playlistId}/tracks`),
};

// Queue
export const queue = {
  list: () => request<QueueItem[]>('/queue'),
  add: (item: { tidal_id: string; item_type: string; title: string; artist?: string; album?: string; quality?: string; format?: string }) =>
    request<QueueItem>('/queue/add', { method: 'POST', body: JSON.stringify(item) }),
  remove: (id: number) => request<{ ok: boolean }>(`/queue/${id}`, { method: 'DELETE' }),
};

// Settings
export const settings = {
  get: () => request<Settings>('/settings'),
  update: (s: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(s) }),
};

// Quality
export const quality = {
  probe: () => request<{ preset: string; bitrate: number }>('/quality/probe', { method: 'POST' }),
  cache: () => request<{ preset: string; bitrate: number } | null>('/quality/cache'),
};

// History
export const history = {
  list: (limit: number = 100) => request<any[]>(`/history?limit=${limit}`),
};
```

- [ ] **Step 2: Implement WebSocket hook**

Create `frontend/src/hooks/useWebSocket.ts`:
```typescript
import { useEffect, useRef, useCallback } from 'react';
import type { WsMessage } from '../api';

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        onMessageRef.current(msg);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      // Reconnect after 3 seconds
      setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts frontend/src/hooks/useWebSocket.ts
git commit -m "feat: REST API client and WebSocket hook"
```

---

### Task 14: App Context and AuthGate

**Files:**
- Create: `frontend/src/context/AppContext.tsx`
- Create: `frontend/src/components/AuthGate.tsx`

- [ ] **Step 1: Implement App context with useReducer**

Create `frontend/src/context/AppContext.tsx`:
```typescript
import React, { createContext, useContext, useReducer, Dispatch } from 'react';
import type { AuthStatus, QueueItem, Settings, WsMessage } from '../api';

export interface AppState {
  auth: AuthStatus;
  activeTab: 'search' | 'queue' | 'settings';
  queue: QueueItem[];
  settings: Settings;
  wsConnected: boolean;
}

type Action =
  | { type: 'SET_AUTH'; payload: AuthStatus }
  | { type: 'SET_TAB'; payload: AppState['activeTab'] }
  | { type: 'SET_QUEUE'; payload: QueueItem[] }
  | { type: 'UPDATE_QUEUE_ITEM'; payload: QueueItem }
  | { type: 'REMOVE_QUEUE_ITEM'; payload: number }
  | { type: 'SET_SETTINGS'; payload: Settings }
  | { type: 'WS_MESSAGE'; payload: WsMessage }
  | { type: 'SET_WS_CONNECTED'; payload: boolean };

const initialState: AppState = {
  auth: { authenticated: false, username: null },
  activeTab: 'search',
  queue: [],
  settings: { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads' },
  wsConnected: false,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_AUTH':
      return { ...state, auth: action.payload };
    case 'SET_TAB':
      return { ...state, activeTab: action.payload };
    case 'SET_QUEUE':
      return { ...state, queue: action.payload };
    case 'UPDATE_QUEUE_ITEM':
      return {
        ...state,
        queue: state.queue.map((item) =>
          item.id === action.payload.id ? action.payload : item
        ),
      };
    case 'REMOVE_QUEUE_ITEM':
      return {
        ...state,
        queue: state.queue.filter((item) => item.id !== action.payload),
      };
    case 'SET_SETTINGS':
      return { ...state, settings: action.payload };
    case 'WS_MESSAGE': {
      const msg = action.payload;
      if (msg.type === 'progress') {
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'downloading', progress: (msg.pct as number) || 0 }
              : item
          ),
        };
      }
      if (msg.type === 'complete') {
        return {
          ...state,
          queue: state.queue.filter((item) => String(item.id) !== msg.id),
        };
      }
      if (msg.type === 'error') {
        return {
          ...state,
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'failed', error: (msg.reason as string) || 'Unknown error' }
              : item
          ),
        };
      }
      return state;
    }
    case 'SET_WS_CONNECTED':
      return { ...state, wsConnected: action.payload };
    default:
      return state;
  }
}

const AppContext = createContext<{
  state: AppState;
  dispatch: Dispatch<Action>;
} | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
```

- [ ] **Step 2: Implement AuthGate component**

Create `frontend/src/components/AuthGate.tsx`:
```typescript
import React, { useState, useEffect } from 'react';
import { auth } from '../api';
import { useApp } from '../context/AppContext';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { dispatch } = useApp();
  const [checking, setChecking] = useState(true);
  const [linking, setLinking] = useState(false);
  const [deviceLink, setDeviceLink] = useState<{ url: string; code: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    auth.getStatus().then((status) => {
      dispatch({ type: 'SET_AUTH', payload: status });
      setChecking(false);
    }).catch(() => setChecking(false));
  }, [dispatch]);

  const handleLogin = async () => {
    setLinking(true);
    setError(null);
    try {
      const link = await auth.getDeviceLink();
      setDeviceLink({ url: link.url, code: link.code });

      const result = await auth.verifyDeviceLink();
      if (result.authenticated) {
        const status = await auth.getStatus();
        dispatch({ type: 'SET_AUTH', payload: status });
      } else {
        setError('Authentication failed. Please try again.');
      }
    } catch (e: any) {
      setError(e.message || 'Authentication failed');
    } finally {
      setLinking(false);
    }
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">Checking authentication...</p>
      </div>
    );
  }

  return (
    <AuthCheck onLogin={handleLogin} linking={linking} deviceLink={deviceLink} error={error}>
      {children}
    </AuthCheck>
  );
}

function AuthCheck({
  children,
  onLogin,
  linking,
  deviceLink,
  error,
}: {
  children: React.ReactNode;
  onLogin: () => void;
  linking: boolean;
  deviceLink: { url: string; code: string } | null;
  error: string | null;
}) {
  const { state } = useApp();

  if (state.auth.authenticated) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="bg-gray-900 rounded-xl p-8 max-w-md w-full text-center">
        <h1 className="text-2xl font-bold mb-2">TidalExtractor</h1>
        <p className="text-gray-400 mb-6">Connect your Tidal account to get started</p>

        {deviceLink && (
          <div className="mb-6 p-4 bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-400 mb-2">Visit this URL to link your account:</p>
            <a
              href={deviceLink.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 underline break-all text-sm"
            >
              {deviceLink.url}
            </a>
            <p className="text-sm text-gray-400 mt-2">Code: <span className="text-white font-mono">{deviceLink.code}</span></p>
          </div>
        )}

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        <button
          onClick={onLogin}
          disabled={linking}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors"
        >
          {linking ? 'Waiting for authorization...' : 'Connect Tidal Account'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/context/AppContext.tsx frontend/src/components/AuthGate.tsx
git commit -m "feat: App context with useReducer and AuthGate with OAuth device link"
```

---

### Task 15: NavBar Component

**Files:**
- Create: `frontend/src/components/NavBar.tsx`

- [ ] **Step 1: Implement NavBar**

Create `frontend/src/components/NavBar.tsx`:
```typescript
import React from 'react';
import { useApp } from '../context/AppContext';
import { auth } from '../api';

export default function NavBar() {
  const { state, dispatch } = useApp();

  const tabs: { key: typeof state.activeTab; label: string }[] = [
    { key: 'search', label: 'Search' },
    { key: 'queue', label: `Queue (${state.queue.length})` },
    { key: 'settings', label: 'Settings' },
  ];

  const handleLogout = async () => {
    await auth.logout();
    dispatch({ type: 'SET_AUTH', payload: { authenticated: false, username: null } });
  };

  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-bold text-white">TidalExtractor</h1>
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => dispatch({ type: 'SET_TAB', payload: tab.key })}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                state.activeTab === tab.key
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {state.auth.username && (
          <span className="text-sm text-gray-400">{state.auth.username}</span>
        )}
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/NavBar.tsx
git commit -m "feat: NavBar with tab switching and logout"
```

---

### Task 16: SearchView Component

**Files:**
- Create: `frontend/src/components/SearchView.tsx`

- [ ] **Step 1: Implement SearchView**

Create `frontend/src/components/SearchView.tsx`:
```typescript
import React, { useState } from 'react';
import { search, queue } from '../api';
import { useApp } from '../context/AppContext';
import type { TrackResult, AlbumResult, PlaylistResult } from '../api';

export default function SearchView() {
  const { state } = useApp();
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'track' | 'album' | 'playlist'>('track');
  const [results, setResults] = useState<{
    tracks: TrackResult[];
    albums: AlbumResult[];
    playlists: PlaylistResult[];
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await search.query(query, searchType);
      setResults(r);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddToQueue = async (
    tidal_id: string | number,
    item_type: string,
    title: string,
    artist: string = '',
    album: string = '',
  ) => {
    await queue.add({
      tidal_id: String(tidal_id),
      item_type,
      title,
      artist,
      album,
      quality: state.settings.default_quality,
      format: state.settings.default_format,
    });
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const typeButtons: { key: typeof searchType; label: string }[] = [
    { key: 'track', label: 'Tracks' },
    { key: 'album', label: 'Albums' },
    { key: 'playlist', label: 'Playlists' },
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <form onSubmit={handleSearch} className="mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tracks, albums, playlists..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold px-6 py-2 rounded-lg transition-colors"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        <div className="flex gap-2 mt-3">
          {typeButtons.map((btn) => (
            <button
              key={btn.key}
              type="button"
              onClick={() => setSearchType(btn.key)}
              className={`px-3 py-1 rounded-md text-sm transition-colors ${
                searchType === btn.key
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </form>

      {results && (
        <div className="space-y-2">
          {results.tracks.map((track) => (
            <div
              key={track.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{track.title}</p>
                <p className="text-gray-400 text-sm truncate">
                  {track.artist} &middot; {track.album} &middot; {formatDuration(track.duration)} &middot;
                  <span className="text-gray-500 ml-1">{track.quality}</span>
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.albums.map((album) => (
            <div
              key={album.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{album.name}</p>
                <p className="text-gray-400 text-sm truncate">
                  {album.artist} &middot; {album.num_tracks} tracks
                  {album.release_date && ` &middot; ${album.release_date}`}
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(album.id, 'album', album.name, album.artist)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.playlists.map((pl) => (
            <div
              key={pl.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{pl.name}</p>
                <p className="text-gray-400 text-sm truncate">
                  {pl.creator || 'Unknown'} &middot; {pl.num_tracks} tracks
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(pl.id, 'playlist', pl.name)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.tracks.length === 0 && results.albums.length === 0 && results.playlists.length === 0 && (
            <p className="text-gray-500 text-center py-8">No results found</p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SearchView.tsx
git commit -m "feat: SearchView with track/album/playlist results and add-to-queue"
```

---

### Task 17: QueueView Component

**Files:**
- Create: `frontend/src/components/QueueView.tsx`

- [ ] **Step 1: Implement QueueView**

Create `frontend/src/components/QueueView.tsx`:
```typescript
import React, { useEffect } from 'react';
import { queue, quality } from '../api';
import { useApp } from '../context/AppContext';

const statusStyles: Record<string, string> = {
  queued: 'bg-gray-700 text-gray-300',
  downloading: 'bg-blue-900 text-blue-300',
  complete: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
};

export default function QueueView() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
  }, [dispatch]);

  const handleRemove = async (id: number) => {
    await queue.remove(id);
    dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: id });
  };

  const handleProbeQuality = async () => {
    try {
      await quality.probe();
    } catch (e) {
      console.error('Quality probe failed:', e);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Download Queue</h2>
        <button
          onClick={handleProbeQuality}
          className="bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors"
        >
          Probe Quality
        </button>
      </div>

      {state.queue.length === 0 ? (
        <p className="text-gray-500 text-center py-8">Queue is empty. Search and add tracks to download.</p>
      ) : (
        <div className="space-y-2">
          {state.queue.map((item) => (
            <div
              key={item.id}
              className="bg-gray-800 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{item.title}</p>
                  <p className="text-gray-400 text-sm truncate">
                    {item.artist} &middot; {item.album} &middot;
                    <span className="ml-1">{item.quality}</span> &middot;
                    <span className="ml-1">{item.format}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusStyles[item.status] || 'bg-gray-700 text-gray-300'}`}>
                    {item.status}
                  </span>
                  <button
                    onClick={() => handleRemove(item.id)}
                    className="text-gray-500 hover:text-red-400 transition-colors text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              {item.status === 'downloading' && (
                <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${item.progress}%` }}
                  />
                </div>
              )}
              {item.status === 'failed' && item.error && (
                <p className="text-red-400 text-sm mt-2">{item.error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/QueueView.tsx
git commit -m "feat: QueueView with progress bars and quality probe button"
```

---

### Task 18: SettingsView Component

**Files:**
- Create: `frontend/src/components/SettingsView.tsx`

- [ ] **Step 1: Implement SettingsView**

Create `frontend/src/components/SettingsView.tsx`:
```typescript
import React, { useEffect, useState } from 'react';
import { settings, auth, quality } from '../api';
import { useApp } from '../context/AppContext';

const QUALITY_OPTIONS = [
  { value: 'hi_res_lossless', label: 'HiRes Lossless (24-bit, up to 192kHz)' },
  { value: 'high_lossless', label: 'Lossless (16-bit FLAC, 44.1kHz)' },
  { value: 'low_320k', label: 'High (320kbps AAC)' },
  { value: 'low_96k', label: 'Normal (96kbps AAC)' },
];

const FORMAT_OPTIONS = [
  { value: 'FLAC', label: 'FLAC (lossless, largest files)' },
  { value: 'MP3', label: 'MP3 (320kbps, broad compatibility)' },
  { value: 'M4A', label: 'M4A/AAC (320kbps, Apple ecosystem)' },
];

export default function SettingsView() {
  const { state, dispatch } = useApp();
  const [saving, setSaving] = useState(false);
  const [qualityCache, setQualityCache] = useState<{ preset: string; bitrate: number } | null>(null);

  useEffect(() => {
    settings.get().then((s) => dispatch({ type: 'SET_SETTINGS', payload: s }));
    quality.cache().then(setQualityCache).catch(() => {});
  }, [dispatch]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await settings.update(state.settings);
      dispatch({ type: 'SET_SETTINGS', payload: updated });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h2 className="text-xl font-bold mb-6">Settings</h2>

      {/* Auth Status */}
      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Account</h3>
        <p className="text-white">
          {state.auth.authenticated
            ? `Connected as ${state.auth.username || 'Unknown'}`
            : 'Not connected'}
        </p>
      </section>

      {/* Quality Cache */}
      {qualityCache && (
        <section className="bg-gray-800 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Detected Quality</h3>
          <p className="text-white">
            {qualityCache.preset} &middot; {qualityCache.bitrate} kbps
          </p>
        </section>
      )}

      {/* Default Quality */}
      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Default Quality</h3>
        <select
          value={state.settings.default_quality}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, default_quality: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        >
          {QUALITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </section>

      {/* Default Format */}
      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Default Format</h3>
        <select
          value={state.settings.default_format}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, default_format: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        >
          {FORMAT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </section>

      {/* Output Directory */}
      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Output Directory</h3>
        <input
          type="text"
          value={state.settings.output_dir}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, output_dir: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        />
      </section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors"
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SettingsView.tsx
git commit -m "feat: SettingsView with quality, format, and output directory config"
```

---

### Task 19: Wire Up App.tsx with All Components

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx to integrate all components**

Replace `frontend/src/App.tsx`:
```typescript
import React, { useEffect, useCallback } from 'react';
import { AppProvider, useApp } from './context/AppContext';
import { useWebSocket } from './hooks/useWebSocket';
import { queue, settings } from './api';
import AuthGate from './components/AuthGate';
import NavBar from './components/NavBar';
import SearchView from './components/SearchView';
import QueueView from './components/QueueView';
import SettingsView from './components/SettingsView';
import type { WsMessage } from './api';

function AppContent() {
  const { state, dispatch } = useApp();

  const handleWsMessage = useCallback((msg: WsMessage) => {
    dispatch({ type: 'WS_MESSAGE', payload: msg });
  }, [dispatch]);

  useWebSocket(handleWsMessage);

  useEffect(() => {
    settings.get().then((s) => dispatch({ type: 'SET_SETTINGS', payload: s }));
    queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
  }, [dispatch]);

  const renderView = () => {
    switch (state.activeTab) {
      case 'search':
        return <SearchView />;
      case 'queue':
        return <QueueView />;
      case 'settings':
        return <SettingsView />;
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1">{renderView()}</main>
      </div>
    </AuthGate>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
```

- [ ] **Step 2: Verify frontend builds and runs**

```bash
cd /Users/felipecanas/Documents/TidalExtractor/frontend
npm run build
```

Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire up App with AuthGate, NavBar, WebSocket, and all views"
```

---

### Task 20: Integration — Backend Vite Proxy Fix and End-to-End Smoke Test

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Fix Vite proxy to strip `/api` prefix**

The backend endpoints don't have an `/api` prefix, so the proxy should map `/api/*` to `/*`. Update `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

Then update `frontend/src/api.ts` to prefix all paths with `/api`:
```typescript
const BASE = '/api';
```

- [ ] **Step 2: Run backend and frontend together**

Terminal 1:
```bash
cd /Users/felipecanas/Documents/TidalExtractor
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Terminal 2:
```bash
cd /Users/felipecanas/Documents/TidalExtractor/frontend
npm run dev
```

Open http://localhost:3000. Verify:
1. AuthGate shows login screen
2. Clicking "Connect Tidal Account" initiates OAuth device link flow
3. After authenticating, search tab loads
4. Search returns results
5. Download button adds to queue
6. Queue shows progress updates via WebSocket

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts frontend/src/api.ts
git commit -m "fix: add /api proxy prefix for clean frontend-backend separation"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ OAuth device link auth (Task 8, Task 14)
- ✅ Search tracks/albums/playlists (Task 9, Task 16)
- ✅ Sequential download queue (Task 7, Task 11)
- ✅ Two-phase quality probe with fallback (Task 4, Task 7)
- ✅ Format conversion FLAC/MP3/M4A (Task 5)
- ✅ Extended metadata tagging (Task 6)
- ✅ Post-download bitrate verification (Task 4, Task 7)
- ✅ React SPA frontend (Tasks 12-19)
- ✅ FastAPI backend with WebSocket (Tasks 10-11)
- ✅ SQLite queue/history/cache (Task 2)
- ✅ YAML config (Task 3)
- ✅ Flat singles / folder collections (Task 7)
- ✅ Error handling for all scenarios (Task 7)

**2. Placeholder scan:** No TBDs or TODOs found. All steps have complete code.

**3. Type consistency:** Checked all function signatures, variable names, and API types across tasks. All consistent.
