# TIDAL Metadata Enrichment and Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a TIDAL-first, cached FreqBlog fallback that improves BPM, key, and genre metadata in search, artist, and album flows without making provider failures block catalog actions.

**Architecture:** Keep `backend/freqblog.py` as the provider transport/normalization boundary, add a SQLite-backed `backend/catalog_metadata.py` service for cache selection and precedence-aware merging, and call that service from the existing catalog endpoints before DJ filtering. Extend the existing `TrackResult` and `TrackRow` contract with optional metadata fields; keep the current TIDAL genre-prefix search and local Camelot compatibility logic.

**Tech Stack:** Python 3, FastAPI, `httpx==0.28.1`, `aiosqlite==0.20.0`, pytest/pytest-asyncio, React 18, TypeScript, Vitest, Testing Library, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-09-21-freqblog-metadata-enrichment-design.md`

## Global Constraints

- TIDAL BPM/key values remain authoritative whenever non-null.
- FreqBlog is server-side only; never expose `FREQBLOG_API_KEY` to the frontend.
- FreqBlog bulk payloads use a bare JSON array and process at most 50 tracks per request, per the [official OpenAPI contract](https://api.freqblog.com/openapi.json).
- Missing, queued, rate-limited, malformed, or unavailable provider metadata must preserve the TIDAL result and download/preview actions.
- Use ISRC first for exact matching and title/artist as the fallback lookup identity.
- The existing `genre:<value>` TIDAL prefix remains the first-pass genre behavior.
- Existing remix/version title handling remains unchanged.
- Preserve unrelated working-tree changes: `.DS_Store`, `.claude/worktrees/agent-a9ffac2fda3444603`, and `docs/superpowers/plans/2026-09-20-clickable-artists-and-albums.md`.
- Work directly in the current workspace; do not create a new worktree because the user explicitly requested direct work.

## Review Focus

- A TIDAL track with BPM/key and a conflicting FreqBlog response must retain TIDAL values — covered by Task 3 merge tests.
- A FreqBlog `202`, `429`, timeout, malformed response, or missing key must not fail search — covered by Task 1 provider tests and Task 4 route tests.
- Bulk results must map to the correct TIDAL track when ISRC is present or absent — covered by Task 1 matching tests.
- A track with a FreqBlog-only Camelot value must pass the existing compatible-key filter — covered by Task 4 filter tests.
- Existing rows without the new optional fields must render and remain downloadable — covered by Task 5 component tests and Task 6 search-flow tests.

---

### Task 1: Define the batched FreqBlog provider contract

**Files:**
- Modify: `backend/freqblog.py`
- Create: `backend/tests/test_freqblog.py`
- Preserve: `backend/tests/test_freqblog_api.py` as the opt-in real-network probe; do not convert it into a required suite test.

**Interfaces:**
- Consumes: formatted track dictionaries containing `id`, `title`, `artist`, and optional `isrc`.
- Produces: `lookup_track_metadata(track_title, artist, isrc=None) -> Optional[dict]` for the downloader, plus `lookup_tracks_metadata(tracks: list[dict]) -> dict[int, dict]` for catalog enrichment. Each batch result has `status` in `found`, `miss`, `queued`, `rate_limited`, or `unavailable`, and optional normalized `data`.

- [ ] **Step 1: Write the failing provider tests**

Add deterministic transport fakes in `backend/tests/test_freqblog.py` and cover the public behavior, not the implementation details:

```python
@pytest.mark.asyncio
async def test_bulk_lookup_prefers_isrc_and_preserves_input_mapping(monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "results": [{
                    "isrc": "US123",
                    "found": True,
                    "result": {
                        "bpm": 128.0,
                        "bpm_alt": None,
                        "bpm_confidence": 4.2,
                        "key": "A-Minor",
                        "key_confidence": 0.9,
                        "camelot": "8A",
                        "open_key": "1m",
                        "genre": "electronic",
                    },
                }],
            }

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    result = await lookup_tracks_metadata([{
        "id": 7,
        "title": "Night Drive",
        "artist": "The Pilot",
        "isrc": "US123",
    }])

    assert requests[0][1]["json"] == [{"isrc": "US123", "track": "Night Drive", "artist": "The Pilot"}]
    assert result[7]["status"] == "found"
    assert result[7]["data"]["camelot"] == "8A"


