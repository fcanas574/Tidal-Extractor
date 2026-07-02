# Backend: freqblog.py

**Role:** Client for the external **FreqBlog API** — fast metadata lookup for BPM, key, and Camelot notation without downloading audio.

**See:** [[Key Detection]] · [[Backend main]]

## Configuration

```python
FREQBLOG_BASE = "https://api.freqblog.com"
FREQBLOG_API_KEY = os.getenv("FREQBLOG_API_KEY")   # from .env
```

Loads `.env` from the project root (`Path(__file__).parent.parent / ".env"`) via `python-dotenv`.

## `lookup_track_metadata(track_title, artist)` → `Optional[dict]`

```
if not FREQBLOG_API_KEY: return None            # skip silently

GET {FREQBLOG_BASE}/lookup
    params: { track: title, artist: artist }
    headers: { User-Agent: "TidalExtractor/0.1.0", X-API-Key: <key> }
    timeout: 10s

404 → return None                                # not in catalog
data = resp.json()

# Require both bpm AND key present
if data.bpm is None or data.key is None:
    return None                                  # found but not analyzed yet

return {
    bpm, bpm_confidence,
    key, key_int, mode,
    camelot, open_key, key_confidence,
    source
}
```

## Response Shape

The FreqBlog API returns rich metadata:
- `bpm` + `bpm_confidence`
- `key` (pitch name) + `key_int` (pitch class int) + `mode` (major/minor)
- `camelot` (e.g., "8A") + `open_key` (alternative notation)
- `key_confidence`
- `source` + `backfill_status` (provenance tracking)

## Integration

Called from `main.py:_detect_preview_key()` as **tier 2** of the hybrid key detection:
1. Check `key_cache` (tier 1)
2. **FreqBlog API** (this module, tier 2) — ~100ms, no audio download
3. Local `detect_key()` via librosa (tier 3, fallback)

Stats tracked in `main.py:freqblog_stats` (`hits`, `misses`, `errors`, `cache_hits`), exposed via `GET /freqblog/stats`.

## Error Handling

- `httpx.HTTPError` → log warning, return `None`
- Any other exception → log warning, return `None`
- Never raises — callers can treat `None` as "fall back to local analysis"

## Why It Exists

Local librosa analysis requires downloading the full preview stream (~seconds). FreqBlog returns pre-computed metadata in ~100ms for tracks already in its catalog — a major UX win for the preview feature. Local analysis remains the fallback for tracks FreqBlog hasn't analyzed.

## Testing

`backend/tests/test_freqblog_api.py` covers the client. The module is async (httpx.AsyncClient).

## See Also

- [[Key Detection]] · [[Backend key_detection]] · [[Backend main]]
