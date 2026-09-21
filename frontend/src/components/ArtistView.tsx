import { queue } from '../api';
import type { AlbumResult, ArtistResult, ResolveResult, TrackResult } from '../api';
import { useApp } from '../context/AppContext';
import AlbumCard from './AlbumCard';
import TrackRow from './TrackRow';

function Cover({ src, alt, round = false, large = false, fallback = '♪' }: { src: string | null; alt: string; round?: boolean; large?: boolean; fallback?: string }) {
  const size = large ? 'w-20 h-20' : 'w-16 h-16';
  if (src) return <img src={src} alt={alt} className={`${size} object-cover shrink-0 ${round ? 'rounded-full' : 'rounded-md'}`} />;
  return <div className={`${size} flex items-center justify-center shrink-0 ${round ? 'rounded-full' : 'rounded-md'}`} style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }} aria-hidden="true">{fallback}</div>;
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
  onBack,
  onOpenArtist,
  onOpenAlbum,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  tracks?: TrackResult[];
  albums: AlbumResult[];
  errors?: ResolveResult['errors'];
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
    <div className="animate-fade-in">
      <div className="flex items-center justify-between gap-4 mb-4">
        {onBack ? <button type="button" className="btn-ghost text-sm px-3 py-1.5" onClick={onBack}>← Back to search</button> : <span />}
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Artist details</span>
      </div>

      <header className="glass p-5 sm:p-6 mb-7 flex items-center gap-5">
        <Cover src={artist.image_url} alt={artist.name} round />
        <div className="min-w-0"><p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Artist</p><h2 className="text-xl font-bold mt-1 truncate" style={{ color: 'var(--text-bright)' }}>{artist.name}</h2>{artist.bio && <p className="text-xs mt-2 line-clamp-3" style={{ color: 'var(--text-muted)' }}>{artist.bio}</p>}</div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.08fr)_minmax(18rem,0.92fr)] gap-6 items-start">
        <section aria-labelledby="artist-top-tracks" className="min-w-0">
          <div className="flex items-center justify-between gap-3 mb-3"><div><h3 id="artist-top-tracks" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Top tracks</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>The five most popular tracks, ready for preview or download.</p></div>{visibleTopTracks.length > 0 && <button type="button" onClick={() => void handleDownloadAllTopTracks()} className="btn-primary text-xs px-3 py-1.5">Download all</button>}</div>
          {errors?.top_tracks && <SectionMessage tone="error">Top tracks could not be loaded: {errors.top_tracks}</SectionMessage>}
          {visibleTopTracks.length > 0 ? <div className="space-y-2">{visibleTopTracks.map(renderTrack)}</div> : !errors?.top_tracks && <SectionMessage>No top tracks were returned for this artist.</SectionMessage>}
        </section>

        <section aria-labelledby="artist-releases" className="min-w-0">
          <div className="mb-3"><h3 id="artist-releases" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Latest releases</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Albums, EPs, and singles — newest first.</p></div>
          {errors?.albums && <SectionMessage tone="error">Latest releases could not be loaded: {errors.albums}</SectionMessage>}
          {albums.length > 0 ? <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">{albums.map((album) => <AlbumCard key={album.id} album={album} variant="release" onOpen={onOpenAlbum ? (item) => onOpenAlbum(item.id) : undefined} onDownload={(item) => void handleAddAlbum(item)} />)}</div> : !errors?.albums && <SectionMessage>No latest releases were returned for this artist.</SectionMessage>}
        </section>
      </div>

      <section aria-labelledby="artist-all-tracks" className="mt-7">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h3 id="artist-all-tracks" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>All tracks</h3>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Every track from this artist’s albums, EPs, and singles.</p>
          </div>
          {tracks.length > 0 && <span className="mono text-[10px] px-2 py-1 rounded" style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>{tracks.length} tracks</span>}
        </div>
        {errors?.tracks && <SectionMessage tone="error">Some artist tracks could not be loaded: {errors.tracks}</SectionMessage>}
        {tracks.length > 0 ? <div className="space-y-2">{tracks.map(renderTrack)}</div> : !errors?.tracks && <SectionMessage>No artist tracks were returned.</SectionMessage>}
      </section>
    </div>
  );
}
