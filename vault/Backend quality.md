# Backend: quality.py

**Role:** ffprobe-based bitrate measurement + quality preset thresholds. The verification core that distinguishes TidalExtractor from naive downloaders.

**See:** [[Quality Verification]] · [[Download Pipeline]]

## Quality Presets

```python
QUALITY_PRESETS = {
    "hi_res_lossless": { min_bitrate: 1500, label: "HiRes Lossless (24-bit)" },
    "high_lossless":   { min_bitrate:  700, label: "Lossless (16-bit FLAC)" },
    "low_320k":        { min_bitrate:  300, label: "High (320kbps AAC)" },
    "low_96k":         { min_bitrate:   64, label: "Normal (96kbps AAC)" },
}
QUALITY_PRESETS_ORDER = list(QUALITY_PRESETS.keys())   # top-down
```

**Order matters:** `probe_quality()` iterates this dict top-down, returning the first preset whose *actual* bitrate clears its threshold.

## `get_bitrate(file_path)` → `Optional[int]`

Runs ffprobe, returns kbps:
```python
ffprobe -v quiet -print_format json -show_format -show_streams <file>
```
- Iterates streams, returns first `audio` stream's `bit_rate // 1000`
- Falls back to `format.bit_rate // 1000` if no stream bitrate
- Returns `None` on timeout, JSON error, or ffprobe missing
- Timeout: 10s

## `bitrate_meets_threshold(preset, actual_bitrate)` → bool

```python
threshold = QUALITY_PRESETS[preset]["min_bitrate"]
return actual_bitrate >= threshold
```

## Why This Matters

Tidal nominally serves different qualities, but the *actual* delivered bitrate depends on the master, the manifest type, and the account tier. Probing a 500KB sample with ffprobe catches cases where:
- A "Lossless" preset only delivers AAC
- HiRes isn't actually available (requires PKCE — see [[Gotchas & Traps]])
- FakinTheFunk-style misreporting (ffprobe measures real container bitrate, not instantaneous VBR)

## Integration

- `probe_quality()` in `downloader.py` uses both functions to find the best working preset per session
- `download_track()` calls `get_bitrate()` on the completed `.tmp` to record `actual_bitrate` in history
- Probed preset cached in `quality_cache` table (singleton, id=1)

## See Also

- [[Backend downloader]] · [[Quality Verification]] · [[Gotchas & Traps]]
