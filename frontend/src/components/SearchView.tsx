import { useEffect, useRef, useState, type FormEvent } from 'react';
import { queue, resolve, search } from '../api';
import type { AlbumResult, SearchFilters, SearchResult, SearchType, TrackResult } from '../api';
import { useApp } from '../context/AppContext';
import AlbumCard from './AlbumCard';
import AlbumView from './AlbumView';
import ArtistView from './ArtistView';
import TrackRow from './TrackRow';

const TIDAL_URL_RE = /^(https?:\/\/)?(www\.|listen\.)?tidal\.com(?:\/|$)/i;
const PAGE_SIZE = 50;

function messageFromError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

const EMPTY_FILTERS: SearchFilters = {};
const GENRES = [
  'House', 'Deep House', 'Techno', 'Trance', 'Drum & Bass',
  'Dubstep', 'Electro', 'Hardstyle', 'Hip-Hop', 'R&B',
  'Reggaeton', 'Latin', 'Pop', 'Rock', 'Afro House', 'Amapiano',
];
const CAMELOT_KEYS = [
  '1A', '2A', '3A', '4A', '5A', '6A', '7A', '8A', '9A', '10A', '11A', '12A',
  '1B', '2B', '3B', '4B', '5B', '6B', '7B', '8B', '9B', '10B', '11B', '12B',
];

function buildApiFilters(filters: SearchFilters, offset = 0, refresh = false): SearchFilters {
  return { ...filters, offset, limit: PAGE_SIZE, ...(refresh ? { refresh: true } : {}) };
}

function hasFilters(filters: SearchFilters) {
  return Object.values(filters).some((value) => value !== undefined && value !== '' && value !== false);
}

function resultCount(results: SearchResult, type: SearchType) {
  switch (type) {
    case 'track': return results.tracks.length;
    case 'artist': return results.artists.length;
    case 'album': return results.albums.length;
    case 'playlist': return results.playlists.length;
  }
}

function resolveToSearchResult(resolved: { tracks: TrackResult[]; albums: AlbumResult[]; playlists: SearchResult['playlists'] }): SearchResult {
  return {
    tracks: resolved.tracks,
    artists: [],
    albums: resolved.albums,
    playlists: resolved.playlists,
    offset: 0,
    limit: PAGE_SIZE,
    has_more: false,
  };
}

function Cover({ src, alt, kind = 'track' }: { src: string | null; alt: string; kind?: 'track' | 'artist' | 'album' | 'playlist' }) {
  if (src) return <img src={src} alt={alt} className="w-12 h-12 rounded-md object-cover shrink-0" />;
  return (
    <div className="w-12 h-12 rounded-md shrink-0 flex items-center justify-center text-sm" style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }} aria-hidden="true">
      {kind === 'track' ? '♪' : kind === 'artist' ? '◎' : kind === 'album' ? '▣' : '☷'}
    </div>
  );
}

function SkeletonResults() {
  return (
    <div className="space-y-2" aria-label="Loading results" aria-busy="true">
      {[1, 2, 3, 4].map((item) => (
        <div key={item} className="glass p-4 flex items-center gap-4 animate-pulse">
          <div className="w-12 h-12 rounded-md shrink-0" style={{ background: 'var(--bg-surface)' }} />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-2/5 rounded" style={{ background: 'var(--bg-surface)' }} />
            <div className="h-2 w-3/5 rounded" style={{ background: 'var(--bg-surface)' }} />
            <div className="h-2 w-1/4 rounded" style={{ background: 'var(--bg-surface)' }} />
          </div>
          <div className="h-8 w-20 rounded" style={{ background: 'var(--bg-surface)' }} />
        </div>
      ))}
    </div>
  );
}

