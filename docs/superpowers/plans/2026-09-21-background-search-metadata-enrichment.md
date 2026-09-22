# Background Search Metadata Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return ordinary track-search results immediately, then enrich their visible metadata in the background and update matching rows live.

**Architecture:** A focused backend job manager deduplicates visible-page FreqBlog work and calls back into `backend.main` when each batch is complete. The search endpoint merges cached metadata synchronously but never waits for a new provider lookup; the completion callback updates the short-lived search cache and broadcasts a WebSocket metadata patch. The frontend reducer applies that patch only to current search rows, and `SearchView` presents a small pending status while it waits.

**Tech Stack:** Python 3, FastAPI, asyncio, aiosqlite, httpx, pytest/pytest-asyncio, React 18, TypeScript, Vitest, Testing Library, WebSocket.

**Spec:** `docs/superpowers/specs/2026-09-21-background-search-metadata-enrichment-design.md`

## Global Constraints

- Work directly on `master`; do not create a worktree because the user explicitly chose direct work.
- Preserve unrelated working-tree changes: `.DS_Store`, `.claude/worktrees/agent-a9ffac2fda3444603`, and `docs/superpowers/plans/2026-09-20-clickable-artists-and-albums.md`.
- Do not add dependencies or expose `FREQBLOG_API_KEY` outside the backend.
- Keep TIDAL BPM/key values authoritative; FreqBlog only fills missing values and supplies optional metadata.
- Unfiltered track searches must not await a FreqBlog provider call. BPM/key-filtered searches must continue to enrich before filtering.
- Bound background work to the visible page and the existing 50-track FreqBlog bulk limit.
- Artist, album, playlist, direct-link, preview, download, and queue semantics remain unchanged.

## Review Focus

- An uncached unfiltered search returns before a slow provider response; cover this in Task 2 with a blocked background enricher.
- Two matching visible-page requests share one provider batch; cover this in Task 1 with a call-count assertion.
- A completed stale job cannot overwrite a refreshed cache page with different track IDs; cover this in Task 2.
- BPM/key filters continue to use synchronously enriched candidates before local filtering; cover this in Task 2.
- A metadata event for an old search cannot add rows or clear the current page’s pending state; cover this in Task 3.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/search_metadata_jobs.py` | Own in-flight visible-page enrichment tasks, de-duplicate job keys, and invoke a completion callback. |
| `backend/tests/test_search_metadata_jobs.py` | Deterministic lifecycle and de-duplication tests for the job manager. |
| `backend/main.py` | Perform cache-only search merging, schedule jobs, update response-cache entries, and broadcast completed patches. |
| `backend/tests/test_search_routes.py` | Route-level tests for non-blocking, filtered, cache-update, and stale-job behavior. |
| `frontend/src/api.ts` | Define `metadata_pending` and the `catalog_metadata` WebSocket payload. |
| `frontend/src/context/AppContext.tsx` | Merge safe metadata patches into existing active search rows. |
| `frontend/src/context/AppContext.test.tsx` | Verify current-row merging, provenance precedence, and stale-message safety. |
| `frontend/src/components/SearchView.tsx` | Render the compact non-blocking metadata status. |
| `frontend/src/components/SearchView.test.tsx` | Verify the pending status is exposed to the user without replacing results. |

### Task 1: Create the background visible-page job manager

**Files:**
- Create: `backend/search_metadata_jobs.py`
- Create: `backend/tests/test_search_metadata_jobs.py`

**Interfaces:**
- Consumes: `enrich(tracks: list[dict]) -> Awaitable[list[dict]]` and `on_complete(subscriptions: dict[str, tuple[int, ...]], tracks: list[dict]) -> Awaitable[None]`.
- Produces: `SearchMetadataJobManager.schedule(cache_key: str, tracks: list[dict]) -> bool` and `await SearchMetadataJobManager.close()`.

- [ ] **Step 1: Write the failing de-duplication and completion tests**

Start `backend/tests/test_search_metadata_jobs.py` with:

```python
import asyncio

import pytest

