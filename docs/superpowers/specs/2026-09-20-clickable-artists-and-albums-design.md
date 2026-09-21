# Clickable Artists and Albums

**Date:** 2026-09-20  
**Status:** Draft for review  
**Scope:** Navigate from track and release metadata to artist and album detail views without losing the active search session

## Goal

Make the catalog feel connected: an artist name in any track row should open
the existing artist page, and an album identity should open an album detail
view with its complete track list. The user must be able to return to the
same search results, filters, and pagination state after exploring either
detail view.

## Understanding summary

- TidalExtractor is a local-first React SPA backed by FastAPI and
  `tidalapi==0.8.11`.
- The frontend deliberately uses an `activeTab` shell instead of a router.
  `AppContext` already owns the committed search session so Search can survive
  switching to Queue, History, or Stats.
- `SearchView` renders track, artist, album, and playlist results. `ArtistView`
  renders top tracks, all artist tracks, and latest releases.
- The backend already has `GET /artist/{artist_id}` and
  `GET /album/{album_id}/tracks`. The album endpoint currently returns tracks
  only, while `format_track()` exposes an album id but not an artist id.
- Album download actions already work through the queue API and must remain
  distinct from navigation actions.
- The established visual direction in `Design.md` requires semantic controls,
  visible focus, explicit loading/error/empty states, and no new router for
  this style of navigation.

## Decisions

| ID | Decision | Alternatives considered | Reason |
|---|---|---|---|
| D1 | Add a context-owned catalog detail mode inside the existing Search surface. | Introduce React Router routes; expand cards inline. | Preserves the current shell, keeps search state in one place, and avoids a new navigation dependency. |
| D2 | Navigate to artists by numeric TIDAL artist id. Add `artist_id` to formatted tracks and albums. | Infer an id from the artist name or construct a TIDAL URL in the browser. | Names are not unique; the backend already has the authoritative artist object and route. |
| D3 | Extend `GET /album/{album_id}/tracks` with an `album` metadata object while retaining the existing `tracks` field. | Add a second album endpoint; render incomplete metadata from the clicked card. | Reuses the existing authenticated fetch path and gives every album entry point the same complete detail contract. |
| D4 | Use separate semantic buttons for navigation and download. | Make the whole card clickable; nest the download button inside a link/button. | Prevents accidental downloads, avoids invalid nested interactive elements, and gives keyboard and touch users equivalent actions. |
| D5 | Extract shared `TrackRow` and `AlbumCard` presentation from screen-local markup. | Duplicate clickable metadata behavior in SearchView, ArtistView, and AlbumView. | A shared owner keeps labels, focus states, preview, download, and navigation behavior consistent. |
| D6 | Treat album detail as a full Search-surface detail state with an explicit “Back to search” action. | Open a modal or replace the entire application shell. | Album track lists need room to scan and act while the global queue, preview player, and search session remain available. |
| D7 | A pasted TIDAL album URL opens the same AlbumView after resolution. | Keep pasted album URLs as download-only search results. | It makes the existing album resolver behave consistently with clickable album results. |
| D8 | Keep album track loading bounded to the existing TIDAL album track response; no new pagination in this slice. | Add album-track pagination or infinite scroll. | Album track lists are a bounded detail view, and pagination would add complexity without a current product requirement. |

## User experience

### Artist navigation

In every rendered `TrackRow`—search results, the artist’s all-tracks list,
and an album’s track list—the artist name is a visible, keyboard-accessible
button when `artist_id` is present. Its accessible name is `Open artist
<artist name>`. Activating it loads the existing artist detail route and shows
`ArtistView` in the Search surface.

If a track has no artist id, its artist text remains readable plain text and
does not pretend to be actionable. Artist lookup errors preserve the previous
search state and show an inline retry plus “Back to search” action.

### Album navigation

Album navigation is available from all album identities currently shown to the
user:

- the album name and cover/info region in search album results;
- the album name and cover/info region in ArtistView latest releases;
- the album name in a track row when `album_id` is present; and
- a resolved TIDAL album URL.

The album navigation control uses the accessible name `Open album <album
name>`. The adjacent `Download` action remains a separate button and adds the
album to the queue without opening detail. Cards are not implemented as one
large click target when that would make the download action ambiguous.

### Album detail view

AlbumView presents:

- a `Back to search` control that returns to the exact prior search session;
- the album cover, album name, artist, release type, release date, track count,
  and quality when available;
- a primary `Download album <album name>` action;
- a track list using the shared TrackRow behavior;
- per-track Preview and Download actions; and
- explicit loading, empty, error/retry, and success-preserving states.

The artist name in the album header is also navigable when the album metadata
contains `artist_id`. The view does not add recommendations, related albums,
playlist editing, or a new player model.

### Navigation and state behavior

The Search session keeps its query, selected type, filters, results, pagination,
partial errors, and current detail state in `AppContext`.

- Opening an artist or album detail view does not clear the existing search
  results.
- `Back to search` closes only the detail state; it does not issue a new search.
- Switching to Queue, History, or Stats and returning to Search restores the
  same detail or result state, consistent with the existing search persistence
  behavior.
- Editing the query or changing the search type closes the current detail view
  before beginning a new search.
- Starting a second detail request cancels or invalidates the first request so
  stale artist/album responses cannot replace the newer selection.
- The preview player, queue state, activity panel, and settings panel remain
  global and are not reset by navigation.

## Data and API design

### Backend contracts

`backend/search.py` changes:

- `format_track(track)` adds `artist_id`, using the TIDAL track artist id when
  available and `null` otherwise.
- `format_album(album)` adds `artist_id` using the album artist id when
  available and `null` otherwise.
