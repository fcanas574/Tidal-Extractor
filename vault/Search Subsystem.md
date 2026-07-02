# Search Subsystem

How search queries become filtered, scored, paginated, enriched results.

**See:** [[Backend search]] · [[Backend main]] · [[DJ Filters]] · [[Frontend api]]

## The Core Challenge

**Tidal's API does not support offset-based pagination.** A single `session.search()` call returns up to N results with no way to ask for "page 2." TidalExtractor works around this by:
1. Fetching a **large batch** (limit=500) on first search
2. **Caching the full list** in-memory keyed by `{query}:{type}`
3. **Slicing** the requested page `[offset : offset+limit]` from the cache

## Endpoint: `GET /search`

### Params
```
q              query string (may be empty if genre set)
type           'track' | 'album' | 'playlist' (default 'track')
offset         int (default 0)
limit          int (default 50)
bpm_min, bpm_max   optional BPM range
key                optional Camelot key (e.g., '8A')
key_compatible     bool (expand to harmonic neighbors)
genre              optional genre name
```

### Flow (`main.py: search()`)

```
1. Auth check → 401 if not authenticated
2. Parse "track - artist" format → split into q + artist_filter
3. Build search_query:
     if genre: "genre:{genre} {q}" (or just "genre:{genre}" if q empty)
4. cache_key = "{search_query}:{type}"
5. Cache HIT  → all_tracks = cached list
   Cache MISS → search_tidal(limit=500)
                 → score_results(q, artist_filter)   # relevance sort
                 → cache the sorted full list
6. Apply DJ filters to FULL list (BPM + Camelot) BEFORE pagination
     filter_tracks_by_dj_metadata(all_tracks, bpm_min, bpm_max, key, key_compatible)
7. Slice page: filtered[offset : offset+limit]
8. enrich_tracks(top 5 of page)   # full_title / version
9. return { tracks: page, albums: [], playlists: [] }
```

### Critical Ordering
**Filters run on the full cached set, THEN the page is sliced.** This means:
- Page 2 of a filtered search correctly continues the filtered results
- Filter changes re-slice the same cached full set (no re-fetch needed)

## Scoring (`score_results`)

Relevance ranking applied once, at cache-population time:

| Signal | Points |
|--------|--------|
| Exact title match (`query in title`) | +10 |
| Partial title match (any word >2 chars) | +5 |
| Released within 30 days | +5 |
| Artist match (when " - " used) | +10 |

Sorted descending. Non-matching tracks get score 0 and sort to the bottom (but still appear).

## Enrichment (`enrich_tracks`)

Improves titles for the **visible top 5** only (saves API calls):
1. `track.full_title` (preferred — includes remix/version)
2. `{title} ({version})` (constructed)
3. `title` (fallback)

Silent on failure. Only top 5 enriched; rest pass through.

## Frontend Pagination ("Load More")

`SearchView.tsx` tracks:
- `loadedCount` (starts 50, reset on new search / filter change)
- `hasMore` (true until a page returns < 50)
- `loadingMore` (button spinner state)

`handleLoadMore` calls `search.query(q, type, {offset: loadedCount, limit: 50, ...filters})` and **appends** results:
```
setResults(prev => ({...prev, tracks: [...prev.tracks, ...newTracks]}))
setLoadedCount(prev => prev + newTracks.length)
setHasMore(newTracks.length === 50 && newTracks.length > 0)
```

## Caching Caveats

- `_search_results_cache` is **in-memory only** — cleared on restart
- Cache key is `{query}:{type}` — **filters are NOT in the key**. Filter changes re-slice the same cached set (fast) but don't trigger a re-fetch. If the underlying results should change with filters, this could be surprising.
- No eviction policy — the dict grows unbounded across a long session
- The cache stores **scored/sorted** results, so re-fetches (cache miss) re-sort

## Genre Search

- Frontend sends `q=""` + `genre="House"` as separate params
- Backend constructs `"genre:House"` (or `"genre:House {q}"` if q also present)
- 17 curated genres in the dropdown (House, Techno, Trance, Drum & Bass, etc.)
- Bug history: frontend once sent `genre:House` as `q`, backend re-prefixed → `genre:genre:House`. Fixed by splitting q and genre. See [[Gotchas & Traps]].

## See Also

- [[Backend search]] · [[Backend main]] · [[DJ Filters]] · [[Frontend api]]
