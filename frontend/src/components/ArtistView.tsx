import { queue } from '../api';
import type { AlbumResult, ArtistResult, ResolveResult, TrackResult } from '../api';
import { useApp } from '../context/AppContext';
import AlbumCard from './AlbumCard';
import TrackRow from './TrackRow';

function Cover({ src, alt, round = false, large = false }: { src: string | null; alt: string; round?: boolean; large?: boolean }) {
  const className = `artist-detail-cover${large ? ' is-large' : ''}${round ? ' is-round' : ''}`;
  if (src) return <img src={src} alt={alt} className={className} loading="lazy" />;
  return <span className={`${className} artist-detail-cover-fallback`} aria-hidden="true">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></svg>
  </span>;
}

function SectionMessage({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'error' }) {
  return <div className="glass p-4 text-sm" role={tone === 'error' ? 'status' : undefined} style={{ color: tone === 'error' ? 'var(--warning)' : 'var(--text-muted)' }}>{children}</div>;
}

export default function ArtistView({
  artist,
  topTracks,
  tracks = [],
  albums,
  errors,
  tracksLoading = false,
  onBack,
  onOpenArtist,
  onOpenAlbum,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  tracks?: TrackResult[];
  albums: AlbumResult[];
  errors?: ResolveResult['errors'];
  tracksLoading?: boolean;
  onBack?: () => void;
  onOpenArtist?: (artistId: number) => void;
  onOpenAlbum?: (albumId: number) => void;
}) {
  const { state, dispatch } = useApp();
  const visibleTopTracks = topTracks.slice(0, 5);

  const handleAddToQueue = async (track: TrackResult) => {
    try {
      const added = await queue.add({ tidal_id: String(track.id), item_type: 'track', title: track.title, artist: track.artist, album: track.album, quality: state.settings.default_quality, format: state.settings.default_format });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-${Date.now()}-${track.id}`, type: 'info', title: 'Added to queue', detail: track.title, dismissAt: Date.now() + 3000 } });
    } catch {
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-err-${Date.now()}`, type: 'error', title: 'Failed to add to queue', detail: track.title, dismissAt: Date.now() + 4000 } });
    }
  };

  const handleAddAlbum = async (album: AlbumResult) => {
    try {
      const added = await queue.add({ tidal_id: String(album.id), item_type: 'album', title: album.name, artist: album.artist, quality: state.settings.default_quality, format: state.settings.default_format });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-${Date.now()}-${album.id}`, type: 'info', title: 'Added to queue', detail: album.name, dismissAt: Date.now() + 3000 } });
    } catch {
      dispatch({ type: 'ADD_TOAST', payload: { id: `add-err-${Date.now()}`, type: 'error', title: 'Failed to add to queue', detail: album.name, dismissAt: Date.now() + 4000 } });
    }
  };

  const handleDownloadAllTopTracks = async () => {
    for (const track of visibleTopTracks) await handleAddToQueue(track);
  };

  const previewTrack = (track: TrackResult) => dispatch({ type: 'SET_PREVIEW', payload: { id: track.id, title: track.title, artist: track.artist, cover_url: track.cover_url, key: null, camelot: null } });

  const renderTrack = (track: TrackResult) => (
    <TrackRow
      key={track.id}
      track={track}
      isPreviewing={state.previewTrack?.id === track.id && state.previewPlaying}
      onPreview={() => previewTrack(track)}
      onDownload={() => void handleAddToQueue(track)}
      onOpenArtist={onOpenArtist}
      onOpenAlbum={onOpenAlbum}
    />
  );

  return (
    <div className="animate-fade-in artist-detail-view">
      {onBack && <div className="album-detail-back"><button type="button" className="btn-ghost text-sm px-3 py-1.5" onClick={onBack}>← Back to search</button><span>Artist details</span></div>}

      <header className="artist-detail-header">
        <Cover src={artist.image_url} alt={artist.name} round />
        <div className="min-w-0"><p className="workspace-eyebrow">Artist</p><h2 className="artist-detail-title" title={artist.name}>{artist.name}</h2>{artist.bio && <p className="artist-detail-bio">{artist.bio}</p>}</div>
      </header>

      <div className="artist-detail-sections">
        <section aria-labelledby="artist-top-tracks" className="artist-detail-section">
          <div className="artist-detail-section-heading"><h3 id="artist-top-tracks">Top tracks</h3>{visibleTopTracks.length > 0 && <button type="button" onClick={() => void handleDownloadAllTopTracks()} className="btn-ghost text-xs px-3 py-1.5">Download top five</button>}</div>
          {errors?.top_tracks && <SectionMessage tone="error">Top tracks could not be loaded: {errors.top_tracks}</SectionMessage>}
          {visibleTopTracks.length > 0 ? <div className="artist-detail-track-list">{visibleTopTracks.map(renderTrack)}</div> : !errors?.top_tracks && <SectionMessage>No top tracks were returned for this artist.</SectionMessage>}
        </section>

        <section aria-labelledby="artist-releases" className="artist-detail-section">
          <div className="artist-detail-section-heading"><h3 id="artist-releases">Latest releases</h3></div>
          {errors?.albums && <SectionMessage tone="error">Latest releases could not be loaded: {errors.albums}</SectionMessage>}
          {albums.length > 0 ? <div className="artist-detail-release-list">{albums.map((album) => <AlbumCard key={album.id} album={album} variant="release" onOpen={onOpenAlbum ? (item) => onOpenAlbum(item.id) : undefined} onDownload={(item) => void handleAddAlbum(item)} />)}</div> : !errors?.albums && <SectionMessage>No latest releases were returned for this artist.</SectionMessage>}
        </section>
      </div>

      <section aria-labelledby="artist-all-tracks" className="artist-detail-section artist-all-tracks">
        <div className="artist-detail-section-heading">
          <h3 id="artist-all-tracks">All tracks</h3>
          {tracks.length > 0 && <span className="mono text-[10px] px-2 py-1 rounded" style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>{tracks.length} tracks</span>}
        </div>
        {errors?.tracks && <SectionMessage tone="error">Some artist tracks could not be loaded: {errors.tracks}</SectionMessage>}
        {tracksLoading ? <SectionMessage>Loading the full artist catalog…</SectionMessage> : tracks.length > 0 ? <div className="artist-detail-track-list">{tracks.map(renderTrack)}</div> : !errors?.tracks && <SectionMessage>No artist tracks were returned.</SectionMessage>}
      </section>
    </div>
  );
}
