# Backend: downloader.py

**Role:** `DownloadOrchestrator` — the engine that turns queue items into tagged files on disk. Owns quality probing, streaming downloads, format conversion, metadata tagging, key detection, and history recording.

**See:** [[Download Pipeline]] · [[Request Lifecycle]] · [[Quality Verification]]

## Class: `DownloadOrchestrator`

```python
def __init__(db, config, ws_manager=None):
    self.session: Optional[tidalapi.Session]
    self._probed_quality: Optional[str]
    self._running: bool = False     # concurrency guard for process_queue
```

### `set_session(session)`
Binds the authenticated Tidal session. Called after auth completes.

## Constants

```python
QUALITY_ENUM_MAP = { "hi_res_lossless", "high_lossless", "low_320k", "low_96k" }  # → tidalapi.Quality
FORMAT_EXT_MAP   = { "FLAC": ".flac", "MP3": ".mp3", "M4A": ".m4a" }
```

## `probe_quality()` — The Quality Ladder

```
for preset_name in QUALITY_PRESETS (top-down: hi_res → 96k):
    test_track = session.get_tracks(limit=1)[0]
    session.audio_quality = QUALITY_ENUM_MAP[preset]
    stream = test_track.get_stream()
    urls = stream.get_stream_manifest().get_urls()
    download first 500KB (512000 bytes) of urls[0]
    bitrate = get_bitrate(tmp)                          # ffprobe
    if bitrate_meets_threshold(preset, bitrate):
        db.set_quality_cache(preset, bitrate)
        return preset                                   # FIRST winner
return None                                             # all failed
```

Caches the first preset that *actually delivers* its promised bitrate. Subsequent track downloads reuse this.

## `extract_track_metadata(track)` → dict

Pulls extended metadata from a tidalapi Track:
`title, artist, artists[], album, album_id, track_num, duration, isrc, bpm, key, explicit, quality, cover_art_url`

**Key field quirk:** `key` = `track.key_scale` if present, else `track.key`, else `None`.

## `download_track(queue_item, on_progress)`

The single-track path (see [[Request Lifecycle]] §4 for full detail):
1. Resolve track + extract metadata
2. Set `session.audio_quality` from preset
3. Get stream manifest URLs
4. Build filename (sanitized), create dirs
5. Stream-download to `.tmp` with progress callback
6. `get_bitrate()` on the tmp
7. Convert format if ext mismatch (else `shutil.move`)
8. Fetch album cover URL
9. `tag_file()` with all metadata + cover
10. `detect_key()` → cache + `tag_key()`
11. `increment_stat` ×3 (total_tracks, total_bytes, quality_{preset})
12. `add_to_history`, `remove_from_queue`

## `_build_filename()`

```
With collection: "{Artist}/{NN} - {Artist} - {Title}{ext}"   # album subfolder
Without:         "{Artist} - {Title}{ext}"
```
`_sanitize_filename()` replaces `[\\/:*?"<>|]` with ` -` and collapses whitespace.

## `_expand_collection(item)`

For album/playlist queue items:
- Fetches tracks via `get_album_tracks` / `get_playlist_tracks`
- Inserts each as a new `track` queue row with `from_collection=True`, `album=collection_name`
- Marks the parent item `complete`

The processing loop then handles each child as a normal track — they land in `{Artist}/{NN} - {Artist} - {Title}.ext`.

## `process_queue()`

Sequential FIFO loop:
```
_running = True
while _running:
    queued = [status=='queued' items from db.get_queue()]
    if empty: break
    item = queued[0]
    if album/playlist: expand + continue
    mark downloading → download_track → broadcast complete
    on error: mark failed + broadcast error
_running = False
```

**One track at a time.** No parallelism. The `_running` flag prevents overlapping loops (checked by `_process_queue_if_idle` in main.py).

## `on_progress` callback (defined inline in `process_queue`)

```python
async def on_progress(item_id, pct, bytes_done, bytes_total):
    await db.update_queue_status(item_id, 'downloading', progress=pct)
    await ws_manager.broadcast({type:'progress', id, pct, bytes, total})
```

## Error Handling

- Download exceptions delete the `.tmp` file and re-raise
- Key detection failures are caught + logged (don't fail the download)
- Album cover fetch failures are swallowed
- Conversion failures raise `RuntimeError` (fail the download)

## See Also

- [[Backend quality]] · [[Backend converter]] · [[Backend tagger]] · [[Backend key_detection]]