@pytest.mark.asyncio
async def test_bulk_lookup_splits_requests_at_fifty_items(monkeypatch):
    payloads = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"results": [
                {"track": row.get("track"), "artist": row.get("artist"), "isrc": row.get("isrc"), "found": False, "result": None}
                for row in payloads[-1]
            ]}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            payloads.append(kwargs["json"])
            return FakeResponse()

    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    tracks = [{"id": index, "title": f"Track {index}", "artist": "Artist"} for index in range(51)]
    result = await lookup_tracks_metadata(tracks)

    assert [len(payload) for payload in payloads] == [50, 1]
    assert list(result) == list(range(51))


@pytest.mark.asyncio
async def test_bulk_lookup_maps_queued_and_rate_limited_statuses_without_raising(monkeypatch):
    class QueuedResponse:
        status_code = 200

        def json(self):
            return {"results": [{"found": False, "backfill_status": "queued", "result": None}]}

        def raise_for_status(self):
            return None

    class RateLimitedResponse:
        status_code = 429

        def json(self):
            return {"detail": "quota exceeded"}

        def raise_for_status(self):
            return None

    class FakeClient:
        response = QueuedResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            return self.response

    client = FakeClient()
    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    queued = await lookup_tracks_metadata([{"id": 1, "title": "Queued", "artist": "Artist"}])
    client.response = RateLimitedResponse()
    limited = await lookup_tracks_metadata([{"id": 2, "title": "Limited", "artist": "Artist"}])

    assert queued[1]["status"] == "queued"
    assert limited[2]["status"] == "rate_limited"
```

Add tests for 404/malformed rows and for missing `FREQBLOG_API_KEY` returning `unavailable` without constructing a client. The assertions must verify payload length, `queued` mapping from `backfill_status`, and `rate_limited` mapping from HTTP 429.

- [ ] **Step 2: Run the focused tests and verify they fail for the missing contract**

Run:

```bash
rtk pytest backend/tests/test_freqblog.py -q
```

Expected: FAIL because `lookup_tracks_metadata` and the normalized status behavior do not exist yet. Fix test setup errors until the failures identify the missing provider behavior.

- [ ] **Step 3: Implement the minimal provider contract**

In `backend/freqblog.py`:

1. Add `FREQBLOG_BATCH_SIZE = 50` and a private `_headers()` helper that returns the user agent and API key without logging the key.
2. Add `_request_payload(track)` that always includes `track` and `artist` when present and includes `isrc` when present; the bulk body must be a bare list.
3. Add `normalize_track_metadata(data)` returning only `bpm`, `bpm_alt`, `bpm_confidence`, `key`, `key_int`, `mode`, `camelot`, `open_key`, `key_confidence`, and `genre`.
4. Add `lookup_tracks_metadata(tracks)` that partitions inputs into 50-item batches, posts to `/bulk`, zips the ordered response rows back to the input IDs, and maps provider statuses as specified by the tests.
5. Extend the existing single lookup signature to accept `isrc=None`; send an ISRC-only `/lookup` request when an ISRC is supplied so the provider’s exact-identifier path wins, otherwise send title/artist. Preserve partial normalized fields and return `None` for non-200 single-lookup responses. The bulk method carries queued status for catalog enrichment.
6. Keep all network exceptions inside the provider boundary and return explicit `unavailable` results instead of raising into catalog routes.

- [ ] **Step 4: Run the focused tests and the existing downloader tests**

Run:

```bash
rtk pytest backend/tests/test_freqblog.py backend/tests/test_downloader.py -q
```

Expected: all focused tests pass, including the existing downloader fallback tests.

- [ ] **Step 5: Commit the provider boundary**

```bash
rtk git add backend/freqblog.py backend/tests/test_freqblog.py
rtk git commit -m "feat: add batched FreqBlog metadata lookup"
```

### Task 2: Add the SQLite catalog metadata cache

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: TIDAL track IDs, ISRCs, normalized provider payloads, statuses, and expiry timestamps.
- Produces: `Database.get_catalog_metadata(tidal_ids, now=None) -> dict[int, dict]` returning only non-expired records, and `Database.set_catalog_metadata(entries) -> None` upserting normalized records.

- [ ] **Step 1: Write the failing cache tests**

Add tests using the existing `db` fixture:

```python
@pytest.mark.asyncio
async def test_catalog_metadata_cache_round_trips_normalized_data(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7,
        "isrc": "US123",
        "data": {"bpm": 128.0, "camelot": "8A", "genre": "electronic"},
        "status": "found",
        "checked_at": 100.0,
        "expires_at": 200.0,
    }])

    result = await db.get_catalog_metadata([7], now=150.0)

    assert result[7]["data"]["bpm"] == 128.0
    assert result[7]["status"] == "found"


