import { useEffect, useRef, useState, type FormEvent } from 'react';
import { queue, resolve, search } from '../api';
import type { AlbumResult, SearchFilters, SearchResult, SearchType, TrackResult } from '../api';
import { useApp } from '../context/AppContext';
import AlbumCard from './AlbumCard';
import AlbumView from './AlbumView';
import ArtistView from './ArtistView';
import TrackRow from './TrackRow';
import WorkspaceInspector from './WorkspaceInspector';

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
    <span className="catalog-cover-fallback" aria-hidden="true">
      {kind === 'track' ? (
        <svg width="19" height="19" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M12.8 4v9.3a2.7 2.7 0 1 1-1.6-2.5V6l5-1.2v6.8a2.7 2.7 0 1 1-1.6-2.5V3.7L12.8 4Z" /></svg>
      ) : kind === 'artist' ? (
        <svg width="19" height="19" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="10" cy="7" r="3" /><path d="M4 17a6 6 0 0 1 12 0" /></svg>
      ) : (
        <svg width="19" height="19" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2.5" y="2.5" width="15" height="15" rx="2.5" /><circle cx="10" cy="10" r="3" /></svg>
      )}
    </span>
  );
}

function SkeletonResults() {
  return (
    <div className="search-skeleton-list" aria-label="Loading results" aria-busy="true">
      {[1, 2, 3, 4].map((item) => (
        <div key={item} className="search-skeleton-row animate-pulse">
          <div className="search-skeleton-cover" />
          <div className="search-skeleton-copy">
            <div className="h-3 w-2/5 rounded" style={{ background: 'var(--bg-surface)' }} />
            <div className="h-2 w-3/5 rounded" style={{ background: 'var(--bg-surface)' }} />
          </div>
          <div className="search-skeleton-action" />
        </div>
      ))}
    </div>
  );
}

