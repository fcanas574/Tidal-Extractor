# Link Paste Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the ability to paste Tidal URLs (tracks, albums, playlists, artists) into the search bar, resolve them server-side, and display results — including an artist page with top tracks and albums.

**Architecture:** Backend gains a `resolve_url()` function in `search.py` that parses Tidal URLs via regex, looks up the content with tidalapi, and returns a structured response. A new `GET /resolve` endpoint exposes it. Frontend auto-detects URLs in the search bar, calls resolve instead of search, and renders an `ArtistView` when the response contains artist data.

**Tech Stack:** Python (tidalapi, FastAPI), React, TypeScript

---

### Task 1: Backend URL parser and resolve_url function

**Files:**
- Modify: `backend/search.py` (add `parse_tidal_url` and `resolve_url` functions and `format_artist` helper)
- Test: `backend/tests/test_search.py` (add tests for URL parsing and resolve)

- [ ] **Step 1: Write the failing tests for `parse_tidal_url`**

Add to `backend/tests/test_search.py`:

```python
from backend.search import parse_tidal_url

def test_parse_tidal_url_track():
    result = parse_tidal_url("https://tidal.com/browse/track/12345")
    assert result == ("track", "12345")

def test_parse_tidal_url_track_listen():
    result = parse_tidal_url("https://listen.tidal.com/track/12345")
    assert result == ("track", "12345")

def test_parse_tidal_url_album():
    result = parse_tidal_url("https://tidal.com/browse/album/999")
    assert result == ("album", "999")

def test_parse_tidal_url_playlist():
    result = parse_tidal_url("https://listen.tidal.com/playlist/abc-123")
    assert result == ("playlist", "abc-123")

def test_parse_tidal_url_artist():
    result = parse_tidal_url("https://tidal.com/browse/artist/42")
    assert result == ("artist", "42")

def test_parse_tidal_url_with_trailing_slug():
    result = parse_tidal_url("https://listen.tidal.com/track/12345/song-name")
    assert result == ("track", "12345")

def test_parse_tidal_url_invalid():
    result = parse_tidal_url("https://spotify.com/track/12345")
    assert result is None

def test_parse_tidal_url_malformed():
    result = parse_tidal_url("https://tidal.com/browse/notreal/abc")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_search.py::test_parse_tidal_url_track -v`

Expected: FAIL with `ImportError: cannot import name 'parse_tidal_url'`

- [ ] **Step 3: Implement `parse_tidal_url`**

Add to `backend/search.py` after the existing `format_playlist` function:

```python
import re

TIDAL_URL_PATTERN = re.compile(
    r"https?://(?:listen\.)?tidal\.com/(?:browse/)?(track|album|playlist|artist)/([^\s/?]+)"
)

def parse_tidal_url(url: str):
    match = TIDAL_URL_PATTERN.match(url.strip())
    if not match:
        return None
    content_type = match.group(1)
    content_id = match.group(2)
    if content_type != "playlist" and not content_id.isdigit():
        return None
    return (content_type, content_id)
```

- [ ] **Step 4: Run parse tests to verify they pass**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_search.py -k "parse_tidal_url" -v`

Expected: All 8 parse tests PASS

- [ ] **Step 5: Write the failing tests for `resolve_url` and `format_artist`**

Add to `backend/tests/test_search.py`:

```python
from backend.search import resolve_url, format_artist

def test_format_artist():
    mock_artist = MagicMock()
    mock_artist.id = 42
    mock_artist.name = "Test Artist"
    mock_artist.image = MagicMock(return_value="https://img.tidal.com/artist.jpg")
    mock_artist.bio = "A test bio"
    result = format_artist(mock_artist)
    assert result["id"] == 42
    assert result["name"] == "Test Artist"
    assert result["image_url"] == "https://img.tidal.com/artist.jpg"
    assert result["bio"] == "A test bio"

