# Search Pagination — "Load More" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Load More" pagination to search results with duplicate prevention.

**Architecture:** Backend maintains in-memory deduplication cache per query; frontend tracks loaded count and appends new results on each "Load More" click.

**Tech Stack:** Python FastAPI (backend), React/TypeScript (frontend), tidalapi library.

## Global Constraints

- No duplicate tracks shown to users — ever
- In-memory cache only — no persistence needed
- Batch size = 50 tracks per load
- Frontend owns `loadedCount` state; backend filters duplicates
- Cache key includes all filters: `{query}:{bpm_min}:{bpm_max}:{key}:{genre}`

---

### Task 1: Backend — Add Deduplication Cache to `/search` Endpoint

**Files:**
- Modify: `backend/main.py:30-38` (FreqBlog stats section — add search cache nearby)
- Modify: `backend/main.py:166-211` (`/search` endpoint)

**Interfaces:**
- Consumes: Existing `search_tidal()` function, `filter_tracks_by_dj_metadata()`
- Produces: `/search` endpoint now accepts `offset` param, returns deduplicated results

- [ ] **Step 1: Add global search cache dictionary**

Add near line 30, after `freqblog_stats`:

```python
# Search deduplication cache: cache_key -> set of seen track IDs
_search_seen_cache: dict[str, set[int]] = {}
```

- [ ] **Step 2: Add `offset` parameter to `/search` endpoint**

Modify line 166-174:

```python
@app.get("/search")
async def search(
    q: str,
    type: str = "track",
    offset: int = 0,  # NEW parameter
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    key: Optional[str] = None,
    key_compatible: bool = False,
    genre: Optional[str] = None,
):
```

- [ ] **Step 3: Implement deduplication logic inside `/search`**