function SkeletonDetail({ label }: { label: string }) {
  return (
    <div className="search-detail-skeleton" role="status" aria-label={label} aria-busy="true">
      <div className="search-detail-skeleton-header animate-pulse">
        <div className="search-detail-skeleton-cover" />
        <div className="search-skeleton-copy"><div /><div /><div /></div>
      </div>
      <div className="search-skeleton-list">
        {[1, 2, 3].map((item) => <div key={item} className="search-skeleton-row animate-pulse"><div className="search-skeleton-cover" /><div className="search-skeleton-copy"><div /><div /></div></div>)}
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
      if (!isCurrentRequest(requestId, controller)) return;
      const hasCompleteTrackData = details.tracks.length > 0;
      dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'artist', id: artistId, data: details, tracksStatus: hasCompleteTrackData ? 'success' : 'loading' } });
      if (hasCompleteTrackData) return;

      try {
        const artistTracks = await search.artistTracks(artistId, controller.signal);
        if (!isCurrentRequest(requestId, controller)) return;
        dispatch({ type: 'DETAIL_ARTIST_TRACKS_SUCCEEDED', payload: { id: artistId, data: artistTracks } });
      } catch (error) {
        if (!isCurrentRequest(requestId, controller)) return;
        const message = messageFromError(error);
        dispatch({ type: 'DETAIL_ARTIST_TRACKS_FAILED', payload: { id: artistId, error: message } });
        notifyError('Artist track lookup failed', message);
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
          dispatch({ type: 'DETAIL_SUCCEEDED', payload: { kind: 'artist', id: resolved.artist.id, data: resolved, tracksStatus: 'success' } });
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
  const inspectorLabel = detail?.kind === 'album' ? 'Album details' : 'Artist details';
  const inspectorTitle = detail?.kind === 'album'
    ? detail.data?.album.name || 'Album details'
    : detail?.kind === 'artist'
      ? detail.data?.artist?.name || 'Artist details'
      : '';

  const inspectorContent = detail?.kind === 'album' ? (
    <AlbumView
      detail={detail}
      onRetry={() => void openAlbum(detail.id)}
      onOpenArtist={openArtist}
      onOpenAlbum={openAlbum}
    />
  ) : detail?.kind === 'artist' && detail.status === 'loading' ? (
    <SkeletonDetail label="Loading artist details" />
  ) : detail?.kind === 'artist' && detail.status === 'error' ? (
    <div className="search-detail-error" role="alert">
      <p className="search-detail-error-title">We couldn’t load this artist.</p>
      <p className="search-detail-error-message">{detail.error}</p>
      <button ref={detailActionRef} type="button" className="btn-primary text-sm" onClick={() => void openArtist(detail.id)}>Retry</button>
    </div>
  ) : detail?.kind === 'artist' && detail.status === 'success' && detail.data?.artist ? (
    <ArtistView
      artist={detail.data.artist}
      topTracks={detail.data.top_tracks}
      tracks={detail.data.tracks}
      albums={detail.data.albums}
      errors={detail.data.errors}
      tracksLoading={detail.tracksStatus === 'loading'}
      onOpenArtist={openArtist}
      onOpenAlbum={openAlbum}
    />
  ) : null;

  return (
    <div className={`search-workspace animate-fade-in${detail ? ' has-inspector' : ''}${results ? ' has-results' : ''}`}>
      <header className="search-command">
        <div className="search-command-top">
          <div className="search-page-heading">
            <p className="workspace-eyebrow">Catalog</p>
            <h1 className="search-page-title">Search</h1>
          </div>
          <form className="search-form" onSubmit={handleSearch} aria-label="Search Tidal catalog" noValidate>
          <label htmlFor="catalog-search" className="sr-only">Search tracks, artists, albums, or paste a Tidal link</label>
          <div className="search-input-shell">
            <div className="search-input-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke={isUrl ? 'var(--accent-primary)' : 'var(--text-dim)'} strokeWidth="1.5">
                {isUrl ? <><path d="M7 11L3 15M11 7L15 3M5 13L13 5" /><circle cx="4" cy="14" r="2" /><circle cx="14" cy="4" r="2" /></> : <><circle cx="7.5" cy="7.5" r="5.5" /><path d="M12 12l4 4" /></>}
              </svg>
            </div>
            <input ref={searchInputRef} id="catalog-search" type="text" value={query} onChange={(event) => { if (detail) dispatch({ type: 'CLOSE_DETAIL' }); dispatch({ type: 'SET_SEARCH_QUERY', payload: event.target.value }); }} placeholder="Search tracks, artists, albums, or paste a Tidal link" className="search-input" />
            {query && <button type="button" className="search-clear" aria-label="Clear search" onClick={clearSearch}>×</button>}
            <button type="submit" className="search-submit">{isUrl ? (loading ? 'Resolving…' : 'Resolve') : 'Search'}</button>
          </div>
          {isUrl && <p className="search-url-status" role="status">Tidal link detected. It will resolve directly.</p>}
          </form>
        </div>

        {!isUrl && (
          <div className="search-command-controls">
            <div className="search-type-group" role="group" aria-label="Search result type">
              {typeButtons.map((button) => (
                <button key={button.key} type="button" className={`search-type-button${searchType === button.key ? ' is-selected' : ''}`} aria-pressed={searchType === button.key} onClick={() => handleTypeChange(button.key)}>
                  {button.label}
                </button>
              ))}
            </div>
            {searchType === 'track' && <button type="button" className="search-refine-toggle" aria-expanded={refineOpen} aria-controls="search-refine" onClick={() => setRefineOpen((open) => !open)}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true"><path d="M2.5 4h11M4.5 8h7m-5 4h3" /></svg>
              Refine{hasActiveFilters ? ` · ${activeChips.length}` : ''}
            </button>}
          </div>
        )}

        {hasActiveFilters && (
          <div className="search-active-filters" role="group" aria-label="Active filters">
            {activeChips.map((chip) => <button key={chip.key} type="button" className="search-filter-chip" aria-label={`Remove ${chip.label} filter`} onClick={() => removeFilter(chip.key)}>{chip.label} <span aria-hidden="true">×</span></button>)}
            <button type="button" className="search-clear-filters" onClick={clearFilters}>Clear filters</button>
          </div>
        )}

        {!isUrl && searchType === 'track' && refineOpen && (
          <div id="search-refine" className="dj-filter-bar search-refine-panel" role="region" aria-label="DJ filters">
            <div className="filter-group"><label htmlFor="bpm-min">BPM</label><input id="bpm-min" type="number" min={60} max={200} placeholder="Min" value={filters.bpmMin ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, bpmMin: event.target.value ? Number(event.target.value) : undefined } })} aria-label="Minimum BPM" /><span aria-hidden="true" style={{ color: 'var(--text-dim)' }}>–</span><input id="bpm-max" type="number" min={60} max={200} placeholder="Max" value={filters.bpmMax ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, bpmMax: event.target.value ? Number(event.target.value) : undefined } })} aria-label="Maximum BPM" /></div>
            <div className="filter-group"><label htmlFor="camelot-key">Key</label><select id="camelot-key" value={filters.key ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, key: event.target.value || undefined } })} aria-label="Camelot key"><option value="">Any key</option>{CAMELOT_KEYS.map((key) => <option key={key} value={key}>{key}</option>)}</select></div>
            {filters.key && <label className="filter-toggle toggle-label"><input type="checkbox" checked={filters.keyCompatible ?? false} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, keyCompatible: event.target.checked || undefined } })} /><span>Compatible keys</span></label>}
            <div className="filter-group"><label htmlFor="genre">Genre</label><select id="genre" value={filters.genre ?? ''} onChange={(event) => dispatch({ type: 'SET_SEARCH_FILTERS', payload: { ...filters, genre: event.target.value || undefined } })} aria-label="Genre"><option value="">Any genre</option>{GENRES.map((genre) => <option key={genre} value={genre}>{genre}</option>)}</select></div>
          </div>
        )}
      </header>

      <div className={`search-workspace-body${detail ? ' has-inspector' : ''}${results ? ' has-results' : ''}`}>
        <section className="search-results-column" aria-label="Catalog results">
          {!detail && loading && <SkeletonResults />}

          {!detail && !loading && error && (
            <div className="search-message" role="alert">
              <p className="search-message-title">We couldn’t complete that search.</p>
              <p className="search-message-copy">{error}</p>
              <button type="button" className="btn-primary text-sm" onClick={() => void runSearch(query.trim(), searchType, filters, true)}>Retry</button>
            </div>
          )}

          {!loading && !error && results && (
            <div className="search-results-list" aria-live="polite">
              {totalResults > 0 && <div className="search-results-summary">
                <span>{totalResults} result{totalResults === 1 ? '' : 's'}</span>
                {results.metadata_pending && searchType === 'track' && <span className="search-metadata-status" role="status">Completing DJ metadata…</span>}
              </div>}
              {results.artists.map((artist) => (
                <button key={artist.id} type="button" className="catalog-result-row" onClick={() => void openArtist(artist.id)} aria-label={`Open artist ${artist.name}`}>
                  <Cover src={artist.image_url} alt={`${artist.name} portrait`} kind="artist" />
                  <span className="catalog-result-copy">
                    <span className="catalog-result-title">{artist.name}</span>
                    <span className="catalog-result-context">Artist</span>
                  </span>
                  <span className="catalog-result-open">Open</span>
                </button>
              ))}
              {results.tracks.map((track) => <TrackRow key={track.id} track={track} isPreviewing={state.previewTrack?.id === track.id && state.previewPlaying} onPreview={() => previewTrack(track)} onDownload={() => void handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)} onOpenArtist={track.artist_id !== null ? openArtist : undefined} onOpenAlbum={track.album_id !== null ? openAlbum : undefined} />)}
              {results.albums.map((album) => <AlbumCard key={album.id} album={album} variant="compact" onOpen={(item) => void openAlbum(item.id)} onDownload={(item) => void handleAddToQueue(item.id, 'album', item.name, item.artist)} />)}
              {results.playlists.map((playlist) => (
                <article key={playlist.id} className="catalog-result-row">
                  <Cover src={playlist.cover_url} alt={`${playlist.name} cover`} kind="playlist" />
                  <div className="catalog-result-copy">
                    <p className="catalog-result-title" title={playlist.name}>{playlist.name}</p>
                    <p className="catalog-result-context">{playlist.creator || 'Unknown creator'} · {playlist.num_tracks} tracks</p>
                  </div>
                  <button type="button" className="catalog-result-download" onClick={() => void handleAddToQueue(playlist.id, 'playlist', playlist.name)} aria-label={`Download playlist ${playlist.name}`}>Download</button>
                </article>
              ))}
              {totalResults === 0 && (
                <div className="search-message search-empty-state">
                  <p className="search-message-title">{hasActiveFilters ? 'No results match these filters.' : 'No results found.'}</p>
                  <p className="search-message-copy">{hasActiveFilters ? 'Clear a filter or try a broader search.' : 'Try another title, artist, or TIDAL link.'}</p>
                  {hasActiveFilters && <button type="button" className="btn-ghost text-sm" onClick={clearFilters}>Clear filters</button>}
                </div>
              )}
              {partialError && (
                <div className="search-partial-message" role="status">
                  <div><p>Some results are shown, but more could not be loaded.</p><p className="search-message-copy">{partialError}</p></div>
                  <button type="button" className="btn-ghost text-xs" onClick={() => void handleLoadMore()}>Retry Load more</button>
                </div>
              )}
              {canLoadMore && !partialError && <div className="search-load-more"><button type="button" onClick={() => void handleLoadMore()} disabled={loadingMore} className="btn-ghost text-sm px-5 py-2.5">{loadingMore ? 'Loading…' : 'Load more results'}</button></div>}
            </div>
          )}

          {!detail && !loading && !error && !results && (
            <div className="search-empty-prompt">
              <span className="search-empty-icon" aria-hidden="true"><svg width="23" height="23" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="8.5" cy="8.5" r="5.5" /><path d="m13 13 4 4" /></svg></span>
              <p>Search the catalog or paste a Tidal link to begin.</p>
              <span>Genre-only searches are available under Refine.</span>
            </div>
          )}
        </section>

        {detail && inspectorContent && (
          <WorkspaceInspector label={inspectorLabel} title={inspectorTitle} onClose={closeDetail}>
            {inspectorContent}
          </WorkspaceInspector>
        )}
      </div>
    </div>
  );
}