def test_resolve_url_track():
    mock_session = MagicMock()
    mock_track = MagicMock()
    mock_track.id = 12345
    mock_track.title = "Test Song"
    mock_track.artist.name = "Test Artist"
    mock_track.album.name = "Test Album"
    mock_track.album.id = 99
    mock_track.duration = 240
    mock_track.audio_quality = "LOSSLESS"
    mock_track.explicit = False
    mock_track.isrc = None
    mock_track.listen_url = ""
    mock_session.track.return_value = mock_track

    result = resolve_url(mock_session, "https://listen.tidal.com/track/12345")
    assert len(result["tracks"]) == 1
    assert result["tracks"][0]["title"] == "Test Song"
    assert result["artist"] is None

def test_resolve_url_artist():
    mock_session = MagicMock()
    mock_artist_obj = MagicMock()
    mock_artist_obj.id = 42
    mock_artist_obj.name = "Test Artist"
    mock_artist_obj.image = MagicMock(return_value="https://img.tidal.com/artist.jpg")
    mock_artist_obj.bio = "A great artist"

    mock_top_track = MagicMock()
    mock_top_track.id = 1
    mock_top_track.title = "Top Hit"
    mock_top_track.artist.name = "Test Artist"
    mock_top_track.album.name = "Best Of"
    mock_top_track.album.id = 10
    mock_top_track.duration = 200
    mock_top_track.audio_quality = "LOSSLESS"
    mock_top_track.explicit = False
    mock_top_track.isrc = None
    mock_top_track.listen_url = ""
    mock_artist_obj.get_top_tracks.return_value = [mock_top_track]

    mock_album_obj = MagicMock()
    mock_album_obj.id = 99
    mock_album_obj.name = "Best Of"
    mock_album_obj.artist.name = "Test Artist"
    mock_album_obj.num_tracks = 12
    mock_album_obj.release_date = "2024-01-01"
    mock_album_obj.audio_quality = "LOSSLESS"
    mock_album_obj.image = MagicMock(return_value="https://img.tidal.com/album.jpg")
    mock_artist_obj.get_albums.return_value = [mock_album_obj]

    mock_session.artist.return_value = mock_artist_obj

    result = resolve_url(mock_session, "https://listen.tidal.com/artist/42")
    assert result["artist"]["name"] == "Test Artist"
    assert len(result["top_tracks"]) == 1
    assert result["top_tracks"][0]["title"] == "Top Hit"
    assert len(result["albums"]) == 1
    assert result["albums"][0]["name"] == "Best Of"

def test_resolve_url_invalid():
    mock_session = MagicMock()
    with pytest.raises(ValueError):
        resolve_url(mock_session, "https://spotify.com/track/12345")
```

- [ ] **Step 6: Run resolve tests to verify they fail**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_search.py -k "resolve_url or format_artist" -v`

Expected: FAIL with `ImportError: cannot import name 'resolve_url'`

- [ ] **Step 7: Implement `format_artist` and `resolve_url`**

Add to `backend/search.py` after `parse_tidal_url`:

```python
def format_artist(artist) -> dict:
    image_url = None
    try:
        image_url = artist.image(480)
    except Exception:
        pass
    return {
        "id": artist.id,
        "name": artist.name or "Unknown",
        "image_url": image_url,
        "bio": getattr(artist, "bio", None),
    }


def resolve_url(session: tidalapi.Session, url: str) -> dict:
    parsed = parse_tidal_url(url)
    if parsed is None:
        raise ValueError(f"Cannot parse Tidal URL: {url}")

    content_type, content_id = parsed
    empty = {"artist": None, "top_tracks": [], "tracks": [], "albums": [], "playlists": []}

    if content_type == "track":
        track = session.track(int(content_id))
        return {**empty, "tracks": [format_track(track)]}

    if content_type == "album":
        album = session.album(int(content_id))
        return {**empty, "albums": [format_album(album)]}

    if content_type == "playlist":
        playlist = session.playlist(content_id)
        return {**empty, "playlists": [format_playlist(playlist)]}

    if content_type == "artist":
        artist = session.artist(int(content_id))
        top_tracks = [format_track(t) for t in artist.get_top_tracks()]
        albums = [format_album(a) for a in artist.get_albums()]
        return {**empty, "artist": format_artist(artist), "top_tracks": top_tracks, "albums": albums}

    return empty
```

