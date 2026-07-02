# Gotchas & Traps

Quirks, footguns, and lessons learned. Read before touching the corresponding code.

**See:** [[Active Work]] · [[Roadmap]] · [[Backend audioop_stub]]

## 🔴 Critical: Untracked `freqblog.py`

`backend/main.py` imports `from backend.freqblog import lookup_track_metadata`, but `backend/freqblog.py` is **untracked in git** (shows as `??` in status). A fresh clone will fail to import `backend.main` → the app won't start.

**Fix:** Commit `backend/freqblog.py` and `backend/tests/test_freqblog_api.py`. See [[Active Work]].

## 🔴 Critical: Nested `TidalExtractor/` Directory

There's an untracked `TidalExtractor/` directory *inside* the project root. This is unexpected — likely a stray clone or build artifact. Investigate before committing anything that might sweep it up.

## ⚠️ HiRes Lossless Requires PKCE

`hi_res_lossless` uses a different Tidal manifest type than LOSSLESS and below. It requires **PKCE-enabled OAuth**. If the OAuth flow isn't PKCE-enabled, the quality probe will simply skip HiRes and fall through to `high_lossless`. Not a crash — just silently lower quality. See [[Auth Flow]] · [[Quality Verification]].

## ⚠️ FakinTheFunk Misreports Bitrate

FakinTheFunk samples *instantaneous* variable bitrate, not overall average. A genuine 24-bit FLAC at ~1,790 kbps may show as 128–160 kbps. **This is why TidalExtractor uses ffprobe** (which reads container bitrate) instead. Don't "verify" downloads with FakinTheFunk. See [[Quality Verification]].

## ⚠️ `tidal.db` vs `tidal_extractor.db`

Two DB files at root:
- `tidal_extractor.db` — **the active database** (114KB, with `-shm`/`-wal`)
- `tidal.db` — **empty (0 bytes), unused**

`tidal.db` appears to be a leftover. The code hardcodes `db_path="tidal_extractor.db"`. Don't confuse them; consider deleting `tidal.db` and gitignoring it. See [[Data Model]].

## ⚠️ Python 3.13 `audioop` Removal

Python 3.13 removed the `audioop` stdlib module ([PEP 594](https://peps.python.org/pep-0594/)). pydub (used by wavypy) imports it. Without `audioop_stub.py` patched into `sys.modules` *before* pydub imports, the waveform engine crashes with `ModuleNotFoundError`. See [[Backend audioop_stub]] · [[Backend waveform]].

## ⚠️ Search Cache Key Excludes Filters

`_search_results_cache` is keyed by `{query}:{type}` — **filters (BPM/key/genre) are NOT in the key**. This means:
- Filter changes re-slice the same cached full result set (fast, no re-fetch)
- But if you *expect* a filter change to fetch fresh results, you'll be surprised

The genre prefix *is* part of the query string, so genre changes do trigger cache misses. BPM/key changes do not. See [[Search Subsystem]].

## ⚠️ Genre Double-Prefix Bug (Historical)

The frontend once sent `genre:House` as the `q` parameter, and the backend prepended `genre:` again → `genre:genre:House` (broken search). Fixed by:
- Frontend sends empty `q` + separate `genre=House`
- Backend constructs `genre:{genre}` only when `q` is empty, else `genre:{genre} {q}`

If you touch the search query construction, re-verify this. See [[DJ Filters]].

## ⚠️ In-Memory Caches Don't Persist

`_search_results_cache` and `freqblog_stats` are module-level dicts — **cleared on every restart**. Search results re-fetch from Tidal on first search after reboot. FreqBlog stats reset to zero. See [[System Design]].

## ⚠️ Waveform Cache Keyed by Stream URL

`get_waveform_cached` uses `@lru_cache` keyed by **stream URL**, not track ID. Tidal stream URLs can rotate/expire, so the same track may miss the cache across sessions or after URL expiry. Within a session, repeats are instant. See [[Backend waveform]].

## ⚠️ Sequential Downloads Only

The orchestrator processes the queue **one track at a time** (`_running` flag prevents concurrency). Bulk downloads of large albums will be slow. There's no parallelism. See [[Download Pipeline]].

## ⚠️ No Per-Track Quality Fallback

The session probe picks one preset; individual tracks download at that preset. If a specific track can't deliver the probed quality, **the download fails** rather than falling back to a lower preset. Conscious trade-off (quality guarantee > completion). See [[Quality Verification]].

## ⚠️ `test_detect_key_mocked` Fails

`backend/tests/test_key_detection.py::test_detect_key_mocked` has a known failure (liberosa mock issue). The Camelot conversion tests pass. Don't be alarmed — but don't let it mask new failures. See [[Development Setup]].

## ⚠️ `output_dir` Default Mismatch

- `AppConfig.DEFAULTS["output_dir"]` = `~/Music/TidalDownloads`
- Committed `config.yaml` = `~/Downloads`
- `AppContext` initial state = `~/Music/TidalDownloads`

The real value loads from the server on mount. The transient mismatch is harmless but can confuse debugging. See [[Configuration]].

## ⚠️ `wsConnected` Provenance

`AppContext.wsConnected` gates the 5s queue polling, but `useWebSocket.ts` doesn't obviously dispatch `SET_WS_CONNECTED`. Verify the wiring if polling behavior changes. See [[Frontend useWebSocket]].

## ⚠️ Schema Migrations Are Implicit

No migration version table. `init()` runs `CREATE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` wrapped in try/except. Additive-only; no way to rename/drop columns cleanly. If you need real schema evolution, add a version table. See [[Data Model]].

## 💡 Session Cost Awareness

The DJ filters session (2026-06-23) cost ~$148, flagged CRITICAL at $63. Heavy Read usage for context restoration + builds. For long sessions, prefer targeted reads over full-file reads, and batch frontend builds. See [[Work Log]].

## See Also

- [[Active Work]] · [[Roadmap]] · [[Work Log]] · [[Backend audioop_stub]]


---

## 🆕 FastAPI Route Shadowing (`/queue/{item_id}` vs literals)

FastAPI matches routes in **declaration order**. If `DELETE /queue/{item_id}` is declared before the literal routes `/queue/completed`, `/queue/batch`, `/queue/all`, the parameterized route captures them (`item_id="completed"`), fails `int` parsing, and returns **422** — making "Clear All" / "Clear Completed" silently fail.

**Fixed (2026-06-29):** Literal routes (`/completed`, `/batch`, `/all`) now declared **before** `/queue/{item_id}`. Regression tests in `backend/tests/test_queue_routes.py` (confirmed they return 422 under the buggy ordering). **Rule of thumb:** in FastAPI, always declare literal/static path segments before parameterized ones. See [[Backend main]].

## 🆕 Completed Items Are Marked, Not Deleted

`download_track` previously called `db.remove_from_queue(id)` on success, so completed tracks vanished on the next poll. Album/playlist parents are marked `'complete'` (never deleted), which made standalone-track downloads *appear* to never show in the queue.

**Fixed (2026-06-29):** `download_track` now calls `db.update_queue_status(id, "complete", progress=100.0)`. Completed items persist in the Queue's "Completed" section until the user clears them — matching the existing UI design. Note: this also means the "Clear Completed" route matters; it was broken by the shadowing bug above.