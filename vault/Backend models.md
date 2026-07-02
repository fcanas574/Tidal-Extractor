# Backend: models.py

**Role:** `Database` — async SQLite access layer via `aiosqlite`. Owns schema creation, migrations, and all CRUD. One persistent connection for the app lifetime.

**See:** [[Data Model]] · [[System Design]]

## Class: `Database`

```python
def __init__(db_path="tidal_extractor.db"):
    self._conn: Optional[aiosqlite.Connection]
```

### `init()`
```python
self._conn = await aiosqlite.connect(db_path)
self._conn.row_factory = aiosqlite.Row     # dict-like rows
await execute("PRAGMA journal_mode=WAL")   # concurrent readers + single writer
await executescript(<schema>)              # CREATE TABLE IF NOT EXISTS ×5
# Migrations (idempotent ALTER, swallow "column exists" errors):
#   ALTER TABLE queue ADD COLUMN from_collection
#   ALTER TABLE key_cache ADD COLUMN bpm
```

### `close()`
Closes the connection (called in lifespan shutdown).

## Tables — see [[Data Model]] for full schema

| Table | Purpose | PK |
|-------|---------|----|
| `queue` | Pending + active downloads | `id` autoincrement |
| `history` | Completed downloads (permanent) | `id` autoincrement |
| `device_stats` | Cumulative counters (key/value) | `key` |
| `quality_cache` | Probed quality preset (singleton) | `id CHECK(id=1)` |
| `key_cache` | Detected key/Camelot/BPM by file hash | `file_hash` |

## Methods by Table

### Queue
- `add_to_queue(tidal_id, item_type, title, artist, album, quality, format, from_collection=False)` → row
- `get_queue()` → list ordered by `created_at ASC` (FIFO)
- `update_queue_status(item_id, status, error=None, progress=None)` — dynamic UPDATE
- `remove_from_queue(item_id)`
- `remove_completed()` → count (deletes `status='complete'`)
- `remove_batch(ids)` → count (IN clause with placeholders)
- `remove_all()` → count

### History
- `add_to_history(tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate)`
- `get_history(limit=100, offset=0)` → ordered by `downloaded_at DESC`

### Quality Cache
- `set_quality_cache(preset, bitrate)` — DELETE then INSERT (singleton, id=1)
- `get_quality_cache()` → `{preset, bitrate}` or `None`
- `clear_quality_cache()`

### Device Stats
- `increment_stat(key, amount=1)` — **UPSERT** via `ON CONFLICT(key) DO UPDATE`
- `get_stat(key)` → int
- `get_all_stats()` → `{key: value}` dict

### Key Cache
- `get_key_cache(file_hash)` → row or None
- `set_key_cache(file_hash, key, camelot, confidence, bpm=None)` — UPSERT

## Patterns

- **WAL mode** — allows concurrent reads while writing; the `-shm` and `-wal` files appear alongside the DB
- **row_factory = Row** — all queries return dict-like rows; methods call `dict(r)` to materialize
- **`execute_fetchall`** — used instead of `execute(...).fetchall()` for compatibility
- **Dynamic SQL in `update_queue_status`** — builds SET clause from provided fields
- **No transactions beyond autocommit** — each method calls `await commit()` after writes

## Gotcha

The migration `ALTER TABLE queue ADD COLUMN from_collection` runs on every boot. The `try/except` swallows the "duplicate column" error silently. Same for `key_cache.bpm`. This is intentional but means schema evolution is implicit — there's no formal migration version.

## See Also

- [[Data Model]] · [[Backend main]] · [[System Design]]