@pytest.mark.asyncio
async def test_expired_catalog_metadata_is_not_returned(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": None, "data": {}, "status": "queued",
        "checked_at": 100.0, "expires_at": 120.0,
    }])

    assert await db.get_catalog_metadata([7], now=121.0) == {}


@pytest.mark.asyncio
async def test_catalog_metadata_upsert_replaces_previous_status(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": None, "data": {}, "status": "queued",
        "checked_at": 100.0, "expires_at": 200.0,
    }])
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": "US123", "data": {"bpm": 128.0}, "status": "found",
        "checked_at": 150.0, "expires_at": 300.0,
    }])

    result = await db.get_catalog_metadata([7], now=200.0)

    assert result[7]["status"] == "found"
    assert result[7]["data"] == {"bpm": 128.0}
```

The upsert test must assert that a later `found` record replaces a previous `queued` record for the same TIDAL ID.

- [ ] **Step 2: Run the model tests and verify the cache tests fail**

Run:

```bash
rtk pytest backend/tests/test_models.py -q
```

Expected: FAIL because the new methods/table do not exist.

- [ ] **Step 3: Implement the cache table and methods**

Extend `Database.init()` with a non-destructive table:

```sql
CREATE TABLE IF NOT EXISTS catalog_metadata_cache (
    tidal_id TEXT PRIMARY KEY,
    isrc TEXT,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    checked_at REAL NOT NULL,
    expires_at REAL NOT NULL
)
```

Implement `get_catalog_metadata()` with one parameterized `IN` query, JSON decoding, and `expires_at > now` filtering. Implement `set_catalog_metadata()` with `INSERT ... ON CONFLICT(tidal_id) DO UPDATE`, JSON encoding, and one commit for the supplied batch. Return TIDAL IDs as integers at the service boundary even though SQLite stores them as text.

- [ ] **Step 4: Run the model tests and the complete backend suite**

Run:

```bash
rtk pytest backend/tests/test_models.py -q
rtk pytest backend/tests/ -q
```

Expected: the focused cache tests and the full backend suite pass. Record any pre-existing warning from the real-network FreqBlog probe without changing that probe in this task.

- [ ] **Step 5: Commit the cache**

```bash
rtk git add backend/models.py backend/tests/test_models.py
rtk git commit -m "feat: cache catalog metadata lookups"
```

### Task 3: Implement precedence-aware catalog enrichment

**Files:**
- Create: `backend/catalog_metadata.py`
- Create: `backend/tests/test_catalog_metadata.py`

**Interfaces:**
- Consumes: `Database`, formatted TIDAL track dictionaries, and `lookup_tracks_metadata` results.
- Produces: `merge_catalog_metadata(track, lookup) -> dict` and `enrich_catalog_tracks(db, tracks, required_fields=None, lookup_limit=None) -> list[dict]`. The service accepts formatted TIDAL dictionaries and always returns the same number/order of dictionaries.

- [ ] **Step 1: Write the failing merge and service tests**

Add pure merge tests first:

```python
def test_merge_catalog_metadata_preserves_tidal_bpm_and_key():
    track = {"id": 7, "bpm": 126.0, "key": "C", "key_scale": "MINOR", "genre": None}
    lookup = {"status": "found", "data": {
        "bpm": 128.0, "key": "A-Minor", "camelot": "8A",
        "bpm_alt": 64.0, "genre": "electronic",
    }}

    result = merge_catalog_metadata(track, lookup)

    assert result["bpm"] == 126.0
    assert result["bpm_source"] == "tidal"
    assert result["key"] == "C"
    assert result["key_source"] == "tidal"
    assert result["genre"] == "electronic"
    assert result["genre_source"] == "freqblog"
    assert result["camelot"] == "8A"