from backend.search_metadata_jobs import SearchMetadataJobManager
```

```python
@pytest.mark.asyncio
async def test_schedule_joins_matching_track_sets_and_notifies_all_cache_keys():
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    provider_calls = []
    notifications = []

    async def enrich(tracks):
        provider_calls.append([track["id"] for track in tracks])
        started.set()
        await release.wait()
        return [{**track, "genre": "dance", "genre_source": "freqblog"} for track in tracks]

    async def on_complete(subscriptions, tracks):
        notifications.append((subscriptions, tracks))
        completed.set()

    manager = SearchMetadataJobManager(enrich=enrich, on_complete=on_complete)
    tracks = [{"id": 7, "title": "Night Drive"}, {"id": 8, "title": "Day Shift"}]

    assert manager.schedule("first", tracks) is True
    await started.wait()
    assert manager.schedule("second", list(reversed(tracks))) is True
    release.set()
    await completed.wait()

    assert provider_calls == [[7, 8]]
    assert notifications[0][0] == {"first": (7, 8), "second": (8, 7)}
    assert notifications[0][1][0]["genre"] == "dance"
    await manager.close()
```

Add a second test where `enrich` raises `RuntimeError("provider unavailable")`; assert completion still runs with the original tracks so its caller can clear pending state.

```python
@pytest.mark.asyncio
async def test_schedule_notifies_with_original_tracks_after_enrichment_failure():
    completed = []
    finished = asyncio.Event()

    async def enrich(tracks):
        raise RuntimeError("provider unavailable")

    async def on_complete(subscriptions, tracks):
        completed.append((subscriptions, tracks))
        finished.set()

    manager = SearchMetadataJobManager(enrich=enrich, on_complete=on_complete)
    source = [{"id": 7, "title": "Night Drive"}]
    manager.schedule("search", source)
    await asyncio.wait_for(finished.wait(), timeout=1)

    assert completed == [({"search": (7,)}, source)]
    await manager.close()
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `rtk pytest backend/tests/test_search_metadata_jobs.py -q`  
Expected: FAIL because `backend.search_metadata_jobs` does not exist.

- [ ] **Step 3: Implement the manager with a narrow ownership boundary**

```python
class SearchMetadataJobManager:
    def __init__(self, *, enrich, on_complete):
        self._enrich = enrich
        self._on_complete = on_complete
        self._jobs: dict[tuple[int, ...], _PendingJob] = {}

    def schedule(self, cache_key: str, tracks: list[dict]) -> bool:
        job_key = tuple(sorted({int(track["id"]) for track in tracks}))
        if not job_key:
            return False
        pending = self._jobs.get(job_key)
        if pending:
            pending.subscriptions[cache_key] = tuple(int(track["id"]) for track in tracks)
            return True
        # Store the task before it can yield, then remove it in its own finally.
        subscriptions = {cache_key: tuple(int(track["id"]) for track in tracks)}
        self._jobs[job_key] = _PendingJob(subscriptions, list(tracks), None)
        self._jobs[job_key].task = asyncio.create_task(self._run(job_key))
        return True
```

`_run()` must await the injected enricher once, call `on_complete()` once with a snapshot of every subscription’s expected page-ID sequence, log unexpected errors, and remove its own job record in `finally`. `close()` must cancel and await all still-running tasks so application shutdown cannot close SQLite while a job is using it.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `rtk pytest backend/tests/test_search_metadata_jobs.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit the job manager checkpoint**

```bash
rtk git add backend/search_metadata_jobs.py backend/tests/test_search_metadata_jobs.py
rtk git commit -m "feat: add background search metadata jobs"
```

### Task 2: Schedule background enrichment from unfiltered search

**Files:**
- Modify: `backend/main.py:45-62, 85-96, 192-222, 261-379`
- Modify: `backend/tests/test_search_routes.py`

**Interfaces:**
- Consumes: `SearchMetadataJobManager` from Task 1 and existing `enrich_catalog_tracks()` cache/provider merge behavior.
- Produces: search responses with `metadata_pending: bool`, a cache-only unfiltered search path, and `_apply_search_metadata_completion(subscriptions, tracks)`.

- [ ] **Step 1: Write failing route and completion tests**

Change the test imports to `import time` and
`from unittest.mock import AsyncMock, MagicMock`, then add a test that stubs
`main._enrich_response_tracks` and `main.search_metadata_jobs`:

```python
async def test_unfiltered_search_merges_cached_metadata_and_schedules_background_work(
    monkeypatch, authenticated
):
    track = {"id": 7, "title": "Night Drive", "artist": "Pilot", "bpm": None, "key": None}
    cached_track = {**track, "genre": "dance", "metadata_status": "partial"}
    monkeypatch.setattr(main, "search_tidal", MagicMock(return_value={
        "tracks": [track], "artists": [], "albums": [], "playlists": [],
    }))
    enrich = AsyncMock(return_value=[cached_track])
    jobs = MagicMock()
    jobs.schedule.return_value = True
    monkeypatch.setattr(main, "_enrich_response_tracks", enrich)
    monkeypatch.setattr(main, "search_metadata_jobs", jobs)
    monkeypatch.setattr(main, "enrich_tracks", lambda session, tracks, top_n: tracks)

    result = await main.search(q="Night Drive", type="track")

    assert result["tracks"][0]["genre"] == "dance"
    assert result["metadata_pending"] is True
    enrich.assert_awaited_once_with(
        [track], required_fields={"bpm", "key", "genre"}, lookup_limit=0
    )
    assert jobs.schedule.call_args.args[1] == [cached_track]
