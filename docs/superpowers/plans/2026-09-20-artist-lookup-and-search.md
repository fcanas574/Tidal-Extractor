# Artist Lookup and Resilient Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dedicated artist search and a two-column artist page while making typed search results reliable and preserving the search session across app tabs.

**Architecture:** Extend the existing FastAPI search and resolve paths instead of creating a second catalog subsystem. Add a shared artist-detail service for both artist URLs and artist IDs, then lift the SearchView workflow into AppContext so tab unmounts do not erase it. Keep album search results and downloads working, but leave album-card navigation explicitly out of this slice.

**Tech Stack:** Python 3, FastAPI, `tidalapi==0.8.11`, pytest; React 18, TypeScript, Tailwind/CSS, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-20-artist-lookup-and-search-design.md`

## Global Constraints

- Add a dedicated `Artist` search mode to the existing type selector.
- Use TIDAL's supported search ceiling of 300 rather than asking the library for 500 items.
- Show latest albums, EPs, and singles sorted newest first; exclude `COMPILATION` entries.
- Preserve the complete search session while switching between Search, Queue, History, and Stats in the running app.
- Repair album search results and retain their existing download action, but defer album-card click navigation and album track inspection.
- Reuse the existing React, Tailwind, and CSS infrastructure; do not add a component library or animation dependency.
- Keep desktop and mobile layouts first-class, with independent loading, empty, and error states for artist sections.
- Keep the interface in English and preserve the validated dark editorial music-workspace direction.
- Do not add recommendations, a new music provider, compilation browsing, or a Queue/History/Stats redesign.

## Review Focus

- **Stale async search response:** a slower request for an older query/type must never replace newer results; pin this in `frontend/src/components/SearchView.test.tsx` during Task 5.
- **Missing or malformed release metadata:** missing dates must sort deterministically and explicit `COMPILATION` entries must never reach the release list; pin this in `backend/tests/test_search.py` during Task 1.
- **Partial artist detail failure:** top tracks must remain usable when release loading fails, and releases must remain usable when top-track loading fails; pin this in backend and ArtistView tests during Tasks 1 and 6.
- **Tab/type/filter transitions:** switching tabs must restore query/results, changing type must hide incompatible DJ filters, and changing filters must reset pagination; pin this in AppContext and SearchView tests during Tasks 4 and 5.
- **Album result semantics:** album search cards must expose download but must not accidentally become navigable before the later album feature; pin this in SearchView tests during Task 5.

## File Map

### Backend

- Modify `backend/search.py` — typed result formatting, release filtering/sorting, shared artist detail loading, and URL-resolution reuse.
- Modify `backend/main.py` — typed search route, bounded cache/freshness behavior, pagination metadata, and `GET /artist/{artist_id}`.
- Modify `backend/tests/test_search.py` — pure search, formatting, artist-detail, release-filter, and URL-resolution tests.
- Create `backend/tests/test_search_routes.py` — isolated async route tests for typed responses, cache bypass, pagination metadata, and artist ID lookup.

### Frontend

- Modify `frontend/src/api.ts` — shared search types, pagination metadata, artist detail method, abort signal, and fresh-search option.
- Modify `frontend/src/context/AppContext.tsx` — search-session state, actions, and result-page merging.
- Modify `frontend/src/context/AppContext.test.tsx` — reducer tests for search persistence and page merging.
- Modify `frontend/src/components/SearchView.tsx` — Artist mode, shared state wiring, race-safe requests, clear/retry behavior, and typed result rendering.
- Modify `frontend/src/components/SearchView.test.tsx` — Artist mode, tab restoration, stale request, filter reset, and album-card behavior.
- Modify `frontend/src/components/ArtistView.tsx` — two-column top-track/latest-release layout and independent section errors.
- Create `frontend/src/components/ArtistView.test.tsx` — artist-page layout content, release filtering presentation, and download-only release cards.
- Modify `frontend/src/test-setup.ts` — bind the jsdom localStorage implementation so the existing volume tests run under Node 25.

## Implementation Tasks

### Task 1: Build and test typed search and artist-detail helpers

**Files:**
- Modify: `backend/search.py:131-245`
- Modify: `backend/tests/test_search.py:1-190`

**Interfaces:**
- Consumes: the existing `tidalapi.Session.search`, `Session.artist`, `Artist.get_top_tracks`, and `Artist.get_albums` methods.
- Produces: `search_tidal(session, query, models=None, limit=50, offset=0, artist_filter=None) -> dict` with `tracks`, `artists`, `albums`, and `playlists` keys; `get_artist_details(session, artist_id: int) -> dict`; `format_album()` with `release_type` and normalized release date metadata.

- [ ] **Step 1: Add failing tests for artist search and typed result keys.**

  Add a `MagicMock` artist to `test_search.py`, return it from `mock_session.search`, call `search_tidal(..., models=["artist"])`, and assert that the formatted artist appears under `results["artists"]`, while the other three arrays still exist. Assert that the session call receives `models=[tidalapi.Artist]`, the requested limit, and offset.

- [ ] **Step 2: Add failing tests for release filtering and ordering.**

  Create album fakes with `type` values `ALBUM`, `EP`, `SINGLE`, and `COMPILATION`, plus dates in different orders and one missing date. Assert that `get_artist_details()` returns only the first three types, newest first, with a deterministic final position for the missing date.

- [ ] **Step 3: Add failing tests for independent artist-section errors.**

  Make `get_top_tracks()` raise while `get_albums()` succeeds, then reverse the failure. Assert that the successful section is returned and an `errors` object identifies only the failed section.

- [ ] **Step 4: Run the focused tests and confirm they fail for the missing behavior.**

  Run:

  ```bash
  rtk python3 -m pytest backend/tests/test_search.py -q
  ```

  Expected: the new artist/release tests fail because artists are not formatted, `search_tidal()` omits the artists key, and the current resolver returns every album without filtering.

- [ ] **Step 5: Implement the minimal helper changes.**

  Extend `model_map` with `"artist": tidalapi.Artist`, pass `offset` through to `session.search`, and always return all four typed arrays. Add a safe release-date helper that prefers `available_release_date`, then `release_date`, then `tidal_release_date`; add `release_type` to formatted albums. Implement `get_artist_details()` with per-section `try/except`, filter out `COMPILATION` and unsupported types, sort descending by the date helper, and cap the release list at eight entries. Refactor the artist branch of `resolve_url()` to call this helper while preserving its existing top-level response keys.

- [ ] **Step 6: Run the focused tests again.**

  Run:

  ```bash
  rtk python3 -m pytest backend/tests/test_search.py -q
  ```

  Expected: PASS, including the existing URL-resolution tests and the new artist/release tests.

- [ ] **Step 7: Commit the isolated backend helper checkpoint.**

  Stage only `backend/search.py` and `backend/tests/test_search.py`; do not stage `.DS_Store` or `.claude/worktrees/agent-a9ffac2fda3444603`.

### Task 2: Repair the search route and add ID-based artist lookup

**Files:**
- Modify: `backend/main.py:41-233`
- Create: `backend/tests/test_search_routes.py`

**Interfaces:**
- Consumes: `search_tidal()` and `get_artist_details()` from Task 1.
- Produces: `GET /search?q=...&type=track|artist|album|playlist&offset=0&limit=50&refresh=false`, returning the four typed arrays plus `offset`, `limit`, and `has_more`; `GET /artist/{artist_id}` returning the shared artist-detail shape.

- [ ] **Step 1: Write isolated route tests before changing `main.py`.**

  Import the route coroutine directly, temporarily replace `main.auth_manager` with an authenticated fake, clear the module cache, and monkeypatch `main.search_tidal`. Assert that an album request returns non-empty `albums`, an artist request returns non-empty `artists`, an unknown type produces a 400 response/error, and the response includes correct `offset`, `limit`, and `has_more` values.

- [ ] **Step 2: Add cache and fresh-retry tests.**

  Call the same search twice and assert the mocked TIDAL helper runs once while the cache entry is fresh. Call with `refresh=True` and assert it runs a second time. Use a cache key containing normalized query, type, offset, limit, BPM bounds, key, compatibility flag, and genre so changing any request input cannot reuse an unrelated page.

- [ ] **Step 3: Add an artist ID route test.**

  Patch `get_artist_details`, call the `/artist/42` coroutine with an authenticated fake, and assert it is called once with integer `42` and its detail payload is returned.

- [ ] **Step 4: Run the new route tests and confirm they fail.**

  Run:

  ```bash
  rtk python3 -m pytest backend/tests/test_search_routes.py -q
  ```

  Expected: failures because the route currently accepts no artist type, discards non-track arrays, has no TTL/fresh flag, and has no artist ID route.

- [ ] **Step 5: Implement the route contract.**

  Replace the current track-only cache with a small timestamped cache entry and a 60-second TTL. Normalize whitespace/case for cache identity, clamp `limit` to `1..300`, reject unsupported types with `HTTPException(400)`, request at most 300 TIDAL results, apply track scoring/DJ filters only to track mode, slice the selected typed collection, and calculate `has_more` from the available filtered collection. Add `refresh: bool = False` to bypass and replace the cache entry. Add `GET /artist/{artist_id}` and route it through `get_artist_details()` in a worker thread.

- [ ] **Step 6: Run route and backend regression tests.**

  Run:

  ```bash
  rtk python3 -m pytest backend/tests/test_search_routes.py backend/tests/test_search.py -q
  ```

  Expected: PASS.

- [ ] **Step 7: Commit the backend route checkpoint.**

  Stage only `backend/main.py` and `backend/tests/test_search_routes.py`.

### Task 3: Define the frontend search contract and API methods

**Files:**
- Modify: `frontend/src/api.ts:15-160`

**Interfaces:**
- Consumes: the response contract from Task 2.
- Produces: `SearchType`, `SearchFilters`, `SearchResult` with `artists`, `offset`, `limit`, and `has_more`; `ResolveResult.errors`; `search.query(..., signal?)`; `search.artist(artistId, signal?)`; and `refresh` request support.

- [ ] **Step 1: Add the shared TypeScript types.**

  Define:

  ```ts
  export type SearchType = 'track' | 'artist' | 'album' | 'playlist';
  export interface SearchFilters {
    offset?: number; limit?: number; refresh?: boolean;
    bpmMin?: number; bpmMax?: number; key?: string;
    keyCompatible?: boolean; genre?: string;
  }
  ```

  Add `artists`, `offset`, `limit`, and `has_more` to `SearchResult`; add `release_type` to `AlbumResult`; and add optional section errors to `ResolveResult`.

- [ ] **Step 2: Update URL construction and request cancellation.**

  Use `URLSearchParams` so `offset`, `limit`, `refresh`, and filters are encoded consistently. Pass an optional `AbortSignal` through `request()` for `search.query`, `search.artist`, and `resolve.url`.

- [ ] **Step 3: Add the ID-based artist method.**

  Implement:

  ```ts
  artist: (artistId: number, signal?: AbortSignal) =>
    request<ResolveResult>(`/artist/${artistId}`, { signal }),
  ```

- [ ] **Step 4: Run the frontend typecheck.**

  Run:

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm run build
  ```

  Expected: existing SearchView errors may appear until Tasks 4–5 update its local types; no API-file errors should remain.

