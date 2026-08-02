# DJ Metadata Tagging (FreqBlog BPM/Key on Download) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write BPM and musical key (Camelot notation) into every downloaded track's standard audio tags, sourced from FreqBlog first and falling back to local audio analysis, so downloads are usable directly in Rekordbox, Serato, and VirtualDJ.

**Architecture:** Backend-only. `backend/tagger.py` gets a new `tag_dj_metadata()` function replacing `tag_key()`. `backend/downloader.py` gets a new `_resolve_dj_metadata()` helper that tries `backend.freqblog.lookup_track_metadata()` first and falls back to the existing `backend.key_detection.detect_key()`, then calls `tag_dj_metadata()` with the result. No new dependencies, no new DB tables, no new Settings/UI.

**Tech Stack:** Python, FastAPI, mutagen, pytest / pytest-asyncio

## Global Constraints

- No new settings, config fields, or frontend changes — this runs automatically on every download, same as today's unconditional local key detection.
- Camelot notation only in the key tag — no alternate notation, no user preference.
- BPM must be written as an **integer** to the tag (`round()` before writing) — MP4's `tmpo` atom raises on a float.
- Reuse `backend.freqblog.lookup_track_metadata(title, artist)` and `backend.key_detection.detect_key(path)` as-is — do not modify either.
- `Database.set_key_cache()` already accepts a `bpm` kwarg (see `backend/models.py:195-207`) — no schema/migration work needed, just pass it.
- Full spec: `docs/superpowers/specs/2026-08-02-dj-metadata-tagging-design.md`.

---

### Task 1: Replace `tag_key` with `tag_dj_metadata` in `backend/tagger.py`

**Files:**
- Modify: `backend/tagger.py:27-52` (the existing `tag_key` function)
- Test: `backend/tests/test_tagger.py`

**Interfaces:**
- Produces: `tag_dj_metadata(file_path: str, camelot: Optional[str], bpm: Optional[float] = None) -> None` — writes the Camelot code to the standard key tag and the rounded BPM to the standard BPM tag, per format. Missing/`None` values are skipped (no tag written for that field). Never raises — logs a warning on failure, same as `tag_key` did.

This task only adds the new function; `tag_key` and its caller in `downloader.py` are left untouched until Task 2, so the full test suite stays green after this task.

- [ ] **Step 1: Add an M4A test fixture to `backend/tests/test_tagger.py`**

Add this alongside the existing `_generate_test_flac` / `_generate_test_mp3` / `test_flac` / `test_mp3` fixtures near the top of the file:

```python
def _generate_test_m4a(path: str):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-c:a", "aac", "-y", path],
        capture_output=True, check=True,
    )


@pytest.fixture
def test_m4a(tmp_path):
    m4a_path = str(tmp_path / "test.m4a")
    _generate_test_m4a(m4a_path)
    return m4a_path
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_tagger.py` (update the import line at the top from `from backend.tagger import tag_file` to `from backend.tagger import tag_file, tag_dj_metadata`):

```python
@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_dj_metadata_flac(test_flac):
    tag_dj_metadata(test_flac, "8A", 128.4)
    f = mutagen.File(test_flac)
    assert f["initialkey"][0] == "8A"
    assert f["bpm"][0] == "128"
    assert "camelot" not in f  # no redundant second field


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_dj_metadata_mp3(test_mp3):
    tag_dj_metadata(test_mp3, "8A", 128.4)
    f = mutagen.File(test_mp3)
    assert f["TKEY"][0] == "8A"
    assert str(f["TBPM"][0]) == "128"
    assert "TXXX:CAMELOT" not in f


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_dj_metadata_m4a_rounds_float_bpm(test_m4a):
    """MP4's tmpo atom requires an int — a raw float BPM must not raise."""
    tag_dj_metadata(test_m4a, "8A", 127.85)
    f = mutagen.File(test_m4a)
    assert f["----:com.apple.iTunes:initialkey"][0] == b"8A"
    assert f["tmpo"][0] == 128


@pytest.mark.skipif(
    subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0,
    reason="ffmpeg not installed"
)
def test_tag_dj_metadata_skips_none_values(test_flac):
    tag_dj_metadata(test_flac, None, None)
    f = mutagen.File(test_flac)
    assert "initialkey" not in f
    assert "bpm" not in f
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest backend/tests/test_tagger.py -v`
Expected: FAIL with `ImportError: cannot import name 'tag_dj_metadata'`

- [ ] **Step 4: Replace `tag_key` with `tag_dj_metadata` in `backend/tagger.py`**

Replace the entire existing `tag_key` function (currently `backend/tagger.py:27-52`, including its local `from mutagen.id3 import TKEY, TXXX` import — `TKEY` and `TBPM` are already imported at module level on line 7, so no import is needed inside the new function) with:

```python
def tag_dj_metadata(file_path: str, camelot: Optional[str], bpm: Optional[float] = None):
    """Write DJ-standard Key (Camelot notation) and BPM tags for Rekordbox/Serato/VirtualDJ."""
    ext = Path(file_path).suffix.lower()
    bpm_int = round(bpm) if bpm else None
    try:
        if ext == ".flac":
            f = FLAC(file_path)
            if camelot:
                f["initialkey"] = [camelot]
            if bpm_int:
                f["bpm"] = [str(bpm_int)]
            f.save()
        elif ext == ".mp3":
            f = MP3(file_path)
            if f.tags is None:
                f.add_tags()
            if camelot:
                f.tags["TKEY"] = TKEY(encoding=3, text=camelot)
            if bpm_int:
                f.tags["TBPM"] = TBPM(encoding=3, text=str(bpm_int))
            f.save()
        elif ext == ".m4a":
            f = MP4(file_path)
            if f.tags is None:
                f.add_tags()
            if camelot:
                f.tags["----:com.apple.iTunes:initialkey"] = [camelot.encode("utf-8")]
            if bpm_int:
                f.tags["tmpo"] = [bpm_int]
            f.save()
    except Exception as e:
        logger.warning(f"Failed to write DJ metadata tags to {file_path}: {e}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest backend/tests/test_tagger.py -v`
Expected: PASS (all tests, including the pre-existing `test_tag_flac` / `test_tag_mp3` / `test_tag_with_cover_art` / `test_tag_skips_none_values` which are untouched)

- [ ] **Step 6: Commit**

```bash
git add backend/tagger.py backend/tests/test_tagger.py
git commit -m "feat: add tag_dj_metadata for Camelot key + BPM tagging"
```

---

### Task 2: Wire FreqBlog→local hybrid lookup into `download_track`

**Files:**
- Modify: `backend/downloader.py:16,18` (imports) and `:232-239` (the post-download key-detection block)
- Modify: `backend/tagger.py` (delete the now-unused `tag_key`, which Task 1 left in place)
- Test: `backend/tests/test_downloader.py`

**Interfaces:**
- Consumes: `tag_dj_metadata(file_path, camelot, bpm)` from Task 1; `lookup_track_metadata(track_title, artist) -> Optional[dict]` from `backend/freqblog.py` (already returns `{bpm, bpm_confidence, key, key_int, mode, camelot, open_key, key_confidence, source}` on hit, `None` on miss/error); `detect_key(audio_path) -> dict` from `backend/key_detection.py` (already returns `{key, camelot, bpm, confidence}`).
- Produces: `_resolve_dj_metadata(final_path: str, title: str, artist: str) -> dict` — module-level async function in `backend/downloader.py` returning `{"key": str, "camelot": str, "bpm": float, "confidence": float, "source": "freqblog" | "local"}`.

- [ ] **Step 1: Write the failing tests for `_resolve_dj_metadata`**

In `backend/tests/test_downloader.py`, change the import line:

```python
from unittest.mock import MagicMock, patch, AsyncMock
from backend.downloader import DownloadOrchestrator, extract_track_metadata, _resolve_auto_quality, _resolve_dj_metadata
```

Append these two tests:

```python
@pytest.mark.asyncio
async def test_resolve_dj_metadata_prefers_freqblog():
    with patch("backend.downloader.lookup_track_metadata", new=AsyncMock(return_value={
        "key": "Am", "camelot": "8A", "bpm": 128.0, "key_confidence": 0.9,
    })), patch("backend.downloader._detect_key") as mock_local:
        result = await _resolve_dj_metadata("fake.flac", "Title", "Artist")

    assert result == {"key": "Am", "camelot": "8A", "bpm": 128.0, "confidence": 0.9, "source": "freqblog"}
    mock_local.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_dj_metadata_falls_back_to_local():
    with patch("backend.downloader.lookup_track_metadata", new=AsyncMock(return_value=None)), \
         patch("backend.downloader._detect_key",
               return_value={"key": "C", "camelot": "8B", "confidence": 1.0, "bpm": 120.0}):
        result = await _resolve_dj_metadata("fake.flac", "Title", "Artist")

    assert result == {"key": "C", "camelot": "8B", "bpm": 120.0, "confidence": 1.0, "source": "local"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest backend/tests/test_downloader.py -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_dj_metadata'`

- [ ] **Step 3: Update imports in `backend/downloader.py`**

Change line 16:
```python
from backend.tagger import tag_file, tag_key
```
to:
```python
from backend.tagger import tag_file, tag_dj_metadata
from backend.freqblog import lookup_track_metadata
```

- [ ] **Step 4: Add `_resolve_dj_metadata` to `backend/downloader.py`**

Add this module-level function right after `_resolve_auto_quality` (which currently ends around line 45, just before the `# Track metadata extraction function` comment):