```

Add these independent tests:

```python
async def test_filtered_search_enriches_before_filtering_without_background_job(
    monkeypatch, authenticated
):
    track = {"id": 7, "title": "Night Drive", "artist": "Pilot", "bpm": None, "key": None, "key_scale": None}
    monkeypatch.setattr(main, "search_tidal", MagicMock(return_value={
        "tracks": [track], "artists": [], "albums": [], "playlists": [],
    }))
    calls = []
    async def enrich(tracks, *, required_fields, lookup_limit=None):
        calls.append((required_fields, lookup_limit))
        return [{**track, "camelot": "8A", "metadata_status": "complete"}]
    jobs = MagicMock()
    monkeypatch.setattr(main, "_enrich_response_tracks", enrich)
    monkeypatch.setattr(main, "search_metadata_jobs", jobs)
    monkeypatch.setattr(main, "enrich_tracks", lambda session, tracks, top_n: tracks)

    result = await main.search(q="Night Drive", type="track", key="8A")

    assert result["tracks"][0]["camelot"] == "8A"
    assert calls[0] == ({"bpm", "key"}, None)
    jobs.schedule.assert_not_called()
```

```python
async def test_metadata_completion_updates_matching_cache_and_broadcasts(monkeypatch):
    key = "matching-page"
    original = {"id": 7, "title": "Night Drive", "genre": None}
    enriched = {**original, "genre": "dance", "genre_source": "freqblog"}
    main._search_results_cache[key] = main._SearchCacheEntry(
        expires_at=time.monotonic() + 60,
        result={"tracks": [original], "artists": [], "albums": [], "playlists": [],
                "offset": 0, "limit": 50, "has_more": False, "metadata_pending": True},
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(main.ws_manager, "broadcast", broadcast)

    await main._apply_search_metadata_completion({key: (7,)}, [enriched])

    assert main._search_results_cache[key].result["tracks"] == [enriched]
    assert main._search_results_cache[key].result["metadata_pending"] is False
    broadcast.assert_awaited_once_with({"type": "catalog_metadata", "tracks": [enriched]})
```

```python
async def test_metadata_completion_does_not_overwrite_changed_cache_page(monkeypatch):
    key = "refreshed-page"
    current = {"id": 99, "title": "New Search"}
    main._search_results_cache[key] = main._SearchCacheEntry(
        expires_at=time.monotonic() + 60,
        result={"tracks": [current], "artists": [], "albums": [], "playlists": [],
                "offset": 0, "limit": 50, "has_more": False, "metadata_pending": True},
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(main.ws_manager, "broadcast", broadcast)

    await main._apply_search_metadata_completion(
        {key: (7,)}, [{"id": 7, "title": "Old Search", "genre": "dance"}]
    )

    assert main._search_results_cache[key].result["tracks"] == [current]
    assert main._search_results_cache[key].result["metadata_pending"] is True
    broadcast.assert_awaited_once()
```

- [ ] **Step 2: Run the focused route tests to verify they fail**

Run: `rtk pytest backend/tests/test_search_routes.py -q`  
Expected: FAIL because the search response has no `metadata_pending`, no background manager exists in `main`, and cache completion is undefined.

- [ ] **Step 3: Implement cache-only merge, lifecycle wiring, and safe completion**

In `backend/main.py`:

1. Import `SearchMetadataJobManager`, declare `search_metadata_jobs: SearchMetadataJobManager | None = None`, initialize it after `await db.init()` in `lifespan`, and close it in the lifespan teardown.
2. Add an async enricher callback that calls the existing catalog service with `required_fields={"bpm", "key", "genre"}` and provider lookups enabled.
3. Add `_apply_search_metadata_completion(subscriptions, tracks)` that builds an ID-to-track map, preserves each cache entry’s current order, only replaces an entry if its `tracks` IDs exactly equal that cache key’s subscribed expected-ID sequence, sets `metadata_pending` false, then broadcasts one `catalog_metadata` message.
4. Preserve `metadata_pending` in `_copy_search_response()` with `bool(result.get("metadata_pending", False))`.
5. In the unfiltered `type == "track"` page path, call `_enrich_response_tracks(..., required_fields={"bpm", "key", "genre"}, lookup_limit=0)` before returning. Keep `enrich_tracks(..., 5)` immediately afterward to preserve full remix titles.
6. After the cache-only merge and title enrichment, schedule a job only if the page has tracks with non-`complete` metadata status and `search_metadata_jobs` is available. Set `metadata_pending` from the scheduler return value. Do not schedule in the filtered path.

The response shape must continue to include all four result arrays, pagination values, and existing track fields.

- [ ] **Step 4: Run the focused backend tests to verify they pass**

Run: `rtk pytest backend/tests/test_search_metadata_jobs.py backend/tests/test_search_routes.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit the backend integration checkpoint**

```bash
rtk git add backend/main.py backend/tests/test_search_routes.py
rtk git commit -m "feat: enrich search metadata in the background"
```

### Task 3: Apply live metadata patches safely in frontend state

**Files:**
- Modify: `frontend/src/api.ts:15-66, 164-168`
- Modify: `frontend/src/context/AppContext.tsx:1-14, 298-390`
- Modify: `frontend/src/context/AppContext.test.tsx`

**Interfaces:**
- Consumes: backend `SearchResult.metadata_pending` and WebSocket `{ type: "catalog_metadata", tracks: TrackResult[] }` messages from Task 2.
- Produces: a typed `CatalogMetadataMessage` and reducer behavior that updates only existing active track results.

- [ ] **Step 1: Write failing reducer tests for matching and stale patches**

```tsx
it('merges a matching catalog metadata patch without replacing TIDAL values', () => {
  renderHarness();
  dispatch({ type: 'SEARCH_SUCCEEDED', payload: makeSearchResult({
    tracks: [{ ...track, bpm: 126, key: 'C', bpm_source: 'tidal', key_source: 'tidal' }],
    metadata_pending: true,
  }) });

  dispatch({ type: 'WS_MESSAGE', payload: {
    type: 'catalog_metadata',
    tracks: [{ ...track, bpm: 128, key: 'Am', camelot: '8A', genre: 'dance',
      bpm_source: 'freqblog', key_source: 'freqblog', genre_source: 'freqblog',
      metadata_status: 'complete' }],
  } });

  expect(searchState().results?.tracks[0]).toMatchObject({
    bpm: 126, key: 'C', camelot: '8A', genre: 'dance',
    bpm_source: 'tidal', key_source: 'tidal', genre_source: 'freqblog',
  });
  expect(searchState().results?.metadata_pending).toBe(false);
});
```

Add a stale-message test: start with track ID `1` and `metadata_pending: true`, send a patch only for ID `99`, then assert the entire active `results` object is unchanged.

- [ ] **Step 2: Run the focused context tests to verify they fail**

Run: `rtk npm --prefix frontend test -- --run src/context/AppContext.test.tsx`  
Expected: FAIL because `catalog_metadata` is not in the WebSocket contract and the reducer does not handle it.

- [ ] **Step 3: Add the API contract and reducer merge helper**

In `frontend/src/api.ts`, add `metadata_pending?: boolean` to `SearchResult`, then model WebSocket payloads as a discriminated union that includes:

```ts
export interface CatalogMetadataMessage {
  type: 'catalog_metadata';
  tracks: TrackResult[];
}
```

In `AppContext.tsx`, add a pure metadata-patch helper. For every matching ID, preserve non-null current `bpm`, `key`, `bpm_source`, and `key_source`; fill missing values from the patch; merge safe supplemental values such as `camelot`, `open_key`, `key_label`, genre, confidence, source, and `metadata_status`. Do not append a patch-only row. In the `WS_MESSAGE` reducer case, clear `metadata_pending` only if at least one current row was updated.

- [ ] **Step 4: Run the focused context tests to verify they pass**

Run: `rtk npm --prefix frontend test -- --run src/context/AppContext.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Commit the live-state checkpoint**

```bash
rtk git add frontend/src/api.ts frontend/src/context/AppContext.tsx frontend/src/context/AppContext.test.tsx
rtk git commit -m "feat: apply live catalog metadata patches"
```

### Task 4: Show background metadata progress without blocking search

**Files:**
- Modify: `frontend/src/components/SearchView.tsx:399-409`
- Modify: `frontend/src/components/SearchView.test.tsx`

**Interfaces:**
- Consumes: `SearchResult.metadata_pending` from Task 3.
- Produces: an accessible, compact status beside the result count.

- [ ] **Step 1: Write the failing search-view status test**

```tsx
it('shows a non-blocking metadata status while a search result is being enriched', async () => {
  vi.mocked(search.query).mockResolvedValue(result({
    tracks: [track],
    metadata_pending: true,
  }));
  renderSearch();

  fireEvent.change(screen.getByRole('textbox', { name: /Search tracks/i }), {
    target: { value: 'Night Drive' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));

  expect(await screen.findByText('Completing DJ metadata…')).toHaveAttribute('role', 'status');
  expect(screen.getByText('Night Drive')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused view test to verify it fails**

Run: `rtk npm --prefix frontend test -- --run src/components/SearchView.test.tsx`  
Expected: FAIL because no pending-status text is rendered.

- [ ] **Step 3: Render the minimal status in the existing result summary**

At the result-count location, render the status only for track results with `results.metadata_pending` true:

```tsx
{results.metadata_pending && searchType === 'track' && (
  <span className="text-xs" role="status" style={{ color: 'var(--text-muted)' }}>
    Completing DJ metadata…
  </span>
)}
```

Keep it within the existing `aria-live="polite"` result container. Do not add a spinner, change the normal search loading state, or disable row actions.

- [ ] **Step 4: Run the focused frontend tests to verify they pass**

Run: `rtk npm --prefix frontend test -- --run src/components/SearchView.test.tsx src/context/AppContext.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Commit the search UX checkpoint**

```bash
rtk git add frontend/src/components/SearchView.tsx frontend/src/components/SearchView.test.tsx
rtk git commit -m "feat: show background metadata progress in search"
```

### Task 5: Verify the complete feature and manual live behavior

**Files:**
- Verify only: files from Tasks 1-4

**Interfaces:**
- Consumes: complete backend job, cache, WebSocket, reducer, and search-view feature.
- Produces: verification evidence before integration.

- [ ] **Step 1: Run all backend tests**

Run: `rtk pytest backend/tests/ -q`  
Expected: all tests pass; the opt-in real-network FreqBlog probe remains skipped.

- [ ] **Step 2: Run all frontend tests**

Run: `rtk npm --prefix frontend test -- --run`  
Expected: all test files and tests pass.

- [ ] **Step 3: Build the frontend**

Run: `rtk npm --prefix frontend run build`  
Expected: TypeScript and Vite production build succeed.

- [ ] **Step 4: Check the complete diff**

Run: `rtk git diff --check`  
Expected: no whitespace errors.

- [ ] **Step 5: Manually verify the local application**

1. Launch backend and frontend.
2. Search for a track with uncached FreqBlog metadata; confirm result rows render before the provider timeout.
3. Confirm `Completing DJ metadata…` is visible without disabling Preview or Download.
4. Confirm genre and `FreqBlog` badges appear in the same rows after the live message; confirm no second search, list reset, or reorder occurs.
5. Run a BPM/key-filtered search and confirm returned tracks are filtered from synchronously enriched metadata.
6. Disconnect the WebSocket, repeat an unfiltered search, and confirm the initial search remains usable; reconnect and repeat to confirm cached metadata appears.
7. Open an artist and album page to confirm their existing metadata behavior is unchanged.
