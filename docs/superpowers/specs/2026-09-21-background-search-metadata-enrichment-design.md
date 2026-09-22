# Background Search Metadata Enrichment Design

**Date:** 2026-09-21  
**Status:** Approved design; awaiting implementation-plan review

## Goal

Keep ordinary track searches fast while allowing their visible rows to gain
FreqBlog-derived BPM, key, genre, and provenance metadata shortly after the
initial result renders.

The search response must not wait for the FreqBlog provider. When background
work completes, matching rows in the current search update in place and can
show the existing genre and `FreqBlog` badges.

## User-facing behavior

1. An unfiltered track search returns TIDAL results immediately, with any
   previously cached catalog metadata already merged in.
2. If visible rows still need optional catalog metadata, the backend starts a
   deduplicated FreqBlog bulk lookup after sending the response.
3. The UI shows a small, non-blocking "Completing DJ metadata…" status while
   that lookup is in progress.
4. The existing live WebSocket sends completed metadata patches. The search
   view merges patches into only the rows it is currently displaying.
5. The genre and `FreqBlog` badges appear as soon as a matching patch arrives;
   the result order, title, queue actions, preview state, and scroll position
   remain unchanged.

BPM/key-filtered searches retain their current synchronous enrichment step,
because metadata is required to decide which tracks match a filter. Artist,
album, playlist, and direct-link detail flows also retain their existing
enrichment behavior.

## Scope

### Included

- Cache-only metadata merging on ordinary, unfiltered track-search pages.
- Background FreqBlog enrichment for the current page of unfiltered track
  results.
- In-flight-job deduplication for identical visible track sets.
- Updating the in-memory search-response cache when a job completes.
- WebSocket metadata patch delivery and safe frontend row merging.
- A non-blocking pending indicator in search results.

### Excluded

- Background enrichment for filtered searches, which need an authoritative
  answer before responding.
- Replacing the existing TIDAL genre-prefix search behavior.
- New FreqBlog browsing or discovery pages.
- Changes to downloads, preview metadata, artist/album contracts, or queue
  behavior.

## Architecture

### Backend request path

For a normal `GET /search?type=track` request with no BPM/key filter:

```text
TIDAL search + existing remix-title enrichment
    ↓
Catalog cache-only merge for the visible page (no provider call)
    ↓
Immediate response: tracks + metadata_pending
    ↓
Schedule a deduplicated background catalog-metadata job when needed
```

The cache-only merge uses the existing catalog metadata service with provider
lookups disabled. Cached FreqBlog metadata appears in the initial response at
SQLite-read speed; an uncached page never waits for the FreqBlog timeout.

Filtered searches continue to call the catalog metadata service with provider
lookups enabled before applying BPM/key filtering. This preserves the existing
filter contract.

### Background job manager

Add a focused backend job manager responsible only for visible search-page
metadata work. It receives formatted track dictionaries and a search-cache
key.

- A normalized, ordered set of TIDAL track IDs identifies an in-flight job.
- A duplicate search for the same visible page joins the existing job rather
  than issuing another FreqBlog bulk request.
- The job holds strong task references until completion so it is not collected
  prematurely.
- On completion, it merges the provider/cache result using the existing
  precedence rules, updates every subscribed search-cache entry, and emits a
  WebSocket patch.
- Provider exceptions remain contained by the existing FreqBlog/catalog
  boundaries. The job emits statuses such as `unavailable`, `queued`, or
  `rate_limited`, then clears the pending state without failing the search.

The manager does not own provider HTTP rules, SQLite serialization, or track
merge policy; those remain in `backend/freqblog.py`, `backend/models.py`, and
`backend/catalog_metadata.py` respectively.

### Search cache updates

The short-lived `_search_results_cache` entry created by the initial response
stores `metadata_pending: true` when a background job is scheduled. When the
job finishes, its corresponding entry is replaced with the enriched visible
rows and `metadata_pending: false`. A repeat request therefore sees the
enriched result without another TIDAL or FreqBlog request.

The update is conditional on each cached page still containing the original
ordered track-ID sequence recorded when that page joined the job. A stale task
must never overwrite a newer page that reused the same cache key after expiry
or refresh.

### WebSocket contract

Extend the existing local WebSocket message union with:

```json
{
  "type": "catalog_metadata",
  "tracks": [
    {
      "id": 123,
      "bpm": 124.0,
      "camelot": "8A",
      "genre": "dance",
      "bpm_source": "freqblog",
      "genre_source": "freqblog",
      "metadata_status": "complete"
    }
  ]
}
```

The payload may contain full formatted track records, but the frontend treats
it as a metadata patch. It updates rows only when their TIDAL IDs already
exist in the active track-search result; it never adds, removes, reorders, or
navigates rows in response to a background message. This makes messages from
an older search or another open tab harmless.

### Frontend state and UI

`SearchResult` gains an optional `metadata_pending` boolean. The search reducer
merges incoming `catalog_metadata` patches by ID into `results.tracks` and
clears `metadata_pending` once a patch affects the active result.

`SearchView` renders a compact live status near the result count only while
`metadata_pending` is true. It is supplemental—not a loading screen—and does
not block preview, download, filtering, pagination, or a new search. Existing
`TrackRow` behavior remains unchanged: it renders the genre and FreqBlog badge
when the patched metadata supplies their current source fields.

If the WebSocket is disconnected, the initial search remains fully usable.
The job still warms the SQLite and search-response caches; the user can see
metadata on a later request, but the app does not retry TIDAL search requests
solely to compensate for a disconnected live channel.

## Data precedence and safety

- TIDAL BPM/key values remain authoritative and are never replaced by a patch.
- FreqBlog may fill missing BPM/key values and add genre, Camelot, confidence,
  and provenance fields.
- The API key remains backend-only and is never included in WebSocket payloads,
  logs, cache keys, or frontend types.
- Background statuses are honest: a timeout or quota response is not treated as
  a metadata miss.
- All background work is bounded to the already-visible search page and the
  provider's existing 50-track batch limit.

## Testing requirements

### Backend

- An unfiltered track search performs cache-only merging and schedules, rather
  than awaits, provider enrichment.
- A filtered BPM/key search continues to await enrichment before filtering.
- A completed job updates its subscribed cache entry and broadcasts one
  `catalog_metadata` message.
- Duplicate visible pages share one in-flight provider lookup.
- A stale/changed cache entry is not overwritten by an older job.
- Provider failure clears pending metadata without failing the original search.

### Frontend

- API types accept `metadata_pending` and `catalog_metadata` messages.
- The reducer merges a metadata patch only into existing active search rows.
- An unrelated or stale patch leaves current results unchanged.
- The pending status is visible while work is outstanding and disappears after
  the relevant patch.
- Existing search, pagination, artist/album navigation, preview, and queue
  tests remain intact.

## Verification

Run the full backend and frontend suites plus the frontend production build.
Manually verify an uncached search renders before the FreqBlog timeout, then
watch its metadata badges appear without a second search or a page reset. Also
verify a BPM/key-filtered search, a disconnected WebSocket search, and an
artist/album detail view.