```python
async def _resolve_dj_metadata(final_path: str, title: str, artist: str) -> dict:
    """Resolve BPM + Camelot key for a downloaded track: FreqBlog first, local audio analysis as fallback."""
    freq_result = await lookup_track_metadata(title, artist)
    if freq_result and freq_result.get("bpm") and freq_result.get("camelot"):
        return {
            "key": freq_result["key"],
            "camelot": freq_result["camelot"],
            "bpm": freq_result["bpm"],
            "confidence": freq_result.get("key_confidence") or 1.0,
            "source": "freqblog",
        }
    local_result = await asyncio.to_thread(_detect_key, final_path)
    return {
        "key": local_result["key"],
        "camelot": local_result["camelot"],
        "bpm": local_result["bpm"],
        "confidence": local_result["confidence"],
        "source": "local",
    }
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest backend/tests/test_downloader.py -v -k resolve_dj_metadata`
Expected: PASS

- [ ] **Step 6: Replace the post-download tagging block in `download_track`**

Replace the existing block (currently `backend/downloader.py:232-239`):

```python
        if ext in (".flac", ".mp3", ".m4a"):
            try:
                key_result = await asyncio.to_thread(_detect_key, final_path)
                h = file_hash(final_path)
                await self.db.set_key_cache(h, key_result["key"], key_result["camelot"], key_result["confidence"])
                await asyncio.to_thread(tag_key, final_path, key_result["key"], key_result["camelot"])
            except Exception as e:
                logger.warning(f"Key detection failed for {final_path}: {e}")
```

with:

```python
        if ext in (".flac", ".mp3", ".m4a"):
            try:
                dj = await _resolve_dj_metadata(final_path, metadata["title"], metadata["artist"])
                h = file_hash(final_path)
                await self.db.set_key_cache(h, dj["key"], dj["camelot"], dj["confidence"], bpm=dj["bpm"])
                await asyncio.to_thread(tag_dj_metadata, final_path, dj["camelot"], dj["bpm"])
                logger.info(f"DJ metadata ({dj['source']}): {final_path} — BPM={dj['bpm']}, Key={dj['camelot']}")
            except Exception as e:
                logger.warning(f"DJ metadata tagging failed for {final_path}: {e}")
```

- [ ] **Step 7: Update the existing integration test's mocks**

In `test_download_track_removes_tmp_file_after_conversion`, replace:

```python
    with patch("httpx.AsyncClient", return_value=FakeClient()), \
         patch("backend.downloader.tag_file"), \
         patch("backend.downloader.tag_key"), \
         patch("backend.downloader._detect_key",
               return_value={"key": "C", "camelot": "8B", "confidence": 1.0}), \
         patch("backend.downloader.file_hash", return_value="hash"):
```

with:

```python
    with patch("httpx.AsyncClient", return_value=FakeClient()), \
         patch("backend.downloader.tag_file"), \
         patch("backend.downloader.tag_dj_metadata"), \
         patch("backend.downloader.lookup_track_metadata", new=AsyncMock(return_value=None)), \
         patch("backend.downloader._detect_key",
               return_value={"key": "C", "camelot": "8B", "confidence": 1.0, "bpm": 120.0}), \
         patch("backend.downloader.file_hash", return_value="hash"):
```

- [ ] **Step 8: Delete the now-unused `tag_key` from `backend/tagger.py`**

`tag_key` (originally `backend/tagger.py:27-52`, already replaced in content by `tag_dj_metadata` from Task 1 — check whether it's still present under its old name anywhere else). Confirm no remaining references:

Run: `grep -rn "tag_key" backend/ --include=*.py`
Expected: no output (Task 1 already replaced the function body; this step just confirms no stale caller survived).

- [ ] **Step 9: Run the full backend test suite**

Run: `pytest backend/ -v`
Expected: PASS — no failures, no references to `tag_key` remaining.

- [ ] **Step 10: Commit**

```bash
git add backend/downloader.py backend/tagger.py backend/tests/test_downloader.py
git commit -m "feat: use FreqBlog BPM/key on download, with local analysis fallback"
```

---

## Self-Review Notes

- **Spec coverage:** hybrid FreqBlog→local lookup (Task 2), Camelot-only key tag + integer BPM tag (Task 1), `key_cache.bpm` populated from the download path (Task 2 Step 6), `tag_key` removed (Task 2 Step 8), no new settings/UI/dependencies (Global Constraints) — all covered.
- **Type consistency:** `_resolve_dj_metadata` return shape (`key`/`camelot`/`bpm`/`confidence`/`source`) matches what `download_track` destructures in Task 2 Step 6, and matches the test assertions in Task 2 Step 1.
- **No placeholders:** every step has literal code, no TBD/TODO.
