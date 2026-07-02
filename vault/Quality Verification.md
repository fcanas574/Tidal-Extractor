# Quality Verification

How TidalExtractor empirically verifies audio quality with ffprobe — the feature that distinguishes it from naive downloaders.

**See:** [[Backend quality]] · [[Download Pipeline]] · [[Gotchas & Traps]]

## The Philosophy

> Trust, but verify. Tidal tells you what quality it's serving; ffprobe tells you what you actually got.

Most downloaders trust the manifest. TidalExtractor **probes** the actual delivered bitrate before committing, because:
- A "Lossless" preset may only deliver AAC
- HiRes isn't always available (requires PKCE auth)
- Account tier and device affect delivery
- Tools like FakinTheFunk misreport (see [[Gotchas & Traps]])

## The Preset Ladder

```python
QUALITY_PRESETS = {
    "hi_res_lossless": { min_bitrate: 1500 },   # 24-bit FLAC
    "high_lossless":   { min_bitrate:  700 },   # 16-bit FLAC
    "low_320k":        { min_bitrate:  300 },   # 320kbps AAC
    "low_96k":         { min_bitrate:   64 },   # 96kbps AAC
}
```

Iterated **top-down**. The first preset whose actual bitrate clears its threshold wins.

## Phase 1: Session Probe (`probe_quality`)

Runs once per session (cached in `quality_cache` table, singleton id=1):

```
for preset in [hi_res_lossless → low_96k]:
    test_track = session.get_tracks(limit=1)[0]
    session.audio_quality = QUALITY_ENUM_MAP[preset]
    stream = test_track.get_stream()
    urls = stream.get_stream_manifest().get_urls()
    download first 500KB (512000 bytes) of urls[0]
    bitrate = get_bitrate(tmp)   # ffprobe
    if bitrate >= preset.min_bitrate:
        db.set_quality_cache(preset, bitrate)
        broadcast {type:'quality', preset, bitrate}
        return preset
return None   # all presets failed
```

**Sample size:** 500KB is enough for ffprobe to read container/stream bitrate accurately without downloading a full track.

## Phase 2: Per-Track Verification (`download_track`)

After a full download:
```
actual_bitrate = get_bitrate(tmp)   # ffprobe on the complete file
# recorded in history table as actual_bitrate
```

This is the **verified** bitrate of the final file — what the user actually received. Displayed in history.

## `get_bitrate(file_path)` — ffprobe wrapper

```python
ffprobe -v quiet -print_format json -show_format -show_streams <file>
```
- Iterates streams, returns first **audio** stream's `bit_rate // 1000` (kbps)
- Falls back to `format.bit_rate // 1000` if no stream-level bitrate
- Returns `None` on timeout (10s), JSON error, or ffprobe missing
- Reads the **container's** reported bitrate, not instantaneous VBR — this is why it's accurate where FakinTheFunk isn't

## Why Not Fallback Per-Track?

The probe runs once per session and picks the best *working* preset. Individual track downloads then **use that preset directly** rather than re-walking the ladder per track. Rationale:
- The probe already established what your account delivers
- Per-track fallback would multiply API calls and slow downloads
- If a specific track fails at the probed quality, the download fails (rather than silently degrading)

> **Note:** This means a track that *individually* can't deliver the probed quality will fail rather than fall back. This is a conscious trade-off favoring quality guarantee over download completion.

## Quality ↔ OAuth Requirement

```
hi_res_lossless  → requires PKCE-enabled OAuth (different manifest type)
high_lossless    → standard BTS manifest
low_320k         → standard BTS manifest
low_96k          → standard BTS manifest
```

If you want HiRes, the OAuth flow must be PKCE-enabled. See [[Auth Flow]] and [[Gotchas & Traps]].

## Stats

`device_stats` table tracks per-quality download counts via `increment_stat(f"quality_{preset}", 1)` per successful download. Surfaced in the Stats dashboard.

## See Also

- [[Backend quality]] · [[Download Pipeline]] · [[Backend downloader]] · [[Gotchas & Traps]]