- Add an album-detail helper that loads the album object once, formats its
  metadata, loads its tracks, and returns:

  ```json
  {
    "album": {
      "id": 42,
      "name": "Example Album",
      "artist": "Example Artist",
      "artist_id": 7,
      "num_tracks": 10,
      "release_date": "2026-01-12",
      "release_type": "ALBUM",
      "quality": "LOSSLESS",
      "cover_url": "https://..."
    },
    "tracks": []
  }
  ```

`backend/main.py` keeps `GET /album/{album_id}/tracks` as the public route and
adds the `album` key to its successful response. The `tracks` key remains
unchanged so existing consumers and the download pipeline remain compatible.
Authentication and existing HTTP error behavior remain unchanged.

The existing `GET /artist/{artist_id}` response remains the source for artist
detail. No new TIDAL provider or artist endpoint is required.

### Frontend contracts

`frontend/src/api.ts` adds:

```ts
export interface AlbumDetailResult {
  album: AlbumResult;
  tracks: TrackResult[];
}

// TrackResult additions
artist_id: number | null;

// AlbumResult additions
artist_id: number | null;
```

The existing `search.albumTracks` method accepts an optional `AbortSignal` and
returns `AlbumDetailResult`. The existing artist method remains cancellable.

The AppContext detail state has one discriminated shape:

```ts
type CatalogDetail =
  | { kind: 'artist'; id: number; status: 'loading' | 'success' | 'error'; data: ResolveResult | null; error: string | null }
  | { kind: 'album'; id: number; status: 'loading' | 'success' | 'error'; data: AlbumDetailResult | null; error: string | null };
```

`SearchSession` owns `detail: CatalogDetail | null`; opening, loading,
success, failure, and closing detail are reducer actions. Existing search
results remain in the same session object while detail is active.

## Component boundaries

- `frontend/src/components/TrackRow.tsx` owns one track row’s metadata layout,
  artist/album navigation controls, preview action, download action, quality
  badge, and accessibility labels. It receives callbacks rather than owning
  search or queue requests.
- `frontend/src/components/AlbumCard.tsx` owns album cover/info presentation,
  the open-album control, and the separate download action. It receives the
  album and callbacks.
- `frontend/src/components/AlbumView.tsx` owns the album header, album-level
  loading/error/empty states, and the track list composition.
- `frontend/src/components/SearchView.tsx` owns request orchestration and
  dispatches detail actions; it does not duplicate album or track-row markup.
- `frontend/src/components/ArtistView.tsx` consumes the shared primitives and
  passes artist/album navigation callbacks.
- `frontend/src/context/AppContext.tsx` owns detail state and transitions but
  does not perform network requests.

## Failure and async behavior

- Detail requests use `AbortController` and a request generation/token. An
  aborted or stale response is ignored.
- Loading keeps the Search shell, player, and queue available; the detail
  content uses stable skeleton geometry.
- An album request failure shows the album-view error with `Retry` and `Back to
  search`; it does not erase the prior results.
- An empty album track list shows a clear empty state and keeps the album
  header/actions available.
- Missing artist or album ids produce non-clickable text, not broken controls.
- A failed navigation request never triggers a download or mutates the queue.

## Accessibility and visual behavior

- Use native `<button type="button">` controls for SPA navigation and actions;
  do not make a `div` or `<p>` clickable.
- Navigation controls have visible hover, pressed, and `:focus-visible`
  states and at least the existing 44px touch-target intent.
- Navigation button labels remain explicit: `Open artist …`, `Open album …`,
  `Download album …`, `Preview …`, and `Download …`.
- The album detail heading hierarchy follows the existing Search/Artist
  surface. Focus returns to the Back control after a failed load or after
  closing detail.
- Keep the established dark editorial music-workspace tokens, responsive
  stacking, and reduced-motion behavior from `Design.md`; no new visual
  library or animation dependency is allowed.

## Non-goals

- Introducing React Router, browser URL routes, or deep-linkable in-app detail
  pages.
- Making playlist cards or queue/history metadata navigable in this slice.
- Recommendations, related artists, favorites, ratings, or streaming controls.
- Album-track pagination, sorting, editing, or playlist creation.
- Changing queue/download semantics, preview streaming, authentication, or
  the existing artist release filtering rules.
- Adding a new TIDAL API provider or changing the pinned TIDALAPI version.

## Acceptance criteria

1. A track artist button opens the correct existing artist page using its
   numeric id from SearchView, ArtistView, and AlbumView track lists.
2. Album names/covers in search results, artist releases, and track rows open
   the correct AlbumView; missing ids remain plain text.
3. Pasted TIDAL album links open AlbumView rather than a download-only album
   result.
4. AlbumView shows metadata, album download, track preview, and per-track
   download actions without nesting or conflating navigation and download.
5. Back to search restores query, type, filters, results, pagination, and
   partial-error state without another network search.
6. Switching tabs and returning preserves the current search/detail session.
7. Loading, empty, error/retry, stale-response, and missing-id states are
   covered by tests and do not mutate the queue unexpectedly.
8. `npm test -- --run`, `npm run build`, the relevant backend pytest suites,
   and `git diff --check` pass before implementation is considered complete.

## Implementation order

1. Add backend artist/album ids and the backwards-compatible album-detail
   response.
2. Add shared TypeScript contracts and reducer detail state.
3. Extract shared TrackRow and AlbumCard primitives with navigation callbacks.
4. Add AlbumView and wire artist/album requests through SearchView.
5. Update SearchView and ArtistView entry points, including resolved album URLs.
6. Add focused backend, reducer, API, component, and interaction tests, then
   perform responsive and accessibility verification.
