# Link Paste Feature Design

**Goal:** Allow users to paste Tidal URLs (tracks, albums, playlists, artists) into the search bar to resolve and download content directly, instead of searching by text.

## URL Detection (Frontend)

The existing search bar auto-detects whether input is a Tidal URL or a regular search query.

- If input starts with `https://tidal.com` or `https://listen.tidal.com`, treat as URL → call `GET /api/resolve?url=<encoded-url>`
- Otherwise, normal search flow unchanged

When a URL is detected, the search bar shows a "Resolving link..." loading state. The response renders in the same results area as search.

## Supported URL Formats

Both Tidal URL patterns are handled:

- `https://tidal.com/browse/{type}/{id}` (e.g. `/browse/track/123456`)
- `https://listen.tidal.com/{type}/{id}` (e.g. `/track/123456`)

Supported types: `track`, `album`, `playlist`, `artist`

URLs may include trailing path segments (e.g. `/track/123456/song-name`) — the parser extracts only the type and numeric ID.

## Resolve Endpoint (Backend)

`GET /resolve?url=<encoded-tidal-url>`

### Parsing

Backend parses the URL with regex to extract content type and numeric ID:

- Type: `track | album | playlist | artist`
- ID: numeric string

Invalid/unrecognized URLs return `422` with a descriptive error.

### Response Formats

**Track:**
```json
{
  "artist": null,
  "top_tracks": [],
  "tracks": [{"id": 123, "title": "...", ...}],
  "albums": [],
  "playlists": []
}
```

**Album:**
```json
{
  "artist": null,
  "top_tracks": [],
  "tracks": [],
  "albums": [{"id": 456, "name": "...", ...}],
  "playlists": []
}
```

**Playlist:**
```json
{
  "artist": null,
  "top_tracks": [],
  "tracks": [],
  "albums": [],
  "playlists": [{"id": "abc", "name": "...", ...}]
}
```

**Artist (extended response):**
```json
{
  "artist": {"id": 789, "name": "...", "image_url": "...", "bio": "..."},
  "top_tracks": [{"id": 1, "title": "...", ...}, ...],
  "albums": [{"id": 2, "name": "...", ...}, ...],
  "tracks": [],
  "playlists": []
}
```

The `tracks`, `albums`, `playlists` arrays reuse the same `format_track`/`format_album`/`format_playlist` helpers from `search.py`. The `artist` and `top_tracks` keys are only present for artist resolutions. Frontend checks for `artist` key to decide rendering mode.

### Implementation

New function `resolve_url(session, url)` in `backend/search.py`:

1. Regex-match URL to extract `content_type` and `content_id`
2. Call corresponding tidalapi method: `session.track(id)`, `session.album(id)`, `session.playlist(id)`, `session.artist(id)`
3. For artists: also call `artist.get_top_tracks()` and `artist.get_albums()`, format results
4. Return structured dict

New endpoint `GET /resolve` in `backend/main.py`:

1. Validate auth
2. Call `resolve_url(auth_manager.session, url)` in thread
3. Return result

## Artist Page (Frontend — new ArtistView)

When the resolve response contains a non-null `artist` key, the frontend renders `ArtistView` instead of the flat search results list.

### Layout

```
┌──────────────────────────────────────┐
│ [Artist Image]  Artist Name          │
│                 Bio snippet...        │
├──────────────────────────────────────┤
│ Top Tracks              [Download All]│
│ ┌────────────────────────────────────┐│
│ │ Track card (same as search results)││
│ │ Track card                         ││
│ └────────────────────────────────────┘│
├──────────────────────────────────────┤
│ Albums                                │
│ ┌────────────────────────────────────┐│
│ │ Album card (same as search results)││
│ │ Album card                         ││
│ └────────────────────────────────────┘│
└──────────────────────────────────────┘
```

- **Artist header**: Image (circle), name, bio (truncated to 2 lines)
- **Top Tracks section**: List of track cards with individual Download buttons. "Download All" button adds every top track to the queue.
- **Albums section**: List of album cards with Download buttons (same as search results)
- All cards reuse the existing glass/card styling from SearchView

### Artist type in api.ts

```typescript
export interface ArtistResult {
  id: number;
  name: string;
  image_url: string | null;
  bio: string | null;
}

export interface ResolveResult {
  artist: ArtistResult | null;
  top_tracks: TrackResult[];
  tracks: TrackResult[];
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}
```

### URL detection logic

In SearchView, before calling the search API:

```typescript
const isUrl = /^(https?:\/\/)?(listen\.)?tidal\.com/.test(query);
if (isUrl) {
  const result = await resolve.url(query);
  setResults(result);
} else {
  const result = await search.query(query, searchType);
  setResults(result);
}
```

The search type filter buttons (Tracks/Albums/Playlists) are hidden when a URL is pasted since the URL already specifies the content type.

## Error Handling

- Invalid Tidal URL → `422` from backend → frontend shows error toast: "Could not resolve this link"
- URL for content type not supported → `422` with message
- tidalapi lookup fails (e.g. ID not found, region-locked) → `404` from backend → toast: "Content not found on Tidal"
- Non-Tidal URL pasted → frontend doesn't send to resolve, falls through to normal search (which will just return empty results for a URL string)