def test_merge_catalog_metadata_fills_missing_dj_fields():
    result = merge_catalog_metadata(
        {"id": 7, "bpm": None, "key": None, "key_scale": None, "genre": None},
        {"status": "found", "data": {
            "bpm": 128.0, "key": "A-Minor", "camelot": "8A",
            "key_confidence": 0.9, "genre": "electronic",
        }},
    )

    assert result["bpm"] == 128.0
    assert result["bpm_source"] == "freqblog"
    assert result["key_source"] == "freqblog"
    assert result["key_confidence"] == 0.9


@pytest.mark.asyncio
async def test_enrich_catalog_tracks_uses_cache_before_provider(monkeypatch, db):
    await db.set_catalog_metadata([{
        "tidal_id": 7,
        "isrc": "US123",
        "data": {"bpm": 128.0, "genre": "electronic", "camelot": "8A"},
        "status": "found",
        "checked_at": 100.0,
        "expires_at": 9999999999.0,
    }])

    async def provider_must_not_run(tracks):
        raise AssertionError("cache hit should skip FreqBlog")

    monkeypatch.setattr("backend.catalog_metadata.lookup_tracks_metadata", provider_must_not_run)
    result = await enrich_catalog_tracks(
        db,
        [{"id": 7, "title": "Night Drive", "artist": "The Pilot", "bpm": None, "key": None, "genre": None}],
        required_fields={"bpm", "genre"},
    )

    assert result[0]["bpm"] == 128.0
    assert result[0]["genre"] == "electronic"
    assert result[0]["metadata_status"] == "complete"