### Task 4: Move search-session state into AppContext

**Files:**
- Modify: `frontend/src/context/AppContext.tsx:1-85,169-360`
- Modify: `frontend/src/context/AppContext.test.tsx`

**Interfaces:**
- Consumes: `SearchType`, `SearchFilters`, `SearchResult`, and `ResolveResult` from Task 3.
- Produces: `state.search` plus reducer actions for query/type/filter updates, initial/append success, errors, artist detail open/close, and loading-more state. `SET_TAB` remains search-state-neutral.

- [ ] **Step 1: Add failing reducer-harness tests.**

  Extend the existing AppContext harness with outputs for `state.search`. Test that `SEARCH_SUCCEEDED` stores results, `SET_TAB` to Queue and back leaves the results untouched, `SEARCH_MORE_SUCCEEDED` appends only the selected typed array without duplicate ids, and `OPEN_ARTIST` followed by `CLOSE_ARTIST` restores the prior result view.

- [ ] **Step 2: Run the focused context tests and confirm failure.**

  Run:

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm test -- --run src/context/AppContext.test.tsx
  ```

  Expected: the harness cannot read the new search state/actions yet.

- [ ] **Step 3: Add `SearchSession` and reducer actions.**

  Store committed query, `SearchType`, compatible filters, `SearchResult | null`, `ResolveResult | null`, `status`, `error`, `partialError`, and `loadingMore`. Implement typed append merging by id for tracks, artists, albums, and playlists. Keep search data in the provider even when `activeTab` changes.

- [ ] **Step 4: Run the context tests.**

  Run the same focused command; expected: PASS.

- [ ] **Step 5: Commit the shared-state checkpoint.**

  Stage only `frontend/src/context/AppContext.tsx` and `frontend/src/context/AppContext.test.tsx`.

### Task 5: Implement Artist search mode and resilient SearchView behavior

**Files:**
- Modify: `frontend/src/components/SearchView.tsx:1-279`
- Modify: `frontend/src/components/SearchView.test.tsx`

**Interfaces:**
- Consumes: the API methods from Task 3 and `state.search` actions from Task 4.
- Produces: dedicated artist result cards, ID-based artist opening, preserved Back behavior, race-safe searches, typed pagination, and album cards with download-only behavior.

- [ ] **Step 1: Add failing SearchView tests.**

  Add tests that:

  ```tsx
  // artist mode renders a result and opens the artist detail request
  fireEvent.click(screen.getByRole('button', { name: 'Artists' }));
  fireEvent.change(input, { target: { value: 'The Pilot' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search' }));
  await waitFor(() => expect(screen.getByText('The Pilot')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /Open artist The Pilot/i }));
  expect(search.artist).toHaveBeenCalledWith(3, expect.any(AbortSignal));
  ```

  Also test that a Queue → Search unmount/remount restores the query and results, an older deferred response is ignored after a newer search completes, filter changes restart at offset 0, and album cards expose `Download album ...` without an open/navigation action.

- [ ] **Step 2: Run the focused SearchView tests and confirm failure.**

  Run:

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm test -- --run src/components/SearchView.test.tsx
  ```

  Expected: Artist mode, shared state, and race-safety tests fail against the current local-state implementation.

- [ ] **Step 3: Replace local workflow state with AppContext search state.**

  Derive query, type, filters, results, artist detail, and request status from `state.search`; dispatch changes from inputs and controls. Keep an `AbortController`/request-generation ref local to the component so unmount aborts pending work and stale responses cannot dispatch success. Retry must pass `refresh: true` while preserving the current query and previous results until the replacement succeeds.

- [ ] **Step 4: Add the dedicated Artist mode.**

  Add `{ key: 'artist', label: 'Artists' }` to the type buttons. Render each artist as a semantic button/card with image, name, accessible `Open artist <name>` label, and an independent loading/error transition from the search results to ArtistView. Keep URL resolution working and send resolved artist data through the same context actions.

- [ ] **Step 5: Add explicit clear, filter, and pagination behavior.**

  Add a keyboard-accessible clear button when the query is non-empty. Hide track-only DJ refinement controls in Artist/Album/Playlist modes. Append the active typed collection on Load more using `has_more`; reset offset/results when the committed query, type, or compatible filters change. Keep album cards as non-clickable containers with only the existing download button.

- [ ] **Step 6: Run the focused SearchView tests.**

  Expected: PASS, including the five Review Focus cases assigned to this task.

- [ ] **Step 7: Commit the SearchView checkpoint.**

  Stage only `frontend/src/components/SearchView.tsx` and `frontend/src/components/SearchView.test.tsx`.

### Task 6: Redesign ArtistView for top tracks and latest releases

**Files:**
- Modify: `frontend/src/components/ArtistView.tsx:28-89`
- Create: `frontend/src/components/ArtistView.test.tsx`
- Modify: `frontend/src/components/SearchView.test.tsx:93-105`

**Interfaces:**
- Consumes: `ArtistResult`, filtered `AlbumResult[]`, `TrackResult[]`, and optional section errors from Task 3/5.
- Produces: responsive two-column artist content with larger release cards; album cards remain download-only.

- [ ] **Step 1: Write failing component tests.**

  Render an artist with two top tracks, an EP, a single, and no compilations. Assert headings `Top tracks` and `Latest releases`, release type/date metadata, top-track preview/download actions, album download actions, and an independent release error message when supplied. Assert there is no button named `Open album ...`.

- [ ] **Step 2: Implement the layout and states.**

  Keep the existing header/back path and top-track actions. Replace the full-width Albums section with a responsive grid whose desktop columns place dense tracks on the left and larger release art on the right; use `Latest releases` copy and release metadata. Render section-specific empty/error content without removing the other section. Keep release cards as non-clickable wrappers with only the Download button.

- [ ] **Step 3: Run ArtistView and SearchView tests.**

  Run:

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm test -- --run src/components/ArtistView.test.tsx src/components/SearchView.test.tsx
  ```

  Expected: PASS.

- [ ] **Step 4: Commit the artist-page checkpoint.**

  Stage only `frontend/src/components/ArtistView.tsx`, `frontend/src/components/ArtistView.test.tsx`, and the intentional SearchView test updates.

### Task 7: Stabilize the existing frontend test environment

**Files:**
- Modify: `frontend/src/test-setup.ts:1-4`
- Test: `frontend/src/components/AudioPlayerFooterVolume.test.tsx`

**Interfaces:**
- Consumes: jsdom's window-localStorage implementation.
- Produces: a Node-global `localStorage` with `clear`, `getItem`, `setItem`, and `removeItem` for all Vitest tests.

- [ ] **Step 1: Re-run the known targeted baseline.**

  Run:

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm test -- --run src/components/AudioPlayerFooterVolume.test.tsx
  ```

  Expected before the fix: failures caused by Node 25 exposing an incomplete global `localStorage` object.

- [ ] **Step 2: Install the jsdom storage binding.**

  After the test environment initializes jsdom, add:

  ```ts
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: window.localStorage,
  });
  ```

- [ ] **Step 3: Re-run the targeted volume suite.**

  Expected: PASS, including cleanup between tests and the volume integration expectation.

- [ ] **Step 4: Commit the test-environment checkpoint.**

  Stage only `frontend/src/test-setup.ts`.

### Task 8: Full verification and visual review

**Files:**
- Modify: any files required by failing verification only; keep unrelated `.DS_Store` and `.claude/worktrees/agent-a9ffac2fda3444603` changes unstaged.

**Interfaces:**
- Consumes: all completed backend/frontend tasks.
- Produces: verified implementation with no known regression in the existing suites.

- [ ] **Step 1: Run all backend tests.**

  ```bash
  rtk python3 -m pytest backend/tests/ -q
  ```

  Expected: all existing and new backend tests pass, with only the repository's known skip(s).

- [ ] **Step 2: Run all frontend tests.**

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor/frontend
  rtk npm test -- --run
  ```

  Expected: all test files pass.

- [ ] **Step 3: Build the frontend.**

  ```bash
  rtk npm run build
  ```

  Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 4: Check the diff and inspect changed files.**

  ```bash
  cd /Users/felipecanas/Projects/TidalExtractor
  rtk git diff --check
  rtk git status --short
  ```

  Expected: no whitespace errors; only the feature files and the pre-existing local metadata changes are present.

- [ ] **Step 5: Exercise the changed workflow manually.**

  With the backend and frontend running, verify: Artist search → artist page → Back; Queue → Search restores the query/results; album search displays downloadable album cards without navigation; latest releases exclude compilations; desktop two-column and narrow stacked layouts; loading, empty, partial, retry, keyboard focus, and reduced-motion states.

- [ ] **Step 6: Review the final diff for scope.**

  Confirm no album-click navigation, compilation section, new dependency, or unrelated queue/download behavior entered the patch. If Google Stitch access is available, compare the artist layout against the approved visual reference before final handoff.

## Plan Self-Review

1. **Spec coverage:** Every approved requirement maps to Tasks 1–8: artist mode and ID navigation (Tasks 1–5), release filtering and two-column page (Tasks 1 and 6), typed album-result repair without album navigation (Tasks 2 and 5), cache freshness/request races (Tasks 2 and 5), and cross-tab search preservation (Tasks 4 and 5).
2. **Placeholder scan:** The plan contains no TBD/TODO steps, vague “handle errors” instructions, or unassigned implementation work; every behavior has a file, interface, test, or verification command.
3. **Type consistency:** `SearchType`, `SearchFilters`, `SearchResult`, and `ResolveResult` are introduced in `api.ts` before AppContext and components consume them. Backend route keys match the frontend response fields: `artists`, `albums`, `playlists`, `offset`, `limit`, and `has_more`.
4. **Review-focus coverage:** stale responses are tested in Task 5; release metadata and compilation filtering in Task 1; partial detail errors in Tasks 1 and 6; tab/type/filter transitions in Tasks 4 and 5; and album download-only semantics in Tasks 5 and 6.

Plan complete and saved to `docs/superpowers/plans/2026-09-20-artist-lookup-and-search.md`.
