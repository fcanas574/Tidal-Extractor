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

  // DJ Filter state
  const [bpmMin, setBpmMin] = useState<number | undefined>(undefined);
  const [bpmMax, setBpmMax] = useState<number | undefined>(undefined);
  const [selectedKey, setSelectedKey] = useState<string>('');
  const [keyCompatible, setKeyCompatible] = useState(false);
  const [selectedGenre, setSelectedGenre] = useState<string>('');

  // Pagination state
  const [loadedCount, setLoadedCount] = useState(50);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const GENRES = [
    'House', 'Deep House', 'Techno', 'Trance', 'Drum & Bass',
    'Dubstep', 'Electro', 'Hardstyle', 'Hip-Hop', 'R&B',
    'Reggaeton', 'Latin', 'Pop', 'Rock', 'Afro House', 'Amapiano',
  ];

  const CAMELOT_KEYS = [
    '1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A',
    '1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B',
  ];

  const isUrl = TIDAL_URL_RE.test(query.trim());

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    // Allow empty query if genre is selected
    if (!query.trim() && !selectedGenre) return;
    setLoading(true);
    setArtistResult(null);
    setLoadedCount(50);
    setHasMore(true);

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
        filters.offset = 0;
        filters.limit = 50;

        const r = await search.query(query.trim(), searchType, Object.keys(filters).length > 0 ? filters : undefined);
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

  const clearFilters = () => {
    setBpmMin(undefined);
    setBpmMax(undefined);
    setSelectedKey('');
    setKeyCompatible(false);
    setSelectedGenre('');
    setLoadedCount(50);
    setHasMore(true);
  };

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

  const hasActiveFilters = bpmMin !== undefined || bpmMax !== undefined || selectedKey || keyCompatible || selectedGenre;

  const toCamelot = (key: string | null, scale: string | null): string | null => {
    if (!key || !scale) return null;
    const pitchToNum: Record<string, number> = {
      'Ab': 1, 'GSharp': 1, 'Eb': 2, 'DSharp': 2, 'Bb': 3, 'ASharp': 3,
      'F': 4, 'C': 5, 'G': 6, 'D': 7, 'A': 8, 'E': 9, 'B': 10,
      'FSharp': 11, 'Gb': 11, 'Db': 12, 'CSharp': 12,
    };
    const num = pitchToNum[key];
    if (num === undefined) return null;
    const letter = scale.toUpperCase() === 'MINOR' ? 'A' : 'B';
    return `${num}${letter}`;
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
              placeholder="Search or paste a Tidal link... (use 'track - artist' to filter)"
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
              <div className="w-px h-5 mx-1" style={{ background: 'var(--glass-border)' }} />
              <div className="filter-group">
                <label style={{ fontSize: '11px' }}>Genre</label>
                <select
                  value={selectedGenre}
                  onChange={(e) => setSelectedGenre(e.target.value)}
                  className="px-2.5 py-1 text-xs rounded-md"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--glass-border)', color: 'var(--text-bright)' }}
                >
                  <option value="">Any Genre</option>
                  {GENRES.map((g) => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </div>
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

      {/* DJ Filter Bar */}
      {results && !artistResult && results.tracks.length > 0 && (
        <div className="dj-filter-bar">
          {/* BPM Filter */}
          <div className="filter-group">
            <label>BPM</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                placeholder="60"
                min={60}
                max={200}
                value={bpmMin ?? ''}
                onChange={(e) => setBpmMin(e.target.value ? Number(e.target.value) : undefined)}
                className="w-14 px-2 py-1 text-sm rounded-md"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--glass-border)', color: 'var(--text-bright)' }}
              />
              <span style={{ color: 'var(--text-dim)' }}>-</span>
              <input
                type="number"
                placeholder="200"
                min={60}
                max={200}
                value={bpmMax ?? ''}
                onChange={(e) => setBpmMax(e.target.value ? Number(e.target.value) : undefined)}
                className="w-14 px-2 py-1 text-sm rounded-md"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--glass-border)', color: 'var(--text-bright)' }}
              />
            </div>
          </div>

          {/* Key Filter */}
          <div className="filter-group">
            <label>Key</label>
            <select
              value={selectedKey}
              onChange={(e) => setSelectedKey(e.target.value)}
              className="px-3 py-1.5 text-sm rounded-md"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--glass-border)', color: 'var(--text-bright)' }}
            >
              <option value="">Any Key</option>
              {CAMELOT_KEYS.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </div>

          {/* Compatible Toggle */}
          {selectedKey && (
            <div className="filter-group filter-toggle">
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={keyCompatible}
                  onChange={(e) => setKeyCompatible(e.target.checked)}
                />
                <span className="toggle-icon">🎯</span>
                <span className="toggle-text">Compatible</span>
              </label>
            </div>
          )}

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button onClick={clearFilters} className="btn-clear-filters text-xs px-3 py-1.5 rounded-md">
              Clear
            </button>
          )}
        </div>
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
                    <div className="flex items-center gap-1.5 mt-1">
                      {track.bpm && (
                        <span
                          className="mono text-[10px] px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(255, 192, 64, 0.15)', color: 'var(--warning)' }}
                        >
                          {Math.round(track.bpm)} BPM
                        </span>
                      )}
                      {toCamelot(track.key, track.key_scale) && (
                        <span
                          className="mono text-[10px] px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(0, 184, 212, 0.15)', color: 'var(--info)' }}
                        >
                          {toCamelot(track.key, track.key_scale)}
                        </span>
                      )}
                    </div>
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
                    onClick={() => dispatch({
                      type: 'SET_PREVIEW',
                      payload: { id: track.id, title: track.title, artist: track.artist, cover_url: track.cover_url, key: null, camelot: null },
                    })}
                    className="text-xs px-2.5 py-1.5 rounded-md transition-all duration-200 shrink-0"
                    style={{
                      color: state.previewTrack?.id === track.id ? 'var(--accent-primary)' : 'var(--text-dim)',
                      background: state.previewTrack?.id === track.id ? 'var(--accent-dim)' : 'var(--bg-surface)',
                      border: `1px solid ${state.previewTrack?.id === track.id ? 'rgba(0, 229, 199, 0.3)' : 'var(--glass-border)'}`,
                    }}
                  >
                    {state.previewTrack?.id === track.id && state.previewPlaying ? (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <rect x="1" y="0" width="3" height="10" rx="0.5" />
                        <rect x="6" y="0" width="3" height="10" rx="0.5" />
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <polygon points="1,0 9,5 1,10" />
                      </svg>
                    )}
                  </button>
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