```

Add a second test for a cache miss that patches the provider, asserts only missing fields are requested, writes the result, and returns all input tracks in their original order.

- [ ] **Step 2: Run the focused tests and verify the enrichment contract fails**

Run:

```bash
rtk pytest backend/tests/test_catalog_metadata.py -q
```

Expected: FAIL because the new module and functions do not exist.

- [ ] **Step 3: Implement the merge and cache/provider orchestration**

Implement these exact rules:

1. Initialize source fields from existing TIDAL values: `tidal` for non-null BPM/key, otherwise `None`.
2. Use cached non-expired rows first.
3. Select only tracks missing at least one `required_fields` value; default `required_fields` is `{"bpm", "key", "genre"}`.
4. Apply `lookup_limit` to provider candidates only; never truncate the returned track list.
5. Call `lookup_tracks_metadata()` once per provider batch and persist each result with TTLs: 30 days for `found`, 24 hours for `miss`, 5 minutes for `queued`/`rate_limited`/`unavailable`.
6. When FreqBlog has a human-readable key and Camelot value, preserve the human-readable provider key in an optional `key_label` field and store the direct `camelot` value for filtering/display; never synthesize a TIDAL `key_scale` from an unverified label.
7. Set `metadata_status` to `complete` when all requested fields are present, `partial` when some are present or the provider returned `miss`, and the provider status for queued/rate-limited/unavailable cases.
8. Return copies of track dictionaries so the caller’s input list is not mutated.

- [ ] **Step 4: Run the enrichment tests and full backend suite**

Run:

```bash
rtk pytest backend/tests/test_catalog_metadata.py -q
rtk pytest backend/tests/ -q
```

Expected: all enrichment and backend tests pass.

- [ ] **Step 5: Commit the enrichment service**

```bash
rtk git add backend/catalog_metadata.py backend/tests/test_catalog_metadata.py
rtk git commit -m "feat: merge cached catalog metadata"
```

### Task 4: Integrate enrichment with search and catalog detail endpoints

**Files:**
- Modify: `backend/search.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_search.py`
- Modify: `backend/tests/test_search_routes.py`

**Interfaces:**
- Consumes: `enrich_catalog_tracks()` from Task 3.
- Produces: formatted tracks with optional provider metadata; DJ filtering that accepts direct `camelot` values before falling back to TIDAL key conversion.

- [ ] **Step 1: Write failing integration tests**

Add a direct Camelot filter regression test:

```python
def test_filter_tracks_by_dj_metadata_accepts_provider_camelot():
    tracks = [{"id": 7, "bpm": None, "key": None, "key_scale": None, "camelot": "8A"}]
    assert main.filter_tracks_by_dj_metadata(tracks, None, None, "8A", False) == tracks
```

Add route tests that patch `main._enrich_response_tracks` with an async function which fills BPM/key/genre, then assert a filtered search includes the fallback track, an enrichment exception preserves the raw TIDAL track, and album/artist responses pass their track lists through the same helper.

- [ ] **Step 2: Run the focused search tests and verify the new behavior fails**

Run:

```bash
rtk pytest backend/tests/test_search.py backend/tests/test_search_routes.py -q
```

Expected: FAIL because filtering ignores direct Camelot data and routes do not call the enrichment service.

- [ ] **Step 3: Add optional fields to `format_track()`**

In `backend/search.py`, retain all current fields and append optional defaults:

```python
"genre": None,
"camelot": None,
"open_key": None,
"key_label": None,
"bpm_alt": None,
"bpm_confidence": None,
"key_confidence": None,
"bpm_source": None,
"key_source": None,
"genre_source": None,
"metadata_status": None,
```

Do not alter `get_track_title()` or the remix/version title logic.

- [ ] **Step 4: Integrate enrichment before filtering and on detail responses**

In `backend/main.py`:

1. Import `enrich_catalog_tracks` and define `_enrich_response_tracks(tracks, *, required_fields, lookup_limit=None) -> list[dict]` as the single endpoint wrapper.
2. In `/search`, after scoring and before `filter_tracks_by_dj_metadata`, call the wrapper with `required_fields={"bpm", "key"}` only when BPM/key filters are active. Enrich the post-filter page with `required_fields={"bpm", "key", "genre"}` so visible rows receive optional metadata.
3. When no DJ filters are active, enrich only the selected page with `required_fields={"bpm", "key", "genre"}`.
4. Update `filter_tracks_by_dj_metadata()` to use `track["camelot"]` when present, otherwise `convert_to_camelot(track["key"], track["key_scale"])`.
5. Enrich `top_tracks` and returned track lists in artist summary/details, artist tracks, album tracks, and resolved TIDAL URL responses. Keep the existing progressive artist-page shape and partial errors.
6. Catch enrichment failures in `_enrich_response_tracks()`, log the failure, and return original TIDAL tracks. Provider-level statuses should normally prevent exceptions from reaching this boundary.

- [ ] **Step 5: Run focused and full backend tests**

Run:

```bash
rtk pytest backend/tests/test_search.py backend/tests/test_search_routes.py -q
rtk pytest backend/tests/ -q
```

Expected: all tests pass, including existing artist/album/remix tests.

- [ ] **Step 6: Commit endpoint integration**

```bash
rtk git add backend/search.py backend/main.py backend/tests/test_search.py backend/tests/test_search_routes.py
rtk git commit -m "feat: apply metadata enrichment to catalog flows"
```

### Task 5: Extend the frontend track contract and shared row

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/TrackRow.tsx`
- Modify: `frontend/src/components/TrackRow.test.tsx`