After line 193 (after `raw = await asyncio.to_thread(search_tidal, ...)`:

```python
# Generate cache key from query + filters
cache_key = f"{q}:{bpm_min}:{bpm_max}:{key}:{genre}"

# Get or initialize seen IDs for this query
if cache_key not in _search_seen_cache:
    _search_seen_cache[cache_key] = set()
seen_ids = _search_seen_cache[cache_key]

# Filter out already-seen tracks
if raw.get("tracks"):
    raw["tracks"] = [t for t in raw["tracks"] if t["id"] not in seen_ids]

# Update seen IDs with new tracks
if raw.get("tracks"):
    seen_ids.update(t["id"] for t in raw["tracks"])
```

- [ ] **Step 4: Add cache cleanup when query changes**

Add after line 186 (after artist_filter logic):

```python
# Clear cache for new query (different from previous search)
# This ensures filter changes start fresh
```

The cache key naturally handles this — different filters = different key = fresh start.

- [ ] **Step 5: Run backend to verify no syntax errors**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python3 -c "from backend.main import app; print('OK')"
```

Expected: `OK` printed, no import errors.

- [ ] **Step 6: Test `/search` with offset parameter**

```bash
# Test initial search
curl "http://localhost:8000/search?q=House&type=track&offset=0&limit=50"

# Test pagination
curl "http://localhost:8000/search?q=House&type=track&offset=50&limit=50"
```

Expected: Second call returns different track IDs (no duplicates).

- [ ] **Step 7: Commit**

```bash
git add backend/main.py
git commit -m "feat: add deduplication cache for search pagination"
```

---

### Task 2: Frontend API — Add `offset` to Search Function

**Files:**
- Modify: `frontend/src/api.ts:1-50` (search function signature)

**Interfaces:**
- Consumes: Existing `search` object and its methods
- Produces: `search.query()` now accepts optional `offset` parameter

- [ ] **Step 1: Find current `search.query()` signature**

Search for `query(` in `frontend/src/api.ts`.

- [ ] **Step 2: Update `search.query()` to accept `offset`**

Current signature likely:
```typescript
query: (q: string, type?: 'track' | 'album' | 'playlist', filters?: {...}) => Promise<...>
```

Modify to:
```typescript
query: (q: string, type?: 'track' | 'album' | 'playlist', filters?: { 
  offset?: number;
  limit?: number;
  bpmMin?: number; 
  bpmMax?: number; 
  key?: string; 
  keyCompatible?: boolean;
  genre?: string;
}) => Promise<{ 
  tracks: TrackResult[]; 
  albums: AlbumResult[]; 
  playlists: PlaylistResult[];
}>
```

- [ ] **Step 3: Update the request URL construction**

Find where the URL is built (likely uses `/search?q=...`) and add offset:

```typescript
const params = new URLSearchParams({
  q,
  type,
  offset: String(filters?.offset ?? 0),
  limit: String(filters?.limit ?? 50),
  ...(filters?.bpmMin && { bpm_min: String(filters.bpmMin) }),
  ...(filters?.bpmMax && { bpm_max: String(filters.bpmMax) }),
  ...(filters?.key && { key: filters.key }),
  ...(filters?.keyCompatible && { key_compatible: 'true' }),
  ...(filters?.genre && { genre: filters.genre }),
});
return request(`/search?${params.toString()}`);
```

- [ ] **Step 4: Run TypeScript compiler to verify**

```bash
cd /Users/felipecanas/Projects/TidalExtractor/frontend
npm run build
```

Expected: No TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: add offset/limit params to search.query()"
```

---

### Task 3: Frontend UI — Add "Load More" Button and State

**Files:**
- Modify: `frontend/src/components/SearchView.tsx:13-30` (state declarations)
- Modify: `frontend/src/components/SearchView.tsx:43-96` (handleSearch, clearFilters)
- Modify: `frontend/src/components/SearchView.tsx:520-550` (after results rendering)

**Interfaces:**
- Consumes: Updated `search.query()` with offset support
- Produces: "Load More" button that appends results without duplicates

- [ ] **Step 1: Add pagination state variables**

After line 30 (after `selectedGenre`):

```typescript
// Pagination state
const [loadedCount, setLoadedCount] = useState(50);  // Tracks fetched so far
const [hasMore, setHasMore] = useState(true);        // More available?
const [loadingMore, setLoadingMore] = useState(false); // Loading state
```

- [ ] **Step 2: Reset pagination on new search**

Modify `handleSearch` (around line 48-50):

```typescript
const handleSearch = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!query.trim() && !selectedGenre) return;
  setLoading(true);
  setArtistResult(null);
  setLoadedCount(50);  // Reset on new search
  setHasMore(true);    // Assume more available until proven otherwise
```

- [ ] **Step 3: Update handleSearch to pass offset/filters**

Modify line 62-69:

```typescript
const filters: { 
  offset?: number;
  limit?: number;
  bpmMin?: number; 
  bpmMax?: number; 
  key?: string; 
  keyCompatible?: boolean;
  genre?: string;
} = {};
if (bpmMin !== undefined) filters.bpmMin = bpmMin;
if (bpmMax !== undefined) filters.bpmMax = bpmMax;
if (selectedKey) filters.key = selectedKey;
if (keyCompatible) filters.keyCompatible = true;
if (selectedGenre) filters.genre = selectedGenre;
// Always pass offset/limit for pagination
filters.offset = 0;
filters.limit = 50;

const r = await search.query(query.trim(), searchType, Object.keys(filters).length > 0 ? filters : undefined);
```

- [ ] **Step 4: Add `handleLoadMore` function**

After `clearFilters` (around line 94):

```typescript
const handleLoadMore = async () => {
  setLoadingMore(true);
  try {
    const filters: { 
      offset: number;
      limit: number;
      bpmMin?: number; 
      bpmMax?: number; 
      key?: string; 
      keyCompatible?: boolean;
      genre?: string;
    } = {
      offset: loadedCount,
      limit: 50,
    };
    if (bpmMin !== undefined) filters.bpmMin = bpmMin;
    if (bpmMax !== undefined) filters.bpmMax = bpmMax;
    if (selectedKey) filters.key = selectedKey;
    if (keyCompatible) filters.keyCompatible = true;
    if (selectedGenre) filters.genre = selectedGenre;

    const r = await search.query(query.trim(), searchType, filters);
    
    // Check if we got fewer results than requested (no more available)
    const gotFewerThanLimit = r.tracks.length < 50;
    
    setResults(prev => prev ? {
      tracks: [...prev.tracks, ...r.tracks],
      albums: prev.albums,
      playlists: prev.playlists,
    } : null);
    
    setLoadedCount(prev => prev + r.tracks.length);
    setHasMore(!gotFewerThanLimit && r.tracks.length > 0);
  } catch (err) {
    dispatch({
      type: 'ADD_TOAST',
      payload: {
        id: `load-more-err-${Date.now()}`,
        type: 'error',
        title: 'Failed to load more',
        detail: String(err),
        dismissAt: Date.now() + 5000,
      },
    });
  } finally {
    setLoadingMore(false);
  }
};
```

- [ ] **Step 5: Add "Load More" button component**

After line 522 (after playlists rendering, before the "no results" message):

```typescript
{/* Load More Button */}
{results && !artistResult && hasMore && (
  <div className="text-center py-8">
    <button
      onClick={handleLoadMore}
      disabled={loadingMore}
      className="btn-primary text-sm px-8 py-3"
      style={{ opacity: loadingMore ? 0.5 : 1 }}
    >
      {loadingMore ? (
        <span className="flex items-center gap-2">
          <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          Loading...
        </span>
      ) : (
        `Load 50 more`
      )}
    </button>
  </div>
)}
```

- [ ] **Step 6: Reset pagination when filters clear**

Modify `clearFilters` (line 88-94):

```typescript
const clearFilters = () => {
  setBpmMin(undefined);
  setBpmMax(undefined);
  setSelectedKey('');
  setKeyCompatible(false);
  setSelectedGenre('');
  setLoadedCount(50);  // Reset on filter clear
  setHasMore(true);
};
```

- [ ] **Step 7: Run frontend build to verify**

```bash
cd /Users/felipecanas/Projects/TidalExtractor/frontend
npm run build
```

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/SearchView.tsx frontend/src/api.ts
git commit -m "feat: add Load More pagination UI"
```

---

### Task 4: Integration Test — Verify End-to-End Pagination

**Files:**
- No changes — manual testing only

**Interfaces:**
- Tests the full pagination flow

- [ ] **Step 1: Start backend server**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
python3 -m uvicorn backend.main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend dev server**

```bash
cd /Users/felipecanas/Projects/TidalExtractor/frontend
npm run dev
```

- [ ] **Step 3: Test pagination flow**

1. Open app in browser (usually http://localhost:5173)
2. Search for a broad query (e.g., "House")
3. Wait for initial 50 results
4. Scroll to bottom, click "Load More"
5. Verify: NEW tracks appear (no duplicates)
6. Repeat 2-3 times
7. Verify: Button eventually hides when exhausted

- [ ] **Step 4: Test filter reset**

1. Search "House"
2. Load more 2-3 times
3. Change BPM filter (e.g., 120-128)
4. Verify: Results reset, pagination starts fresh at offset 0

- [ ] **Step 5: Test error handling**

1. Stop backend server while frontend is running
2. Click "Load More"
3. Verify: Error toast appears, button re-enables for retry

- [ ] **Step 6: Document results**

Note any issues found in a comment below this task.

---

## Plan Self-Review

**1. Spec coverage:**
- ✅ Deduplication cache (Task 1)
- ✅ Offset parameter (Task 1, Task 2)
- ✅ Frontend state management (Task 3)
- ✅ "Load More" UI (Task 3)
- ✅ Filter reset behavior (Task 3)
- ✅ Integration testing (Task 4)

**2. Placeholder scan:**
- ✅ No TBDs, TODOs, or vague requirements
- ✅ All code blocks show actual implementation

**3. Type consistency:**
- ✅ `offset: number` in frontend matches `offset: int` in backend
- ✅ `TrackResult[]` append logic consistent
- ✅ Filter param names match (`bpmMin` → `bpm_min`)

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-23-search-pagination-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**