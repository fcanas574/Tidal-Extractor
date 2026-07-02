# Request Lifecycle

How a track flows from search → download → tagged file. The canonical path through the system.

## 1. Search & Discovery

```
User types query in SearchView
  → GET /search?q=...&type=track&offset=0&limit=50&genre=House&bpm_min=120
  → main.py: search()
      ├── Parse "track - artist" format if present
      ├── Prepend genre: prefix → "genre:House <q>"
      ├── Cache key = "{query}:{type}"
      ├── Cache MISS? → search_tidal() [tidalapi, in thread]
      │     ├── session.search(models=[Track,Album,Playlist], limit=500)
      │     ├── format_track() each result (incl. bpm, key, key_scale)
      │     └── artist_filter applied if " - " used
      ├── score_results() → relevance sort (exact title +10, partial +5, recency +5, artist +10)
      ├── Cache full unfiltered list in _search_results_cache
      ├── filter_tracks_by_dj_metadata() (BPM range + Camelot, harmonic expand)
      ├── Slice page [offset : offset+limit]
      └── enrich_tracks() top 5 (full_title / version remix info)
  → { tracks: [...], albums: [], playlists: [] }
```

Details: [[Search Subsystem]] · [[DJ Filters]]

## 2. Add to Queue

```
User clicks "Download" on a track
  → POST /queue/add  { tidal_id, title, artist, quality?, format? }
  → main.py: add_to_queue()
      ├── quality = item.quality or config.default_quality
      ├── fmt    = item.format  or config.default_format
      ├── db.add_to_queue(...)           # INSERT into queue (status='queued')
      └── asyncio.create_task(_process_queue_if_idle())
  → returns queue_item
```

## 3. Queue Processing Loop (`downloader.py: process_queue`)

```
_running = True
while _running:
  queue = db.get_queue()
  queued = [items where status == 'queued']
  if empty: break
  item = queued[0]                                # FIFO, one at a time

  if item.item_type in ('album','playlist'):
      status → 'downloading'
      _expand_collection(item)                    # fetch tracks, add as track items
      status → 'complete'
      continue

  status → 'downloading'
  try:
      download_track(item, on_progress)           # see §4
      ws.broadcast({ type:'complete', id, path, size })
  except:
      status → 'failed' (error msg)
      ws.broadcast({ type:'error', id, reason })

_running = False
```

**Critical:** Sequential, single-track-at-a-time. The `_running` flag is the only concurrency guard.

## 4. Single Track Download (`download_track`)

```
track = session.track(int(tidal_id))
metadata = extract_track_metadata(track)         # title, artist, album, isrc, bpm, key...

quality_enum = QUALITY_ENUM_MAP[quality_preset]
session.audio_quality = quality_enum
stream = track.get_stream()
manifest = stream.get_stream_manifest()
urls = manifest.get_urls()                        # list of CDN URLs

filename = build_filename(title, artist, ext, collection?)
output_path = output_dir / filename
tmp_path = output_path + ".tmp"

# Stream download with progress callback
httpx.stream(GET, urls[0]):
    write chunks → tmp_path
    on_progress(id, pct, bytes_done, bytes_total)
        → db.update_queue_status(progress=pct)
        → ws.broadcast({ type:'progress', id, pct, bytes, total })

actual_bitrate = get_bitrate(tmp_path)            # ffprobe

# Format conversion (if needed)
if ext != manifest.file_extension:
    convert_format(tmp, final, format.lower())   # ffmpeg
else:
    shutil.move(tmp, final)

# Cover art
album = session.album(track.album.id)
metadata.cover_art_url = album.image(1280)

# Tag
tag_file(final, metadata, cover_url)              # mutagen

# Key detection + embedding (for FLAC/MP3/M4A)
key_result = detect_key(final)                    # librosa
db.set_key_cache(hash, key, camelot, conf, bpm)
tag_key(final, key, camelot)                      # initialkey + camelot tags

# Stats + history
db.increment_stat('total_tracks', 1)
db.increment_stat('total_bytes', size)
db.increment_stat(f'quality_{preset}', 1)
db.add_to_history(...)
db.remove_from_queue(item.id)
```

> **Note on quality fallback:** The *probe* (`probe_quality()`) walks presets top-down once per session and caches the winner. Individual track downloads use the *probed* preset directly rather than re-falling-back per track. See [[Quality Verification]].

## 5. Realtime Feedback

The `on_progress` callback fires on every 64KB chunk:
- Updates DB progress column (for polling reconciliation)
- Broadcasts `{type:'progress', id, pct, bytes, total}` over WebSocket

Frontend `AppContext` reducer handles these → updates queue item + toast. See [[State Management]].

## 6. Variations

### Album / Playlist
Adding an album/playlist inserts *one* row with `item_type='album'`. The processing loop sees it, marks it downloading, calls `_expand_collection()` which fetches all tracks and inserts them as individual `track` rows (with `from_collection=True` and `album` = collection name), then marks the parent complete. The loop then processes each child track normally — and they land in `Artist - Album/NN - Artist - Title.ext` subfolders.

### Re-download (from history)
`POST /history/re-download` behaves identically to `/queue/add` — inserts a fresh queue row and triggers processing.

## See Also

- [[Backend downloader]] · [[Quality Verification]] · [[Backend tagger]] · [[Realtime Updates]]
