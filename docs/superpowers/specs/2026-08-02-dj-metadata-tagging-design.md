# DJ Metadata Tagging (FreqBlog BPM/Key on Download) Design

**Goal:** Write BPM and musical key (Camelot notation) into every downloaded track's standard audio tags, sourced from FreqBlog first and falling back to local audio analysis, so downloads are usable directly in Rekordbox, Serato, and VirtualDJ without a separate tagging pass.

**Architecture:** Backend-only. No new settings, no new UI, no new DB tables. Reuses the existing `freqblog.py` lookup (today only wired into the preview endpoint) and the existing local key/BPM detector (`key_detection.py`), applying the same hybrid pattern the preview flow already uses.

**Tech Stack:** Python (FastAPI), mutagen

---

## Current State (why this is needed)

- `backend/freqblog.py`'s `lookup_track_metadata()` is only called from the preview endpoint (`main.py::_detect_preview_key`). The download path (`downloader.py::download_track`) never calls it.
- The download path always runs local `_detect_key()` (librosa) after every download and writes **only the key** via `tagger.py::tag_key()`. The detected **BPM is discarded** — it's cached in the DB `key_cache` table but never written into the audio file.
- The key that does get written is the raw musical name (e.g. `Am`) into `TKEY`/`initialkey`, plus a redundant copy of the Camelot code into a separate custom field (`TXXX:CAMELOT` / `camelot` Vorbis field / custom M4A atom) that most DJ software doesn't read.

## Backend Changes

### `backend/tagger.py`

Replace `tag_key(file_path, key, camelot)` with:

```python
def tag_dj_metadata(file_path: str, camelot: Optional[str], bpm: Optional[float] = None):
    """Write DJ-standard Key (Camelot notation) and BPM tags."""
```

- Writes Camelot notation as the **sole** key tag value (`TKEY` for MP3, `initialkey` for FLAC, `----:com.apple.iTunes:initialkey` for M4A) — drops the redundant separate camelot field.
- Writes BPM, **rounded to an integer**, to the standard BPM tag (`TBPM` for MP3, `bpm` Vorbis field for FLAC, `tmpo` atom for M4A). Rounding is required for M4A: mutagen's `tmpo` atom expects an int, not a float, and would raise on a float value.
- Each field is only written if present (same `if metadata.get(...)` guard style as `tag_file`).
- Same per-format try/except-at-the-call-site pattern as today — a tagging failure logs a warning and doesn't raise.

### `backend/downloader.py`

In `download_track`, replace the current post-download block:

```python
key_result = await asyncio.to_thread(_detect_key, final_path)
h = file_hash(final_path)
await self.db.set_key_cache(h, key_result["key"], key_result["camelot"], key_result["confidence"])
await asyncio.to_thread(tag_key, final_path, key_result["key"], key_result["camelot"])
```

with a hybrid lookup, mirroring the preview flow's pattern:

1. Call `lookup_track_metadata(metadata["title"], metadata["artist"])` (new import from `backend.freqblog`).
2. If it returns a result with both `bpm` and `camelot` present, use those (source = `"freqblog"`).
3. Otherwise, fall back to `_detect_key(final_path)` as today (source = `"local"`).
4. Cache the winning result in `key_cache` via `db.set_key_cache(h, key, camelot, confidence, bpm=bpm)` — the `bpm` column already exists in the schema, it just wasn't populated from this code path.
5. Call `tag_dj_metadata(final_path, camelot, bpm)`.
6. Log which source won (`logger.info`), matching the `[FreqBlog HIT/MISS]` logging style already used in `main.py`.

The whole block stays wrapped in the existing `try/except` so a failure in both FreqBlog and local analysis just skips DJ tagging — it never fails the download.

No pre-check against the cache before calling FreqBlog (matches today's preview behavior of hitting the API each time there's no cache entry) — not adding new caching dimensions beyond what exists.

## Compatibility Notes (documented, not implemented — these are DJ-app-side settings)

- **Serato**: reads the key tag literally in "Original Tag" display mode, and can also auto-convert to Camelot in its own display setting — works either way.
- **Rekordbox**: has a "Key display format → Alphanumeric" preference that renders Camelot correctly. By default, Rekordbox (and Serato) may **re-analyze BPM/key on import**, overwriting the file's tag — the user needs to disable that auto-analysis in their DJ software's preferences for our tags to stick. This is a known, standard caveat (Mixed In Key gives the same warning to its users) and isn't something fixable from the file side.
- **VirtualDJ**: reads existing tags more directly.
- **Traktor** (not in the requested list, noted for completeness): its native Key field doesn't understand Camelot notation at all — would show as unrecognized text. Out of scope since it wasn't requested.

## Testing

- `backend/tests/test_tagger.py`: replace the `tag_key` coverage with `tag_dj_metadata` — assert Camelot lands in the key tag and BPM lands in the BPM tag for FLAC/MP3/M4A, and that a float BPM doesn't raise on M4A.
- `backend/tests/test_downloader.py`: update the existing mocked download test to patch `backend.downloader.lookup_track_metadata` (returning `None`) alongside the existing `_detect_key` mock, so the local-fallback path is what's exercised; keep asserting the final tagged file exists.

## Not In Scope (YAGNI)

- No Settings UI or config toggle — this runs automatically on every download, same as today's local key detection.
- No key-notation preference — Camelot only, per decision.
- No writing of cue points, beatgrids, or other proprietary Serato/Rekordbox binary formats — FreqBlog only offers BPM/key/Camelot/open-key data, nothing else to write.
- No re-tagging of already-downloaded files already on disk.
- No changes to the preview flow (`main.py::_detect_preview_key`) — it already does its own equivalent hybrid lookup for a different purpose (display only, no file write) and is left untouched.
