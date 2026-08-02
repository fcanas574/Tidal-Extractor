# Instant Full-Track Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return the full-track stream URL immediately and move waveform/key/BPM work behind a separately polled metadata lifecycle.

**Architecture:** Add `/preview/{track_id}/stream` for fast URL resolution and `/preview/{track_id}/metadata` for a per-track analysis job snapshot. Keep `/preview/{track_id}` unchanged. The frontend starts `Audio` from the stream response and polls metadata only while that track is active.

**Tech Stack:** FastAPI, asyncio tasks, Python dataclasses, React hooks, TypeScript fetch API, existing SQLite cache.

## Global Constraints

- The stream endpoint must not call waveform or local key detection.
- The metadata job must never delay browser audio playback.
- A late response for an old track must not mutate the active player.
- The old combined endpoint remains callable.
- Polling is used instead of adding preview events to the download WebSocket.

---

### Task 1: Define preview job state and endpoint contracts

**Files:**
- Create: `backend/preview_jobs.py`
- Test: `backend/tests/test_preview_jobs.py`

**Interfaces:**
- Produces `PreviewMetadataSnapshot` with fields `track_id: int`, `status: Literal["queued", "processing", "complete", "failed"]`, `revision: int`, `waveform: dict | None`, `key: str | None`, `camelot: str | None`, `bpm: float | None`, `error: str | None`.
- Produces `PreviewJobManager.start_or_get(track_id: int, stream_url: str, duration: float | None) -> PreviewMetadataSnapshot`.
- Produces `PreviewJobManager.snapshot(track_id: int) -> PreviewMetadataSnapshot | None`.
- Produces `PreviewJobManager.active_job_count() -> int` and `PreviewJobManager.run_pending_for_test() -> None` for deterministic unit tests.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_or_get_is_idempotent():
    manager = PreviewJobManager(analyzer=lambda *_: {})
    first = manager.start_or_get(12, "https://example.test/stream", 240.0)
    second = manager.start_or_get(12, "https://example.test/stream", 240.0)
    assert first.track_id == second.track_id == 12
    assert manager.active_job_count() == 1


def test_snapshot_reports_failed_job():
    manager = PreviewJobManager(analyzer=lambda *_: (_ for _ in ()).throw(RuntimeError("decode failed")))
    manager.start_or_get(12, "https://example.test/stream", 240.0)
    manager.run_pending_for_test()
    snapshot = manager.snapshot(12)
    assert snapshot.status == "failed"
    assert snapshot.error == "decode failed"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest backend/tests/test_preview_jobs.py -q`

Expected: FAIL because `backend/preview_jobs.py` does not exist.

- [ ] **Step 3: Implement the minimal in-memory manager**

Use an `asyncio.Task` per track, retain the latest snapshot under an `asyncio.Lock`, increment `revision` whenever a snapshot changes, and remove completed jobs only after their terminal snapshot is available. The manager must cancel and replace a job only when explicitly requested; repeated `start_or_get` calls must return the existing job.

- [ ] **Step 4: Run the focused test**

Run: `python3 -m pytest backend/tests/test_preview_jobs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/preview_jobs.py backend/tests/test_preview_jobs.py
git commit -m "feat: add preview metadata job lifecycle"
```

### Task 2: Add fast stream and metadata endpoints

**Files:**
- Modify: `backend/main.py:264-290, 475-497`
- Modify: `backend/preview_jobs.py`
- Test: `backend/tests/test_preview_routes.py`

**Interfaces:**
- `GET /preview/{track_id}/stream` returns `{track_id: int, stream_url: str, duration: float | None}`.
- `GET /preview/{track_id}/metadata` returns `PreviewMetadataSnapshot` as JSON.
- `PreviewJobManager` consumes an analyzer callback that initially calls the existing `get_waveform_cached` and `_detect_preview_key` functions in a background task; the streaming waveform plan replaces that callback with `analyze_stream` while preserving the snapshot contract.

- [ ] **Step 1: Write route tests**

```python
def test_stream_route_returns_before_analyzer(monkeypatch):
    monkeypatch.setattr(main.auth_manager, "is_authenticated", True)
    monkeypatch.setattr(main.auth_manager.session, "track", fake_track)
    monkeypatch.setattr(main, "get_waveform_cached", lambda _: (_ for _ in ()).throw(AssertionError("must not run")))
    response = client.get("/preview/123/stream")
    assert response.status_code == 200
    assert response.json()["stream_url"] == "https://example.test/full-track"