function SkeletonDetail({ label }: { label: string }) {
  return (
    <div className="space-y-4" role="status" aria-label={label} aria-busy="true">
      <div className="glass p-5 sm:p-6 flex items-center gap-5 animate-pulse">
        <div className="w-24 h-24 rounded-md shrink-0" style={{ background: 'var(--bg-surface)' }} />
        <div className="flex-1 space-y-3">
          <div className="h-3 w-20 rounded" style={{ background: 'var(--bg-surface)' }} />
          <div className="h-6 w-2/5 rounded" style={{ background: 'var(--bg-surface)' }} />
          <div className="h-3 w-1/3 rounded" style={{ background: 'var(--bg-surface)' }} />
        </div>
      </div>
      <div className="glass p-5 animate-pulse">
        <div className="h-4 w-32 rounded mb-4" style={{ background: 'var(--bg-surface)' }} />
        <div className="space-y-2">{[1, 2, 3].map((item) => <div key={item} className="h-16 rounded" style={{ background: 'var(--bg-surface)' }} />)}</div>
      </div>
    </div>
  );
}

export default function SearchView() {
  const { state, dispatch } = useApp();
  const session = state.search;
  const { query, type: searchType, filters, results, detail } = session;
  const [refineOpen, setRefineOpen] = useState(false);
  const requestController = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const detailActionRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => () => {
    generation.current += 1;
    requestController.current?.abort();
  }, []);

  useEffect(() => {
    if (detail?.status === 'error') detailActionRef.current?.focus();
  }, [detail?.kind, detail?.id, detail?.status]);

  const beginRequest = () => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    generation.current += 1;
    return { controller, requestId: generation.current };
  };

  const isCurrentRequest = (requestId: number, controller: AbortController) => (
    generation.current === requestId && !controller.signal.aborted
  );

  const notifyError = (title: string, detail: string) => {
    dispatch({ type: 'ADD_TOAST', payload: { id: `search-err-${Date.now()}`, type: 'error', title, detail, dismissAt: Date.now() + 5000 } });
  };

  const closeDetail = () => {
    dispatch({ type: 'CLOSE_DETAIL' });
    window.setTimeout(() => searchInputRef.current?.focus(), 0);
  };

  const openArtist = async (artistId: number) => {
    const { controller, requestId } = beginRequest();
    dispatch({ type: 'DETAIL_STARTED', payload: { kind: 'artist', id: artistId } });
    try {
      const details = await search.artist(artistId, controller.signal);
      if (isCurrentRequest(requestId, controller)) {
        dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'artist', id: artistId, data: details } });
      }
    } catch (error) {
      if (!isCurrentRequest(requestId, controller)) return;
      const message = messageFromError(error);
      dispatch({ type: 'DETAIL_FAILED', payload: { kind: 'artist', id: artistId, error: message } });
      notifyError('Artist lookup failed', message);
    }
  };

  const openAlbum = async (albumId: number) => {
    const { controller, requestId } = beginRequest();
    dispatch({ type: 'DETAIL_STARTED', payload: { kind: 'album', id: albumId } });
    try {
      const details = await search.albumTracks(albumId, controller.signal);
      if (isCurrentRequest(requestId, controller)) {
        dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'album', id: albumId, data: details } });
      }
    } catch (error) {
      if (!isCurrentRequest(requestId, controller)) return;
      const message = messageFromError(error);
      dispatch({ type: 'DETAIL_FAILED', payload: { kind: 'album', id: albumId, error: message } });
      notifyError('Album lookup failed', message);
    }
  };

  const runSearch = async (searchQuery: string, type: SearchType, appliedFilters: SearchFilters, refresh = false) => {
    const urlSearch = TIDAL_URL_RE.test(searchQuery);
    const { controller, requestId } = beginRequest();
    dispatch({ type: 'SEARCH_STARTED', payload: { query: searchQuery, type, filters: appliedFilters } });

    try {
      if (urlSearch) {
        const resolved = await resolve.url(searchQuery, controller.signal);
        if (!isCurrentRequest(requestId, controller)) return;
        if (resolved.artist) {
          dispatch({ type: 'DETAIL_STARTED', payload: { kind: 'artist', id: resolved.artist.id } });
          dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'artist', id: resolved.artist.id, data: resolved } });
        } else if (resolved.albums[0]) {
          const albumId = resolved.albums[0].id;
          dispatch({ type: 'DETAIL_STARTED', payload: { kind: 'album', id: albumId } });
          const details = await search.albumTracks(albumId, controller.signal);
          if (!isCurrentRequest(requestId, controller)) return;
          dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'album', id: albumId, data: details } });
        } else {
          dispatch({ type: 'SEARCH_SUCCEEDED', payload: resolveToSearchResult(resolved) });
        }
        return;
      }

      const response = await search.query(searchQuery, type, buildApiFilters(appliedFilters, 0, refresh), controller.signal);
      if (!isCurrentRequest(requestId, controller)) return;
      dispatch({ type: 'SEARCH_SUCCEEDED', payload: response });
    } catch (err) {
      if (!isCurrentRequest(requestId, controller)) return;
      const message = messageFromError(err);
      dispatch({ type: 'SEARCH_FAILED', payload: message });
      notifyError(urlSearch ? 'Could not resolve this link' : 'Search failed', message);
    }
  };

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery && !filters.genre) return;
    void runSearch(trimmedQuery, searchType, filters);
  };

  const clearSearch = () => {
    requestController.current?.abort();
    generation.current += 1;
    dispatch({ type: 'CLEAR_SEARCH' });
  };

  const clearFilters = () => {
    dispatch({ type: 'SET_SEARCH_FILTERS', payload: EMPTY_FILTERS });
    if (query.trim()) void runSearch(query.trim(), searchType, EMPTY_FILTERS);
    else dispatch({ type: 'CLEAR_SEARCH' });
  };

  const removeFilter = (filter: keyof SearchFilters) => {
    const nextFilters = { ...filters };
    delete nextFilters[filter];
    if (filter === 'key') delete nextFilters.keyCompatible;
    dispatch({ type: 'SET_SEARCH_FILTERS', payload: nextFilters });
  };

  const handleTypeChange = (nextType: SearchType) => {
    dispatch({ type: 'SET_SEARCH_TYPE', payload: nextType });
    dispatch({ type: 'CLOSE_DETAIL' });
    if (nextType !== 'track') {
      dispatch({ type: 'SET_SEARCH_FILTERS', payload: EMPTY_FILTERS });
      setRefineOpen(false);
    }
  };

  const handleLoadMore = async () => {
    if (!results || (!query.trim() && !filters.genre)) return;
    const offset = resultCount(results, searchType);
    const { controller, requestId } = beginRequest();
    dispatch({ type: 'SEARCH_MORE_STARTED' });
    try {
      const response = await search.query(query.trim(), searchType, buildApiFilters(filters, offset), controller.signal);
      if (isCurrentRequest(requestId, controller)) {
        dispatch({ type: 'SEARCH_MORE_SUCCEEDED', payload: { type: searchType, result: response } });
      }
    } catch (err) {
      if (!isCurrentRequest(requestId, controller)) return;
      const message = messageFromError(err);
      dispatch({ type: 'SEARCH_MORE_FAILED', payload: message });
      notifyError('Failed to load more', message);
    }
  };

  const handleAddToQueue = async (tidalId: string | number, itemType: string, title: string, artist = '', album = '') => {
    try {
      const added = await queue.add({ tidal_id: String(tidalId), item_type: itemType, title, artist, album, quality: state.settings.default_quality, format: state.settings.default_format });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-${Date.now()}-${tidalId}`, type: 'info', title: 'Added to queue', detail: title, dismissAt: Date.now() + 3000 } });
    } catch {
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-err-${Date.now()}`, type: 'error', title: 'Failed to add to queue', detail: title, dismissAt: Date.now() + 4000 } });
    }
  };

  const previewTrack = (track: TrackResult) => dispatch({ type: 'SET_PREVIEW', payload: { id: track.id, title: track.title, artist: track.artist, cover_url: track.cover_url, key: null, camelot: null } });

  const isUrl = TIDAL_URL_RE.test(query.trim());
  const loading = session.status === 'loading';
  const error = session.error;
  const partialError = session.partialError;
  const loadingMore = session.loadingMore;
  const hasActiveFilters = searchType === 'track' && hasFilters(filters);
  const typeButtons: { key: SearchType; label: string }[] = [
    { key: 'track', label: 'Tracks' },
    { key: 'artist', label: 'Artists' },
    { key: 'album', label: 'Albums' },
    { key: 'playlist', label: 'Playlists' },
  ];
  const activeChips = [
    filters.bpmMin !== undefined ? { key: 'bpmMin' as const, label: `Min ${filters.bpmMin} BPM` } : null,
    filters.bpmMax !== undefined ? { key: 'bpmMax' as const, label: `Max ${filters.bpmMax} BPM` } : null,
    filters.key ? { key: 'key' as const, label: `Key ${filters.key}` } : null,
    filters.keyCompatible ? { key: 'keyCompatible' as const, label: 'Compatible keys' } : null,
    filters.genre ? { key: 'genre' as const, label: filters.genre } : null,
  ].filter(Boolean) as { key: keyof SearchFilters; label: string }[];
  const totalResults = results
    ? results.tracks.length + results.artists.length + results.albums.length + results.playlists.length
    : 0;
  const canLoadMore = Boolean(results && resultCount(results, searchType) > 0 && results.has_more);

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 animate-fade-in">
      <div className="mb-8">
        <form onSubmit={handleSearch} aria-label="Search Tidal catalog">
          <label htmlFor="catalog-search" className="sr-only">Search tracks, artists, albums, or paste a Tidal link</label>
          <div className="flex items-center gap-1 p-1.5" style={{ background: 'var(--bg-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius)' }}>
            <div className="pl-3 flex items-center" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke={isUrl ? 'var(--accent-primary)' : 'var(--text-dim)'} strokeWidth="1.5">
                {isUrl ? <><path d="M7 11L3 15M11 7L15 3M5 13L13 5" /><circle cx="4" cy="14" r="2" /><circle cx="14" cy="4" r="2" /></> : <><circle cx="7.5" cy="7.5" r="5.5" /><path d="M12 12l4 4" /></>}
              </svg>
            </div>
            <input ref={searchInputRef} id="catalog-search" type="text" value={query} onChange={(event) => { if (detail) dispatch({ type: 'CLOSE_DETAIL' }); dispatch({ type: 'SET_SEARCH_QUERY', payload: event.target.value }); }} placeholder="Search tracks, artists, albums, or paste a Tidal link" className="input-abyss flex-1 border-none outline-none px-3 py-2.5 text-sm" />
            {query && <button type="button" className="btn-ghost text-lg px-2 py-1" aria-label="Clear search" onClick={clearSearch}>×</button>}
            <button type="submit" className="btn-primary text-sm px-5 py-2 shrink-0">{isUrl ? (loading ? 'Resolving…' : 'Resolve') : 'Search'}</button>
          </div>
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>Search by title or artist. Use <span className="mono">track - artist</span> for an exact pairing.</p>
          {isUrl && <p className="text-xs mt-2" style={{ color: 'var(--accent-primary)' }} role="status">Tidal link detected. It will resolve directly.</p>}
        </form>

        {!isUrl && (
          <div className="flex flex-wrap items-center gap-2 mt-5">
            <div className="flex items-center gap-1" role="group" aria-label="Search result type">
              {typeButtons.map((button) => <button key={button.key} type="button" aria-pressed={searchType === button.key} onClick={() => handleTypeChange(button.key)} className="btn-ghost text-sm px-3 py-1.5" style={searchType === button.key ? { color: 'var(--accent-primary)', background: 'var(--accent-dim)', borderColor: 'rgba(0, 229, 199, 0.3)' } : undefined}>{button.label}</button>)}
            </div>
            {searchType === 'track' && <button type="button" className="btn-ghost text-sm px-3 py-1.5" aria-expanded={refineOpen} aria-controls="search-refine" onClick={() => setRefineOpen((open) => !open)}>Refine{hasActiveFilters ? ` (${activeChips.length})` : ''}</button>}
          </div>
        )}

        {hasActiveFilters && (
          <div className="flex flex-wrap items-center gap-2 mt-4" aria-label="Active filters">
            {activeChips.map((chip) => <button key={chip.key} type="button" className="btn-ghost text-xs px-2.5 py-1" aria-label={`Remove ${chip.label} filter`} onClick={() => removeFilter(chip.key)}>{chip.label} <span aria-hidden="true">×</span></button>)}
            <button type="button" className="btn-ghost text-xs px-2.5 py-1" onClick={clearFilters}>Clear filters</button>
          </div>
        )}

        {!isUrl && searchType === 'track' && refineOpen && (
          <div id="search-refine" className="dj-filter-bar mt-4" role="region" aria-label="DJ filters">
            <div className="filter-group"><label htmlFor="bpm-min">BPM</label><input id="bpm-min" type="number" min={60} max={200} placeholder="Min" value={filters.bpmMin ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, bpmMin: event.target.value ? Number(event.target.value) : undefined } })} aria-label="Minimum BPM" /><span aria-hidden="true" style={{ color: 'var(--text-dim)' }}>–</span><input id="bpm-max" type="number" min={60} max={200} placeholder="Max" value={filters.bpmMax ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, bpmMax: event.target.value ? Number(event.target.value) : undefined } })} aria-label="Maximum BPM" /></div>
            <div className="filter-group"><label htmlFor="camelot-key">Key</label><select id="camelot-key" value={filters.key ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, key: event.target.value || undefined } })} aria-label="Camelot key"><option value="">Any key</option>{CAMELOT_KEYS.map((key) => <option key={key} value={key}>{key}</option>)}</select></div>
            {filters.key && <label className="filter-toggle toggle-label"><input type="checkbox" checked={filters.keyCompatible ?? false} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, keyCompatible: event.target.checked || undefined } })} /><span>Compatible keys</span></label>}
            <div className="filter-group"><label htmlFor="genre">Genre</label><select id="genre" value={filters.genre ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, genre: event.target.value || undefined } })} aria-label="Genre"><option value="">Any genre</option>{GENRES.map((genre) => <option key={genre} value={genre}>{genre}</option>)}</select></div>
          </div>
        )}
      </div>

      {detail?.kind === 'album' && (
        <AlbumView
          detail={detail}
          onBack={closeDetail}
          onRetry={() => void openAlbum(detail.id)}
          onOpenArtist={openArtist}
          onOpenAlbum={openAlbum}
        />
      )}

      {detail?.kind === 'artist' && detail.status === 'loading' && <SkeletonDetail label="Loading artist details" />}

      {detail?.kind === 'artist' && detail.status === 'error' && (
        <div className="glass p-8 text-center" role="alert">
          <p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>We couldn’t load this artist.</p>
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{detail.error}</p>
          <div className="flex items-center justify-center gap-2 mt-5">
            <button ref={detailActionRef} type="button" className="btn-primary text-sm" onClick={() => void openArtist(detail.id)}>Retry</button>
            <button type="button" className="btn-ghost text-sm px-3 py-1.5" onClick={closeDetail}>← Back to search</button>
          </div>
        </div>
      )}

      {detail?.kind === 'artist' && detail.status === 'success' && detail.data?.artist && (
        <ArtistView
          artist={detail.data.artist}
          topTracks={detail.data.top_tracks}
          tracks={detail.data.tracks}
          albums={detail.data.albums}
          errors={detail.data.errors}
          onBack={closeDetail}
        />
      )}

      {!detail && loading && <SkeletonResults />}

      {!detail && !loading && error && (
        <div className="glass p-8 text-center" role="alert"><p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>We couldn’t complete that search.</p><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{error}</p><button type="button" className="btn-primary text-sm mt-5" onClick={() => void runSearch(query.trim(), searchType, filters, true)}>Retry</button></div>
      )}

      {!detail && !loading && !error && results && (
        <div className="space-y-2" aria-live="polite">
          {totalResults > 0 && <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>{totalResults} result{totalResults === 1 ? '' : 's'}</p>}
          {results.artists.map((artist, index) => <button key={artist.id} type="button" className="glass glass-hover p-3 sm:p-4 w-full text-left flex items-center gap-3 sm:gap-4" style={{ animationDelay: `${index * 30}ms` }} onClick={() => void openArtist(artist.id)} aria-label={`Open artist ${artist.name}`}><Cover src={artist.image_url} alt={`${artist.name} portrait`} kind="artist" /><span className="min-w-0 flex-1"><span className="block text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{artist.name}</span><span className="block text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Artist</span></span><span className="btn-ghost text-xs px-3 py-1.5 shrink-0">Open</span></button>)}
          {results.tracks.map((track) => <TrackRow key={track.id} track={track} isPreviewing={state.previewTrack?.id === track.id && state.previewPlaying} onPreview={() => previewTrack(track)} onDownload={() => void handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)} onOpenArtist={track.artist_id !== null ? openArtist : undefined} onOpenAlbum={track.album_id !== null ? openAlbum : undefined} />)}
          {results.albums.map((album) => <AlbumCard key={album.id} album={album} variant="compact" onOpen={(item) => void openAlbum(item.id)} onDownload={(item) => void handleAddToQueue(item.id, 'album', item.name, item.artist)} />)}
          {results.playlists.map((playlist, index) => <div key={playlist.id} className="glass glass-hover p-3 sm:p-4 flex items-center gap-3 sm:gap-4" style={{ animationDelay: `${results.artists.length + results.tracks.length + results.albums.length + index * 30}ms` }}><Cover src={playlist.cover_url} alt={`${playlist.name} cover`} kind="playlist" /><div className="min-w-0 flex-1"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{playlist.name}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{playlist.creator || 'Unknown creator'} · {playlist.num_tracks} tracks</p></div><button type="button" onClick={() => void handleAddToQueue(playlist.id, 'playlist', playlist.name)} className="btn-primary text-xs px-3 py-1.5 shrink-0" aria-label={`Download playlist ${playlist.name}`}>Download</button></div>)}
          {totalResults === 0 && <div className="glass p-8 text-center"><p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>{hasActiveFilters ? 'No results match these filters.' : 'No results found.'}</p><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{hasActiveFilters ? 'Clear a filter or try a broader search.' : 'Try another title, artist, or Tidal link.'}</p>{hasActiveFilters && <button type="button" className="btn-primary text-sm mt-5" onClick={clearFilters}>Clear filters</button>}</div>}
          {partialError && <div className="glass p-4 mt-4" role="status"><p className="text-sm" style={{ color: 'var(--text-bright)' }}>Some results are shown, but more could not be loaded.</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{partialError}</p><button type="button" className="btn-ghost text-xs mt-2 px-2 py-1" onClick={() => void handleLoadMore()}>Retry Load more</button></div>}
          {canLoadMore && !partialError && <div className="text-center py-6"><button type="button" onClick={() => void handleLoadMore()} disabled={loadingMore} className="btn-primary text-sm px-8 py-3">{loadingMore ? 'Loading…' : 'Load more results'}</button></div>}
        </div>
      )}

      {!detail && !loading && !error && !results && <div className="text-center py-20"><div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center" style={{ background: 'var(--bg-mid)', border: '1px solid var(--glass-border)' }} aria-hidden="true"><svg width="26" height="26" viewBox="0 0 18 18" fill="none" stroke="var(--text-dim)" strokeWidth="1.5"><circle cx="7.5" cy="7.5" r="5.5" /><path d="M12 12l4 4" /></svg></div><p className="text-sm" style={{ color: 'var(--text-dim)' }}>Search the catalog or paste a Tidal link to begin.</p><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>Genre-only searches are available under Refine.</p></div>}
    </div>
  );
}
