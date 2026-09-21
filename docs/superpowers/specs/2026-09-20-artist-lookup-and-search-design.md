# Artist lookup and resilient search

**Date:** 2026-09-20  
**Status:** Draft for review  
**Scope:** Dedicated artist search, artist-page release layout, search correctness, and search-session persistence

## Goal

Make it possible to search specifically for an artist and open the existing
artist page, then make that page useful as a compact artist workspace. At the
same time, repair the search contract so artist, album, playlist, and track
results are returned consistently, and preserve the user's search while they
move between Search, Queue, History, and Stats.

## Understanding summary

- TidalExtractor is a local-first React SPA for downloading TIDAL tracks,
  albums, and playlists.
- The existing artist detail flow already resolves artist URLs and fetches top
  tracks and albums, but text search cannot return artists.
- The backend currently restricts the search model map to tracks, albums, and
  playlists, then returns only tracks from the search route even when other
  result types were fetched.
- SearchView owns query, type, filters, results, pagination, and artist detail
  locally. App tab changes unmount SearchView, so that state disappears.
- The current visual direction is the validated dark editorial music
  workspace: solid readable result surfaces, selective mint accents, and
  responsive layouts that preserve the download workflow.

## Decisions

| ID | Decision | Alternatives considered | Reason |
|---|---|---|---|
| D1 | Add a dedicated `Artist` search mode to the existing type selector. | Mix artists into every search; create a separate artist screen. | Keeps result semantics predictable and reuses the current Search surface. |
| D2 | Extend the existing search contract and add a shared artist-detail service. | Build a separate artist subsystem with duplicated data-fetching logic. | Minimizes API drift and lets pasted artist URLs and artist cards share behavior. |
| D3 | Add `GET /artist/{artist_id}` for ID-based navigation while retaining URL resolution. | Convert artist cards into synthetic TIDAL URLs in the client. | An explicit ID route is clearer and avoids coupling navigation to URL formatting. |
| D4 | Show latest albums, EPs, and singles sorted newest first; exclude compilations. | Show every artist album; include compilations in a secondary section. | Matches the requested “new releases” surface and avoids unrelated appearances. |
| D5 | Initially show a bounded presentation-sized release set, with the current download action. | Render an unbounded artist discography. | Keeps the artist page readable and avoids adding discography pagination to this slice. |
| D6 | Lift committed search state into AppContext. | Keep SearchView mounted but hidden; persist only in component state. | The shared state survives tab unmounts and is the existing coordination point. |
| D7 | Repair album search results, but defer clicking an album to inspect its tracks. | Add album detail navigation now. | Album lookup reliability is in scope; album exploration is an explicitly later feature. |
| D8 | Treat a fresh retry as a cache bypass and use a short bounded search cache. | Cache indefinitely; remove caching entirely. | Reduces stale new-release results without giving up protection against repeated requests. |

## Non-goals

- Album-card click navigation or an album detail/track-inspection screen.
- Recommendations, similar artists, or a new music provider.
- A redesign of Queue, History, Stats, authentication, or download behavior.
- Compilation browsing on the artist page.
- Persistent search restoration across application restarts unless the existing
  app state architecture requires it; this slice guarantees preservation while
  switching features in the running app.

## API and backend design

### Typed search

Extend the search model mapping to include `tidalapi.Artist`. The search route
will accept `type=artist` in addition to the existing track, album, and playlist
types. The response contract will retain the typed arrays and return the array
corresponding to the requested mode instead of discarding albums, playlists, or
artists.

The route will use TIDAL's supported search ceiling of 300 rather than asking
the library for 500 items. Pagination will be explicit: the backend returns
the requested page and a `has_more` value derived from the page boundary. The
cache key includes normalized query, type, offset, limit, and all server-side
filter inputs.

Artist search results contain the artist id, name, image URL, and a stable
TIDAL/share URL when available. The frontend uses the id for navigation.

### Artist detail

Add a backend artist-detail route that uses a shared service also called by
artist URL resolution. The service will:

1. Fetch the artist object.
2. Fetch the artist's top tracks using the existing TidalAPI capability.
3. Fetch the artist's albums.
4. Keep only album types representing albums, EPs, or singles.
5. Exclude `COMPILATION` entries.
6. Sort using the best available release date, preferring the available release
   date and falling back to the ordinary or TIDAL release date.
7. Return a bounded latest-release list for the artist page.

The existing artist URL resolver and the new ID route must produce the same
artist detail shape. A failure in releases must not prevent top tracks from
rendering, and vice versa; the response should preserve independently available
sections where the backend can do so.

### Album search

Album-mode search will return formatted album objects from the backend so the
existing album result cards can display and download them. No new click handler,
album detail route, or album track panel is added in this slice. The existing
album tracks endpoint remains available for the later album exploration feature.