def test_metadata_route_returns_processing_snapshot(monkeypatch):
    response = client.get("/preview/123/metadata")
    assert response.status_code == 200
    assert response.json()["track_id"] == 123
    assert response.json()["status"] in {"queued", "processing", "complete"}
```

- [ ] **Step 2: Run the tests to verify the new routes fail**

Run: `python3 -m pytest backend/tests/test_preview_routes.py -q`

Expected: FAIL with 404 for the new routes.

- [ ] **Step 3: Implement `/stream`**

Resolve the track and temporarily request the existing low-quality URL exactly as the current endpoint does. Return immediately after `track.get_url()`; do not call waveform generation or key detection. Include `track.duration` when available.

- [ ] **Step 4: Implement `/metadata`**

Resolve the same low-quality URL, call `start_or_get`, and return the current snapshot. The analyzer must catch its own errors and convert them into `failed` snapshots rather than raising into the stream route.

- [ ] **Step 5: Run route tests**

Run: `python3 -m pytest backend/tests/test_preview_routes.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/preview_jobs.py backend/tests/test_preview_routes.py
git commit -m "feat: add instant preview stream and metadata routes"
```

### Task 3: Switch the player to the fast lifecycle

**Files:**
- Modify: `frontend/src/api.ts:206-214`
- Modify: `frontend/src/components/AudioPlayerFooter.tsx:231-259`
- Test: `frontend/src/components/AudioPlayerFooter.test.tsx`

**Interfaces:**
- `preview.getStream(trackId)` returns `PreviewStream { track_id: number; stream_url: string; duration: number | null }`.
- `preview.getMetadata(trackId)` returns `PreviewMetadataSnapshot` matching the backend contract.

- [ ] **Step 1: Write the failing player tests**

```tsx
it('starts audio from the stream response before metadata resolves', async () => {
  preview.getStream = vi.fn().mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
  preview.getMetadata = vi.fn().mockImplementation(() => new Promise(() => {}));
  render(<PreviewHarness trackId={7} />);
  expect(await screen.findByTestId('audio-started')).toBeInTheDocument();
});

it('ignores metadata belonging to a replaced preview', async () => {
  // Resolve track 7 metadata after the harness has selected track 8.
  // The visible waveform must remain track 8's waveform.
});
```

- [ ] **Step 2: Run the focused frontend test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/AudioPlayerFooter.test.tsx`

Expected: FAIL because the player still waits for `preview.getUrl()`.

- [ ] **Step 3: Add typed API methods**

Keep `preview.getUrl()` unchanged for fallback. Add `getStream()` and `getMetadata()` using the existing `request<T>()` helper.

- [ ] **Step 4: Start audio immediately and poll metadata**

Use an `AbortController` for the stream request, a second controller for metadata polling, and a monotonically increasing local preview token. Construct `new Audio(stream_url)` as soon as the stream response arrives. Poll metadata every 750ms while `status` is not terminal. Apply a snapshot only when its `track_id` and local token still match the active preview.

- [ ] **Step 5: Add visible failure handling**

Add a `.catch()` for both requests. Stream failure clears the preview and creates an error toast. Metadata failure leaves audio playing and shows a non-blocking metadata fallback state.

- [ ] **Step 6: Run frontend tests and build**

Run: `cd frontend && npm test -- --run src/components/AudioPlayerFooter.test.tsx && npm run build`

Expected: PASS and a successful Vite build.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/AudioPlayerFooter.tsx frontend/src/components/AudioPlayerFooter.test.tsx
git commit -m "feat: start preview audio before metadata analysis"
```
