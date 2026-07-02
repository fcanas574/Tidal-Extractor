# Download Pipeline

The end-to-end flow that turns a search result into a verified, converted, tagged file on disk. This is TidalExtractor's defining feature.

**See:** [[Request Lifecycle]] · [[Quality Verification]] · [[Backend downloader]]

## Two Phases

The pipeline is split into a **one-time quality probe** (per session) and a **per-track download**.

### Phase 1: Quality Probe (`probe_quality`)

Runs once per session (triggered manually via `POST /quality/probe` or on first need). Walks the preset ladder top-down and caches the winner.

```
for preset in [hi_res_lossless, high_lossless, low_320k, low_96k]:
    fetch a test track's stream at this quality
    download first 500KB
    bitrate = ffprobe(tmp)
    if bitrate >= preset.min_bitrate:
        db.set_quality_cache(preset, bitrate)   # singleton row
        broadcast {type:'quality', preset, bitrate}
        return preset
return None   # all failed
```

**Why probe?** Tidal's *offered* quality isn't always the *delivered* quality. The probe empirically discovers which preset your account + device actually receives before committing to real downloads.

### Phase 2: Per-Track Download (`download_track`)

Uses the **probed** preset (not a fresh fallback per track):

```
1. track = session.track(tidal_id)
2. metadata = extract_track_metadata(track)
3. session.audio_quality = QUALITY_ENUM_MAP[probed_preset]
4. stream = track.get_stream(); urls = manifest.get_urls()
5. filename = build_filename(...)   # sanitized, optional album subfolder
6. Stream-download urls[0] → output.tmp (64KB chunks, progress callback)
7. actual_bitrate = ffprobe(tmp)
8. if ext != manifest_ext: convert_format(tmp, final) else: move(tmp, final)
9. cover_url = album.image(1280); tag_file(final, metadata, cover_url)
10. key_result = detect_key(final); set_key_cache; tag_key(final, key, camelot)
11. increment_stat ×3; add_to_history; remove_from_queue
12. broadcast {type:'complete', id, path, size}
```

## Visual Flow

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Probe   │──▶│ Download │──▶│ ffprobe  │──▶│ Convert  │──▶│   Tag    │
│ (once)   │   │ to .tmp  │   │ verify   │   │ (if need)│   │ metadata │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                  │
                                                                  ▼
                                                          ┌──────────┐
                                                          │   Key    │
                                                          │ detect + │
                                                          │  embed   │
                                                          └──────────┘
```

## Collection Expansion

Album/playlist queue items are **not** downloaded directly. `process_queue` detects them and calls `_expand_collection`:
- Fetches all tracks via `get_album_tracks` / `get_playlist_tracks`
- Inserts each as a new `track` queue row with `from_collection=True` and `album=<collection_name>`
- Marks the parent `complete`

Child tracks then download normally, landing in `{Artist}/{NN} - {Artist} - {Title}.ext` (the `album` field triggers the subfolder path in `build_filename`).

## Progress Reporting

The `on_progress` callback fires per 64KB chunk:
```
pct = (bytes_done / content_length) × 100
db.update_queue_status(id, 'downloading', progress=pct)
ws.broadcast({type:'progress', id, pct, bytes_done, bytes_total})
```

Frontend reducer updates the queue item + a toast in real time. See [[Realtime Updates]].

## Failure Modes

| Failure | Behavior |
|---------|----------|
| No stream URL | `RuntimeError` → item marked `failed`, WS `error` broadcast |
| Download network error | `.tmp` deleted, re-raised → `failed` |
| ffprobe fails | `actual_bitrate = 0` (download still succeeds, recorded as 0) |
| Conversion fails | `RuntimeError` → `failed` |
| Cover art fetch fails | Swallowed (no cover embedded) |
| Key detection fails | Swallowed + logged (download succeeds without key tags) |
| Tagging fails | Swallowed (download succeeds untagged) |

**Philosophy:** Key/cover/tagging failures never fail a download — only stream/conversion failures do.

## File Naming

```
Standalone:  {Artist} - {Title}{ext}
Collection:  {Artist}/{NN} - {Artist} - {Title}{ext}
```
Sanitization: `[\\/:*?"<>|]` → ` -`, whitespace collapsed.

## Cleanup

- Startup: `_cleanup_tmp_files(output_dir)` removes stale `.tmp` files from crashes
- Per-download: `.tmp` deleted on success (moved or converted) or on exception

## See Also

- [[Request Lifecycle]] · [[Quality Verification]] · [[Backend downloader]] · [[Backend tagger]] · [[Backend converter]]