**Interfaces:**
- Consumes: the optional backend fields from Task 4.
- Produces: accessible, compact metadata badges that work with both old and enriched API responses.

- [ ] **Step 1: Write the failing row tests**

Add a test with a FreqBlog-only track:

```tsx
it('renders optional genre and direct Camelot metadata', () => {
  render(
    <TrackRow
      track={{ ...track, bpm: 128, key: null, key_scale: null, camelot: '8A', genre: 'electronic', bpm_source: 'freqblog', genre_source: 'freqblog' }}
      isPreviewing={false}
      onPreview={vi.fn()}
      onDownload={vi.fn()}
    />,
  );

  expect(screen.getByText('8A')).toBeInTheDocument();
  expect(screen.getByText('electronic')).toBeInTheDocument();
  expect(screen.getByLabelText(/FreqBlog metadata/i)).toBeInTheDocument();
});
```

Add a second test that renders the existing `track` fixture without optional fields and asserts that the row still renders its title and Download button.

- [ ] **Step 2: Run the focused frontend test and verify it fails**

Run:

```bash
rtk npm test -- --run src/components/TrackRow.test.tsx
```

Expected: FAIL because the TypeScript contract lacks the optional fields and `TrackRow` does not render them.

- [ ] **Step 3: Extend `TrackResult` and implement the row badges**

In `frontend/src/api.ts`, add optional fields:

```ts
camelot?: string | null;
open_key?: string | null;
key_label?: string | null;
genre?: string | null;
bpm_alt?: number | null;
bpm_confidence?: number | null;
key_confidence?: number | null;
bpm_source?: 'tidal' | 'freqblog' | null;
key_source?: 'tidal' | 'freqblog' | null;
genre_source?: 'freqblog' | null;
metadata_status?: 'complete' | 'partial' | 'miss' | 'queued' | 'rate_limited' | 'unavailable' | null;
```

In `TrackRow.tsx`:

1. Prefer `track.camelot` before deriving Camelot from TIDAL key fields.
2. Render `track.genre` as a neutral technical badge when present.
3. Render one compact, text-labeled provider badge with an accessible label when any source is `freqblog`; do not use color alone.
4. Keep title, artist/album navigation, Preview, Download, and quality badge behavior unchanged.
5. Preserve stable badge spacing when optional metadata is absent.

- [ ] **Step 4: Run focused tests, typecheck, and frontend build**

Run:

```bash
rtk npm test -- --run src/components/TrackRow.test.tsx
rtk npm run build
```

Expected: focused tests pass and TypeScript/Vite build exits successfully.

- [ ] **Step 5: Commit the shared row contract**

```bash
rtk git add frontend/src/api.ts frontend/src/components/TrackRow.tsx frontend/src/components/TrackRow.test.tsx
rtk git commit -m "feat: display enriched track metadata"
```

### Task 6: Cover the end-to-end search/refinement contract

**Files:**
- Modify: `frontend/src/components/SearchView.test.tsx`
- Modify: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: enriched `TrackResult` values and existing `SearchView` filter controls.
- Produces: regression coverage proving the user can still search, refine, preview, download, open album/artist details, and use old responses.

- [ ] **Step 1: Write the failing flow tests**

Extend the existing `SearchView` fixture with an enriched track and add assertions that a search result shows the genre/FreqBlog badge, keeps the Preview and Download buttons, and still opens the artist and album. Add a response fixture without optional metadata and assert it renders normally.

Add an API contract assertion that an enriched JSON response is accepted without changing query encoding or cancellation behavior.

