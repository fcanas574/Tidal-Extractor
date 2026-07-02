# Work Log

Chronological feature history, reconstructed from git log + handoff docs.

**See:** [[Active Work]] · [[Roadmap]] · [[Design Specs]]

## Recent Work (June 2026)

### Search Pagination — "Load More" (2026-06-23 → 2026-06-27)
- `feat: add offset/limit params to search.query()`
- `feat: add Load More button and pagination state`
- `feat: add deduplication cache for search pagination`
- `fix: pagination cache slicing`
- `fix: pagination with DJ filters`
- `fix: Load More offset with filters`

**What:** Frontend "Load More" button appends 50 tracks at a time. Backend caches full search result list (Tidal has no native offset), filters applied to full set before slicing. See [[Search Subsystem]].

### DJ Search Filters (2026-06-23) ✅ Complete
BPM range, Camelot key, harmonic compatibility, genre browser. See [[DJ Filters]] and `handoff/Session-2026-06-23-dj-filters-complete.md`.

### Search Improvements (2026-06-19)
- Result scoring (exact/partial title, recency, artist match)
- Metadata enrichment for top N (full_title / version)
- Integrated into `/search` endpoint

### Key Detection & FreqBlog (2026-06-18 → 2026-06-21)
- Camelot key detection backend (librosa)
- Stats + key detection integrated into download pipeline
- FreqBlog API integration (hybrid key detection for previews)
- Camelot fallback formula fix + key/camelot metadata embedding

### Frontend Features (May 2026)
- Stats dashboard
- HistoryView with re-download
- Camelot key with rainbow animation during preview
- Tri-band waveform preview (`AudioPlayerFooter`)
- Settings panel, toast notifications

### Core App (May 2026)
- FastAPI backend with WebSocket
- Tidal OAuth device-link auth
- Download orchestrator with quality fallback
- ffprobe bitrate verification
- ffmpeg format conversion
- mutagen metadata tagging
- Queue, history, device stats
- Search, album/playlist/URL resolve

## Commits (last 20)

```
ac24d55 fix: Load More offset with filters
f64b389 fix: pagination with DJ filters
140a653 fix: pagination cache slicing
1000c98 feat: add Load More button and pagination state
841a271 feat: add offset/limit params to search.query()
08e0188 feat: add deduplication cache for search pagination
2a54fb0 docs: add DJ filters to README
1ad3236 docs: DJ search filters implementation complete handoff
fc9eb00 feat: DJ search filters design spec
1aed851 chore: complete search improvements with scoring and enrichment
aed468b feat: integrate scoring and enrichment into /search endpoint
292b96c feat: add metadata enrichment for top N search results
9f704fb feat: add result scoring function for search ranking
413df6d feat: show Camelot key with rainbow animation during preview
f98d12b fix: correct Camelot fallback formula and add key/camelot metadata embedding
5a56e6a docs: update README with new features
53fed2b feat: Stats dashboard frontend
e02115c feat: HistoryView frontend with re-download
0389d51 feat: integrate stats and key detection into download pipeline
6199cbb feat: Camelot key detection backend with librosa
```

## Handoff Documents

In `handoff/`:
- `Session-2026-06-18.md`
- `Session-2026-06-21.md`
- `Session-2026-06-23-dj-filters-complete.md`

## Session Cost Note

The DJ filters session (2026-06-23) cost ~$148 in API usage, flagged CRITICAL at $63 — user approved continuing. Heavy Read usage for context restoration + multiple builds. See [[Gotchas & Traps]].

## See Also

- [[Active Work]] · [[Roadmap]] · [[Design Specs]]


---

## Queue Visibility & Clear Bugs (2026-06-29) ✅ Complete

**Reported:**
1. "Clear All" / "Clear Completed" in the Queue screen don't work.
2. Standalone track downloads don't show in the queue — only albums/playlists do.

**Root causes found via `systematic-debugging`:**

1. **FastAPI route shadowing** — `DELETE /queue/{item_id}` was declared *before* `/queue/completed`, `/queue/batch`, `/queue/all` in `backend/main.py`. The param route captured the literals → `int` parse fail → 422. Clear buttons silently no-op'd. *Verified empirically with `TestClient` before fixing.*

2. **`wsConnected` never set** — `useWebSocket.ts` had no `onopen`/`onerror`; only `onclose` (reconnect-only, no dispatch). So `state.wsConnected` stayed `false` forever → the 5s poll reconciler (`if (!state.wsConnected) return;`) never ran → queue fetched once on mount only.

3. **Optimistic-add gap** — `SearchView`/`HistoryView`/`QueueView` called `queue.add()` but only fired a toast; never updated `state.queue`. Items added while the (broken) poll was the only refresher never appeared.

4. **Completed items deleted** — `download_track` called `remove_from_queue` on success. Completed tracks vanished on next fetch; album/playlist parents persist (marked `'complete'`, never deleted). This made standalone tracks *look* like they never showed up.

**Fixes (all in working tree, uncommitted):**
- `backend/main.py`: reordered literal DELETE routes before `/{item_id}`.
- `backend/tests/test_queue_routes.py`: 4 regression tests (verified they 422 under buggy ordering).
- `frontend/src/hooks/useWebSocket.ts`: `onopen`/`onclose`/`onerror` → `SET_WS_CONNECTED`.
- `frontend/src/context/AppContext.tsx`: `UPDATE_QUEUE_ITEM` now **upserts** (insert new id, replace existing).
- `SearchView`/`HistoryView`/`QueueView`: dispatch `UPDATE_QUEUE_ITEM` with the returned `QueueItem`.
- `backend/downloader.py`: `update_queue_status(id, "complete", 100.0)` instead of `remove_from_queue`.

**Verification:** backend `62 passed, 1 skipped`; frontend `tsc --noEmit` clean.

**See:** [[Gotchas & Traps]] (new entries: Route Shadowing, Completed Items Marked Not Deleted, RESOLVED wsConnected).