- [ ] **Step 8: Run all search tests to verify they pass**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_search.py -v`

Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/search.py backend/tests/test_search.py
git commit -m "feat: add parse_tidal_url, resolve_url, and format_artist"
```

---

### Task 2: Backend `/resolve` endpoint

**Files:**
- Modify: `backend/main.py` (add `GET /resolve` endpoint and import `resolve_url`)

- [ ] **Step 1: Add the import and endpoint**

In `backend/main.py`, update the import line:

```python
from backend.search import search_tidal, get_album_tracks, get_playlist_tracks, resolve_url
```

Add after the `/playlist/{playlist_id}/tracks` endpoint:

```python
@app.get("/resolve")
async def resolve_tidal_url(url: str):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        result = await asyncio.to_thread(resolve_url, auth_manager.session, url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Content not found: {e}")
    return result
```

- [ ] **Step 2: Verify the server starts**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -c "from backend.main import app; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/main.py
git commit -m "feat: add GET /resolve endpoint for Tidal URL resolution"
```

---

### Task 3: Frontend API client — add resolve function and types

**Files:**
- Modify: `frontend/src/api.ts` (add `ArtistResult`, `ResolveResult` interfaces and `resolve` API object)

- [ ] **Step 1: Add types and resolve API**

Add to `frontend/src/api.ts` after the `PlaylistResult` interface:

```typescript
export interface ArtistResult {
  id: number;
  name: string;
  image_url: string | null;
  bio: string | null;
}
```

Add after `PlaylistResult`:

```typescript
export interface ResolveResult {
  artist: ArtistResult | null;
  top_tracks: TrackResult[];
  tracks: TrackResult[];
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}
```

Add after the `history` export at the end of the file:

```typescript
export const resolve = {
  url: (url: string) => request<ResolveResult>(`/resolve?url=${encodeURIComponent(url)}`),
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/api.ts
git commit -m "feat: add ArtistResult, ResolveResult types and resolve.url API"
```

---

### Task 4: Frontend ArtistView component

**Files:**
- Create: `frontend/src/components/ArtistView.tsx`

- [ ] **Step 1: Create ArtistView component**

Create `frontend/src/components/ArtistView.tsx`:

```tsx
import { queue } from '../api';
import { useApp } from '../context/AppContext';
import type { ArtistResult, TrackResult, AlbumResult } from '../api';

export default function ArtistView({
  artist,
  topTracks,
  albums,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  albums: AlbumResult[];
}) {
  const { state, dispatch } = useApp();

  const handleAddToQueue = async (
    tidal_id: string | number,
    item_type: string,
    title: string,
    artist: string = '',
    album: string = '',
  ) => {
    try {
      await queue.add({
        tidal_id: String(tidal_id),
        item_type,
        title,
        artist,
        album,
        quality: state.settings.default_quality,
        format: state.settings.default_format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-${Date.now()}-${tidal_id}`,
          type: 'info',
          title: 'Added to queue',
          detail: title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to add to queue',
          detail: title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const handleDownloadAllTopTracks = async () => {
    for (const track of topTracks) {
      await handleAddToQueue(track.id, 'track', track.title, track.artist, track.album);
    }
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const qualityBadgeColor = (q: string) => {
    if (q.includes('hi_res') || q.includes('HI_RES')) return { bg: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' };
    if (q.includes('lossless') || q.includes('LOSSLESS')) return { bg: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' };
    if (q.includes('320')) return { bg: 'rgba(255, 192, 64, 0.1)', color: 'var(--warning)' };
    return { bg: 'var(--bg-surface)', color: 'var(--text-dim)' };
  };

  return (
    <div className="animate-fade-in">
      {/* Artist header */}
      <div className="glass p-6 mb-6 flex items-center gap-5">
        {artist.image_url ? (
          <img
            src={artist.image_url}
            alt={artist.name}
            className="w-20 h-20 rounded-full object-cover shrink-0"
            style={{ border: '2px solid var(--glass-border)' }}
          />
        ) : (
          <div
            className="w-20 h-20 rounded-full shrink-0 flex items-center justify-center text-2xl"
            style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
          >
            ♫
          </div>
        )}
        <div className="min-w-0">
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>
            {artist.name}
          </h2>
          {artist.bio && (
            <p
              className="text-xs mt-1 line-clamp-2"
              style={{ color: 'var(--text-muted)' }}
            >
              {artist.bio}
            </p>
          )}
        </div>
      </div>

      {/* Top Tracks */}
      {topTracks.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h3
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: 'var(--text-dim)' }}
            >
              Top Tracks
            </h3>
            <button
              onClick={handleDownloadAllTopTracks}
              className="btn-primary text-xs px-3 py-1.5"
            >
              ↓ Download All
            </button>
          </div>
          <div className="space-y-2">
            {topTracks.map((track, i) => {
              const qbc = qualityBadgeColor(track.quality);
              return (
                <div
                  key={track.id}
                  className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    {track.cover_url ? (
                      <img
                        src={track.cover_url}
                        alt=""
                        className="w-10 h-10 rounded-md object-cover shrink-0"
                        style={{ border: '1px solid var(--glass-border)' }}
                      />
                    ) : (
                      <div
                        className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                        style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                      >
                        ♪
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                        {track.title}
                      </p>
                      <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {track.artist} · {track.album} · {formatDuration(track.duration)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    <span
                      className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0"
                      style={{ background: qbc.bg, color: qbc.color }}
                    >
                      {track.quality}
                    </span>
                    <button
                      onClick={() => handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)}
                      className="btn-primary text-xs px-3 py-1.5 shrink-0"
                    >
                      ↓ Download
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Albums */}
      {albums.length > 0 && (
        <section>
          <h3
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: 'var(--text-dim)' }}
          >
            Albums
          </h3>
          <div className="space-y-2">
            {albums.map((album, i) => (
              <div
                key={album.id}
                className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {album.cover_url ? (
                    <img
                      src={album.cover_url}
                      alt=""
                      className="w-10 h-10 rounded-md object-cover shrink-0"
                      style={{ border: '1px solid var(--glass-border)' }}
                    />
                  ) : (
                    <div
                      className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                    >
                      ▦
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {album.name}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleAddToQueue(album.id, 'album', album.name, album.artist)}
                  className="btn-primary text-xs px-3 py-1.5 shrink-0 ml-3"
                >
                  ↓ Download
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/components/ArtistView.tsx
git commit -m "feat: add ArtistView component for resolved artist pages"
```

---

### Task 5: Frontend SearchView — URL detection and resolve integration

**Files:**
- Modify: `frontend/src/components/SearchView.tsx` (add URL detection, resolve call, ArtistView rendering, hide type buttons for URLs)

- [ ] **Step 1: Update SearchView with URL detection and resolve flow**

Replace the `SearchView.tsx` file contents with:

```tsx
import { useState } from 'react';
import { search, queue, resolve } from '../api';
import { useApp } from '../context/AppContext';
import type { TrackResult, AlbumResult, PlaylistResult, ArtistResult } from '../api';
import ArtistView from './ArtistView';

const TIDAL_URL_RE = /^(https?:\/\/)?(listen\.)?tidal\.com/;

export default function SearchView() {
  const { state, dispatch } = useApp();
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'track' | 'album' | 'playlist'>('track');
  const [results, setResults] = useState<{
    tracks: TrackResult[];
    albums: AlbumResult[];
    playlists: PlaylistResult[];
  } | null>(null);
  const [artistResult, setArtistResult] = useState<{
    artist: ArtistResult;
    top_tracks: TrackResult[];
    albums: AlbumResult[];
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const isUrl = TIDAL_URL_RE.test(query.trim());

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setArtistResult(null);

    try {
      if (isUrl) {
        const r = await resolve.url(query.trim());
        if (r.artist) {
          setArtistResult({ artist: r.artist, top_tracks: r.top_tracks, albums: r.albums });
          setResults({ tracks: [], albums: [], playlists: [] });
        } else {
          setResults({ tracks: r.tracks, albums: r.albums, playlists: r.playlists });
        }
      } else {
        const r = await search.query(query, searchType);
        setResults(r);
      }
    } catch (err) {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `resolve-err-${Date.now()}`,
          type: 'error',
          title: isUrl ? 'Could not resolve this link' : 'Search failed',
          detail: String(err),
          dismissAt: Date.now() + 5000,
        },
      });
    } finally {
      setLoading(false);
    }
  };

  const handleAddToQueue = async (
    tidal_id: string | number,
    item_type: string,
    title: string,
    artist: string = '',
    album: string = '',
  ) => {
    try {
      await queue.add({
        tidal_id: String(tidal_id),
        item_type,
        title,
        artist,
        album,
        quality: state.settings.default_quality,
        format: state.settings.default_format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-${Date.now()}-${tidal_id}`,
          type: 'info',
          title: 'Added to queue',
          detail: title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to add to queue',
          detail: title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const typeButtons: { key: typeof searchType; label: string; icon: string }[] = [
    { key: 'track', label: 'Tracks', icon: '♪' },
    { key: 'album', label: 'Albums', icon: '▦' },
    { key: 'playlist', label: 'Playlists', icon: '☰' },
  ];

  const qualityBadgeColor = (q: string) => {
    if (q.includes('hi_res') || q.includes('HI_RES')) return { bg: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' };
    if (q.includes('lossless') || q.includes('LOSSLESS')) return { bg: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' };
    if (q.includes('320')) return { bg: 'rgba(255, 192, 64, 0.1)', color: 'var(--warning)' };
    return { bg: 'var(--bg-surface)', color: 'var(--text-dim)' };
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      {/* Search Hero */}
      <div className="mb-10 text-center">
        <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
          <div
            className="flex items-center gap-1 p-1.5"
            style={{
              background: 'var(--bg-deep)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius)',
              boxShadow: loading ? '0 0 24px rgba(0, 184, 212, 0.1)' : 'none',
              transition: 'box-shadow 0.3s',
            }}
          >
            <div className="pl-3 flex items-center">
              {isUrl ? (
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="var(--accent-primary)" strokeWidth="1.5">
                  <path d="M7 11L3 15" />
                  <path d="M11 7L15 3" />
                  <path d="M5 13L13 5" />
                  <circle cx="4" cy="14" r="2" />
                  <circle cx="14" cy="4" r="2" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="var(--text-dim)" strokeWidth="1.5">
                  <circle cx="7.5" cy="7.5" r="5.5"/>
                  <path d="M12 12l4 4"/>
                </svg>
              )}
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setArtistResult(null); }}
              placeholder="Search or paste a Tidal link..."
              className="flex-1 bg-transparent border-none outline-none px-3 py-2.5 text-sm"
              style={{ color: 'var(--text-bright)' }}
            />
            <button
              type="submit"
              disabled={loading}
              className="btn-primary text-sm px-5 py-2 shrink-0"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  {isUrl ? 'Resolving' : 'Searching'}
                </span>
              ) : (
                isUrl ? 'Resolve' : 'Search'
              )}
            </button>
          </div>

          {!isUrl && (
            <div className="flex items-center justify-center gap-1 mt-4">
              {typeButtons.map((btn) => (
                <button
                  key={btn.key}
                  type="button"
                  onClick={() => setSearchType(btn.key)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-all duration-200"
                  style={{
                    color: searchType === btn.key ? 'var(--accent-primary)' : 'var(--text-dim)',
                    background: searchType === btn.key ? 'var(--accent-dim)' : 'transparent',
                  }}
                >
                  <span className="text-xs">{btn.icon}</span>
                  {btn.label}
                </button>
              ))}
            </div>
          )}

          {isUrl && (
            <p className="text-xs mt-3" style={{ color: 'var(--accent-primary)' }}>
              Tidal link detected — will resolve directly
            </p>
          )}
        </form>
      </div>

      {/* Artist view */}
      {artistResult && (
        <ArtistView
          artist={artistResult.artist}
          topTracks={artistResult.top_tracks}
          albums={artistResult.albums}
        />
      )}

      {/* Results (non-artist) */}
      {results && !artistResult && (
        <div className="space-y-2">
          {results.tracks.map((track, i) => {
            const qbc = qualityBadgeColor(track.quality);
            return (
              <div
                key={track.id}
                className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {track.cover_url ? (
                    <img
                      src={track.cover_url}
                      alt=""
                      className="w-10 h-10 rounded-md object-cover shrink-0"
                      style={{ border: '1px solid var(--glass-border)' }}
                    />
                  ) : (
                    <div
                      className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                    >
                      ♪
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {track.title}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {track.artist} · {track.album} · {formatDuration(track.duration)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-3">
                  <span
                    className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0"
                    style={{ background: qbc.bg, color: qbc.color }}
                  >
                    {track.quality}
                  </span>
                  <button
                    onClick={() => handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)}
                    className="btn-primary text-xs px-3 py-1.5 shrink-0"
                  >
                    ↓ Download
                  </button>
                </div>
              </div>
            );
          })}

          {results.albums.map((album, i) => (
            <div
              key={album.id}
              className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
              style={{ animationDelay: `${results.tracks.length + i * 30}ms` }}
            >
              <div className="flex items-center gap-4 flex-1 min-w-0">
                {album.cover_url ? (
                  <img
                    src={album.cover_url}
                    alt=""
                    className="w-10 h-10 rounded-md object-cover shrink-0"
                    style={{ border: '1px solid var(--glass-border)' }}
                  />
                ) : (
                  <div
                    className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                  >
                    ▦
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                    {album.name}
                  </p>
                  <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleAddToQueue(album.id, 'album', album.name, album.artist)}
                className="btn-primary text-xs px-3 py-1.5 shrink-0 ml-3"
              >
                ↓ Download
              </button>
            </div>
          ))}

          {results.playlists.map((pl, i) => (
            <div
              key={pl.id}
              className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
              style={{ animationDelay: `${results.tracks.length + results.albums.length + i * 30}ms` }}
            >
              <div className="flex items-center gap-4 flex-1 min-w-0">
                {pl.cover_url ? (
                  <img
                    src={pl.cover_url}
                    alt=""
                    className="w-10 h-10 rounded-md object-cover shrink-0"
                    style={{ border: '1px solid var(--glass-border)' }}
                  />
                ) : (
                  <div
                    className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                  >
                    ☰
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                    {pl.name}
                  </p>
                  <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {pl.creator || 'Unknown'} · {pl.num_tracks} tracks
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleAddToQueue(pl.id, 'playlist', pl.name)}
                className="btn-primary text-xs px-3 py-1.5 shrink-0 ml-3"
              >
                ↓ Download
              </button>
            </div>
          ))}

          {results.tracks.length === 0 && results.albums.length === 0 && results.playlists.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm" style={{ color: 'var(--text-dim)' }}>No results found</p>
            </div>
          )}
        </div>
      )}

      {!results && !artistResult && (
        <div className="text-center py-24">
          <div
            className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'var(--bg-mid)', border: '1px solid var(--glass-border)' }}
          >
            <svg width="28" height="28" viewBox="0 0 18 18" fill="none" stroke="var(--text-dim)" strokeWidth="1.5">
              <circle cx="7.5" cy="7.5" r="5.5"/>
              <path d="M12 12l4 4"/>
            </svg>
          </div>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Search or paste a Tidal link to get started
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/components/SearchView.tsx
git commit -m "feat: add URL detection and resolve integration to SearchView"
```

---

### Task 6: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_search.py -v`

Expected: All tests PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx vite build`

Expected: Build succeeds with no errors
