# Backend: tagger.py

**Role:** Metadata embedding via **mutagen** for FLAC, MP3, and M4A files. Writes standard tags plus DJ-specific key/Camelot fields.

**See:** [[Download Pipeline]] · [[Backend downloader]]

## Public API

### `tag_file(file_path, metadata, cover_art_url=None)`
Dispatches by extension:
- `.flac` → `_tag_flac`
- `.mp3` → `_tag_mp3`
- `.m4a` → `_tag_m4a`
- other → logs warning, no-op

### `tag_key(file_path, key, camelot)`
Embeds **only** the key + Camelot fields (called after `detect_key` post-download). Swallows errors (logs warning) so a tagging failure doesn't break a successful download.

## Metadata Fields Written

| Field | FLAC | MP3 (ID3) | M4A (MP4) |
|-------|------|-----------|-----------|
| title | `title` | `TIT2` | `©nam` |
| artist | `artist` | `TPE1` | `©ART` |
| album | `album` | `TALB` | `©alb` |
| track_num | `tracknumber` | `TRCK` | `trkn` (tuple) |
| genre | `genre` | `TCON` | `©gen` |
| year | `date` | `TDRC` | `©DAY` |
| label | `label` | `TPUB` | `----:LABEL` |
| isrc | `isrc` | `TSRC` | `----:ISRC` |
| bpm (>0) | `bpm` | `TBPM` | `tmpo` |
| key | `initialkey` | `TKEY` | `----:initialkey` |
| **camelot** (key-only) | `camelot` | `TXXX:CAMELOT` | `----:CAMELOT` |

## Cover Art

### `_get_cover_bytes(metadata, cover_art_url)`
Priority:
1. `metadata['cover_art_path']` if local file exists (reads bytes)
2. `cover_art_url` → `requests.get(url)` (10s timeout)
3. `None`

Embedded as JPEG, type 3 (front cover):
- **FLAC:** `Picture(type=3, mime="image/jpeg", data=...)` via `add_picture`
- **MP3:** `APIC(mime="image/jpeg", type=3, desc="Cover")`
- **M4A:** `MP4Cover(data, FORMAT_JPEG)` in `covr` tag

## Format-Specific Quirks

### FLAC (`_tag_flac`)
- Calls `f.delete()` first (wipes existing tags + pictures) for a clean write
- Uses Vorbis comment keys (lowercase)

### MP3 (`_tag_mp3`)
- Ensures tags exist (`if f.tags is None: f.add_tags()`)
- `delall("APIC")` before adding new cover (no duplicate art)
- Builds a list of ID3 frame objects, adds each
- Encoding 3 = UTF-8

### M4A (`_tag_m4a`)
- Ensures tags exist
- iTunes-style freeform tags use `----:com.apple.iTunes:NAME` with UTF-8 bytes
- `tmpo` for BPM (Apple's tempo atom)
- Track number stored as `(track_num, 0)` tuple in `trkn`

## Integration

`download_track()` calls:
1. `tag_file(final_path, metadata, cover_url)` — full metadata after conversion
2. (later) `tag_key(final_path, key, camelot)` — after `detect_key` runs

Both wrapped in `asyncio.to_thread`.

## See Also

- [[Backend downloader]] · [[Backend key_detection]] · [[Download Pipeline]]
