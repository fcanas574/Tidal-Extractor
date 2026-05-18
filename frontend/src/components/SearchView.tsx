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
                      &#9834;
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
                    &#8595; Download
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
                    &#9638;
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
                &#8595; Download
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
                    &#9776;
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
                &#8595; Download
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