- [ ] **Step 2: Run the focused frontend suite and verify the new assertions fail before the flow is complete**

Run:

```bash
rtk npm test -- --run src/components/SearchView.test.tsx src/api.test.ts
```

Expected: the new enriched-row assertion fails until the Task 5 contract is present; after Task 5, rerun this step and confirm it passes.

- [ ] **Step 3: Keep the existing search flow unchanged**

Keep `SearchView.tsx`’s existing Refine controls, active chips, request cancellation, progressive detail loading, and download actions. The expected implementation changes are limited to the enriched `TrackResult` fixture and shared `TrackRow`; do not add a second refinement panel or alter search request behavior.

- [ ] **Step 4: Run the complete frontend suite and build**

Run:

```bash
rtk npm test -- --run
rtk npm run build
```

Expected: all frontend tests pass and the production build succeeds.

- [ ] **Step 5: Commit the end-to-end frontend coverage**

```bash
rtk git add frontend/src/components/SearchView.test.tsx frontend/src/api.test.ts
rtk git commit -m "test: cover enriched search results"
```

### Task 7: Whole-branch verification and review package

**Files:**
- Modify only files required by verification fixes; do not change unrelated dirty files.
- Evidence: `docs/superpowers/specs/2026-09-21-freqblog-metadata-enrichment-design.md` and this plan.

**Interfaces:**
- Consumes: all committed implementation tasks.
- Produces: a verified branch ready for code review, with any critical/important review fixes applied through another RED → GREEN cycle.

- [ ] **Step 1: Run the complete backend and frontend verification commands**

Run each command separately and record its exit code/output:

```bash
rtk pytest backend/tests/ -q
rtk npm test -- --run
rtk npm run build
rtk git diff --check 318b815..HEAD
```

If the repository’s backend suite reports only the pre-existing real-network probe warning, record it explicitly; do not turn that probe into a network-dependent required test.

- [ ] **Step 2: Run static UI checks and inspect the changed workflow**

Because the repository has `Design.md` but no `premium-ui.json` or bundled premium audit script, verify manually against `Design.md` and the existing component tests:

1. Start the backend/frontend using the documented README commands.
2. Search for a track with missing TIDAL BPM/key and confirm the row remains actionable.
3. Apply BPM and key filters and confirm a fallback-enriched result can match.
4. Open an album and artist page and confirm enriched rows use the same badges.
5. Exercise provider-unavailable behavior with no `FREQBLOG_API_KEY`; confirm TIDAL results remain visible.
6. Keyboard-tab through Refine, filter controls, track navigation, Preview, and Download.
7. Inspect a narrow viewport and `prefers-reduced-motion` behavior; no new layout jump should appear.

- [ ] **Step 3: Audit changed code for contract violations**

Run:

```bash
rtk rg -n "alert\(|confirm\(|prompt\(|onClick=\{\(.*\) =>" frontend/src/components/TrackRow.tsx frontend/src/components/SearchView.tsx
rtk git status --short
```

Confirm there are no browser dialogs, non-semantic new click targets, API-key logs, or modifications to the unrelated dirty files.

- [ ] **Step 4: Request a fresh code review**

Create the review package from the first implementation commit after the spec commit through `HEAD`, including the spec and this plan, and dispatch the repository’s code-review mechanism with these requirements:

- Verify TIDAL precedence, cache expiry, provider status handling, and batch mapping.
- Verify direct Camelot filtering and existing TIDAL key conversion.
- Verify old frontend responses and action buttons remain compatible.
- Classify findings as Critical, Important, or Minor.

Fix every Critical/Important finding with a new failing test, minimal implementation, focused test, and full-suite rerun. Record deferred Minor findings in the final handoff.

- [ ] **Step 5: Final status check**

Run:

```bash
rtk git status --short --branch
rtk git log --oneline -10
```

Report the exact test/build results, any deferred Minor findings, and the list of implementation commits. Do not claim completion until the verification output is fresh and read.
