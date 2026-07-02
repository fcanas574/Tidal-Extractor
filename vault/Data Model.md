# Data Model

SQLite schema for `tidal_extractor.db`. Five tables. WAL journal mode.

**See:** [[Backend models]] · [[System Design]]

## Schema Overview

```
queue           — pending + active downloads (transient)
history         — completed downloads (permanent)
device_stats    — cumulative counters (key/value)
quality_cache   — probed quality preset (singleton, id=1)
key_cache       — detected key/BPM by file hash
```

## `queue`

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | INTEGER PK | AUTOINCREMENT | |
| `tidal_id` | TEXT | NOT NULL | Tidal track/album/playlist ID |
| `item_type` | TEXT | 'track' | 'track' \| 'album' \| 'playlist' |
| `title` | TEXT | NOT NULL | |
| `artist` | TEXT | '' | |
| `album` | TEXT | '' | Collection name for child tracks |
| `quality` | TEXT | 'high_lossless' | Preset name |
| `format` | TEXT | 'FLAC' | 'FLAC' \| 'MP3' \| 'M4A' |
| `status` | TEXT | 'queued' | 'queued' \| 'downloading' \| 'complete' \| 'failed' |
| `progress` | REAL | 0.0 | 0–100 |
| `error` | TEXT | NULL | Failure reason |
| `from_collection` | INTEGER | 0 | True if expanded from album/playlist |
| `created_at` | TIMESTAMP | CURRENT_TIMESTAMP | FIFO ordering |

**Lifecycle:** `queued` → `downloading` (progress updates) → `complete` (removed) or `failed` (error set). Album/playlist parents go `queued` → `downloading` → `complete` after expansion (their children become track rows).

## `history`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `tidal_id` | TEXT | |
| `item_type` | TEXT | |
| `title` | TEXT | |
| `artist` | TEXT | |
| `album` | TEXT | |
| `quality` | TEXT | Preset used |
| `format` | TEXT | Final format |
| `file_path` | TEXT | Absolute path on disk |
| `file_size` | INTEGER | Bytes |
| `actual_bitrate` | INTEGER | Verified kbps (ffprobe) |
| `downloaded_at` | TIMESTAMP | |

Ordered by `downloaded_at DESC` in queries.

## `device_stats`

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT PK | e.g. 'total_tracks', 'total_bytes', 'quality_high_lossless' |
| `value` | INTEGER | |
| `updated_at` | TIMESTAMP | |

Written via UPSERT (`ON CONFLICT(key) DO UPDATE SET value = value + excluded.value`).

**Known keys:** `total_tracks`, `total_bytes`, `quality_hi_res_lossless`, `quality_high_lossless`, `quality_low_320k`, `quality_low_96k`.

## `quality_cache`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | `CHECK (id = 1)` — singleton |
| `preset` | TEXT | e.g. 'high_lossless' |
| `bitrate` | INTEGER | Verified kbps |
| `updated_at` | TIMESTAMP | |

`set_quality_cache` does DELETE then INSERT (enforces singleton).

## `key_cache`

| Column | Type | Notes |
|--------|------|-------|
| `file_hash` | TEXT PK | MD5[:16] of file content, OR `preview_key_{track_id}` for previews |
| `key` | TEXT | e.g. 'Am', 'C' |
| `camelot` | TEXT | e.g. '8A' |
| `confidence` | REAL | 0–1 |
| `bpm` | REAL | Nullable (added via migration) |
| `detected_at` | TIMESTAMP | |

Written via UPSERT. Used by both post-download key detection (file hash key) and preview key detection (`preview_key_{track_id}` key).

## Migrations

Schema evolution is **implicit** (no version table). On every `init()`:
1. `CREATE TABLE IF NOT EXISTS` ×5 (idempotent)
2. `ALTER TABLE queue ADD COLUMN from_collection` (try/except — column may exist)
3. `ALTER TABLE key_cache ADD COLUMN bpm` (try/except — column may exist)

The `try/except` swallows "duplicate column" errors. This works but means there's no formal migration history — schema changes are additive only.

## PRAGMA

```sql
PRAGMA journal_mode=WAL;
```
Write-Ahead Logging: concurrent readers + single writer. Produces `-shm` and `-wal` sidecar files (visible in the repo working tree).

## Connection Model

Single `aiosqlite.Connection` opened in `init()`, reused for all queries, closed in lifespan shutdown. No pool. All queries use `row_factory = aiosqlite.Row` → dict-like rows.

## See Also

- [[Backend models]] · [[System Design]] · [[API Reference]]