### Freshness and request safety

- Use a short TTL for in-memory search entries.
- Add an internal fresh/retry path that bypasses the cache and replaces the
  cached entry with the newest successful response.
- Preserve the query and current results when a request fails.
- Normalize whitespace and case for cache identity without changing the query
  displayed to the user.
- Reset pagination when the committed query, type, or compatible filters change.
- Return no stale page over a newer page for the same search session.

## Frontend behavior

### Search surface

The existing type selector becomes:

```text
Tracks · Artists · Albums · Playlists
```

Artist mode shows image-backed artist cards with an accessible open action. A
successful artist selection replaces the result list with ArtistView while
retaining the search session underneath. Back returns to the same query, type,
filters, result page, and scroll context where practical.

Artist mode does not show track-only DJ filters. Switching away from Artist mode
clears or hides incompatible filters without clearing the committed query.

Album mode continues to expose the existing download action. Album cards are
not navigable yet; the later album feature will add that behavior deliberately.

### Shared search session

Add a search-session branch to AppContext/reducer containing:

- committed query and selected search type;
- active compatible filters;
- typed result collections and pagination metadata;
- loading, error, and retry state;
- current artist detail, if open;
- the previous search result view needed for Back.

SearchView reads and dispatches this state instead of keeping the workflow in
component-local state. `SET_TAB` must not clear it. Search requests use an
abort or request-generation guard so a slower previous query cannot overwrite a
newer one.

### Artist page layout

The existing artist header remains the identity anchor. On desktop, the content
below it becomes two responsive columns:

- **Top tracks:** the denser left column, retaining preview, download, and
  download-all actions.
- **Latest releases:** the wider right column, using larger album artwork and
  release metadata. Cards expose download actions but are not clickable in this
  release.

On narrow screens, the columns stack without hiding actions. Top tracks and
latest releases have independent loading, empty, and error states. A missing
artist image uses the existing fallback treatment. Keyboard focus, visible
focus rings, reduced motion, and semantic buttons remain consistent with the
validated frontend rework.

## Data and interaction flow

```text
Search mode = Artist
        │
        ▼
GET /search?type=artist
        │
        ▼
Artist result card ── open ──► GET /artist/{id}
        │                          │
        │                          ├─ top tracks
        │                          └─ latest non-compilation releases
        │
        └─ Back ──► preserved Artist search session

Search mode = Album
        │
        ▼
GET /search?type=album ──► album result cards + download
                                  │
                                  └─ album click navigation deferred
```

## Failure and empty states

| Case | Expected behavior |
|---|---|
| Artist search has no matches | Explain that no artists matched and preserve the search input. |
| Artist detail partially fails | Render the available section and show a retry action for the failed section. |
| Latest releases are absent | Show a clear empty release state rather than an empty layout. |
| Search request fails | Keep query, type, filters, and prior results; offer Retry. |
| Fresh search returns newer content | Replace the cached result and preserve the user's current search mode. |
| User changes tabs | Preserve the complete search session. |
| Album search returns results | Render album cards and existing download actions; do not navigate on card click. |

## Testing strategy

### Backend

- Artist model inclusion and artist result formatting.
- `/search?type=artist` response shape, pagination, and empty results.
- Album and playlist response collections are no longer dropped.
- Artist detail filtering excludes compilations and sorts by release date.
- URL resolution and ID-based artist detail share the same data shape.
- Cache identity, TTL/fresh bypass, pagination metadata, and error handling.

### Frontend

- Artist mode renders cards and opens ArtistView by id.
- Back restores the artist search session.
- Search state survives switching to another app tab and back.
- Album results render download actions without introducing click navigation.
- Older requests cannot overwrite newer results.
- Retry preserves the query and replaces stale cached results.
- Artist page renders independent top-track and release states responsively.

## Verification

Run the focused backend and frontend tests, the complete backend test suite,
frontend test suite, frontend build, and `git diff --check`. Review the artist
page and search flow at desktop and mobile widths, including empty, failed,
partial, loading, keyboard, and reduced-motion states. If Google Stitch access
is provided before implementation, use it to validate the two-column artist
composition and its responsive stacking; otherwise use the existing validated
frontend design direction.

## Implementation order

1. Add backend typed artist search and correct typed search responses.
2. Extract shared artist detail loading and add the ID route with release
   filtering/sorting.
3. Add frontend API types and Artist search mode/results.
4. Move search-session state into AppContext and preserve it across tabs.
5. Update ArtistView to the top-tracks/latest-releases layout.
6. Add reliability guards, fresh retry behavior, and pagination metadata.
7. Add focused tests and perform full verification.

Album click navigation remains a separate future plan after this slice is stable.
