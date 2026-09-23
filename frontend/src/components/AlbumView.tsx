import { queue } from '../api';
import type { CatalogDetail } from '../context/AppContext';
import type { TrackResult } from '../api';
import { useApp } from '../context/AppContext';
import TrackRow from './TrackRow';

type AlbumDetailState = Extract<CatalogDetail, { kind: 'album' }>;

type AlbumViewProps = {
  detail: AlbumDetailState;
  onBack?: () => void;
  onRetry: () => void;
  onOpenArtist: (artistId: number) => void;
  onOpenAlbum: (albumId: number) => void;
};

function Cover({ src, alt, large = false }: { src: string | null; alt: string; large?: boolean }) {
  if (src) return <img src={src} alt={alt} className={`album-detail-cover${large ? ' is-large' : ''}`} />;
  return <span className={`album-detail-cover album-row-cover-fallback${large ? ' is-large' : ''}`} aria-hidden="true"><svg width="22" height="22" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2.5" y="2.5" width="15" height="15" rx="2.5" /><circle cx="10" cy="10" r="3" /></svg></span>;
}

function BackButton({ onBack }: { onBack: () => void }) {
  return <button type="button" className="btn-ghost text-sm px-3 py-1.5" onClick={onBack}>← Back to search</button>;
}

export default function AlbumView({ detail, onBack, onRetry, onOpenArtist, onOpenAlbum }: AlbumViewProps) {
  const { state, dispatch } = useApp();

  const notify = (type: 'info' | 'error', title: string, detailText: string) => {
    dispatch({
      type: 'ADD_TOAST',
      payload: { id: `${type}-${Date.now()}`, type, title, detail: detailText, dismissAt: Date.now() + (type === 'error' ? 5000 : 3000) },
    });
  };

  const addToQueue = async (tidalId: number, itemType: string, title: string, artist = '', album = '') => {
    try {
      const added = await queue.add({ tidal_id: String(tidalId), item_type: itemType, title, artist, album, quality: state.settings.default_quality, format: state.settings.default_format });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      notify('info', 'Added to queue', title);
    } catch {
      notify('error', 'Failed to add to queue', title);
    }
  };

  const previewTrack = (track: TrackResult) => dispatch({ type: 'SET_PREVIEW', payload: { id: track.id, title: track.title, artist: track.artist, artist_id: track.artist_id, cover_url: track.cover_url, key: null, camelot: null } });

  if (detail.status === 'loading') {
    return (
      <div className="animate-fade-in">
        {onBack && <div className="album-detail-back"><BackButton onBack={onBack} /><span>Album details</span></div>}
        <div className="space-y-5" role="status" aria-label="Loading album details" aria-busy="true">
          <div className="glass p-5 sm:p-6 flex items-center gap-5 animate-pulse"><div className="w-28 h-28 sm:w-36 sm:h-36 rounded-md" style={{ background: 'var(--bg-surface)' }} /><div className="space-y-3 flex-1"><div className="h-3 w-1/4 rounded" style={{ background: 'var(--bg-surface)' }} /><div className="h-7 w-2/3 rounded" style={{ background: 'var(--bg-surface)' }} /><div className="h-3 w-1/2 rounded" style={{ background: 'var(--bg-surface)' }} /></div></div>
          <div className="space-y-2">{[1, 2, 3].map((item) => <div key={item} className="glass h-20 animate-pulse" style={{ background: 'var(--bg-surface)' }} />)}</div>
        </div>
      </div>
    );
  }

  if (detail.status === 'error' || !detail.data) {
    return (
      <div className="animate-fade-in">
        <div className="glass p-8 text-center" role="alert">
          <p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>We couldn’t load this album.</p>
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{detail.error || 'The album details are unavailable.'}</p>
          <div className="flex items-center justify-center gap-2 mt-5"><button type="button" className="btn-primary text-sm" onClick={onRetry}>Retry</button>{onBack && <BackButton onBack={onBack} />}</div>
        </div>
      </div>
    );
  }

  const { album, tracks } = detail.data;
  const renderTrack = (track: TrackResult) => (
    <TrackRow
      key={track.id}
      track={track}
      isPreviewing={state.previewTrack?.id === track.id && state.previewPlaying}
      onPreview={() => previewTrack(track)}
      onDownload={() => void addToQueue(track.id, 'track', track.title, track.artist, track.album)}
      onOpenArtist={onOpenArtist}
      onOpenAlbum={onOpenAlbum}
    />
  );

  return (
    <div className="animate-fade-in album-detail-view">
      {onBack && <div className="album-detail-back"><BackButton onBack={onBack} /><span>Album details</span></div>}

      <header className="album-detail-header">
        <Cover src={album.cover_url} alt={`${album.name} cover`} large />
        <div className="min-w-0 flex-1">
          <p className="workspace-eyebrow">{album.release_type || 'Album'}</p>
          <h2 className="album-detail-title" title={album.name}>{album.name}</h2>
          {album.artist_id !== null ? <button type="button" className="album-detail-artist" onClick={() => onOpenArtist(album.artist_id!)} aria-label={`Open artist ${album.artist}`}>{album.artist}</button> : <p className="album-detail-artist">{album.artist}</p>}
          <div className="album-detail-metadata mono"><span>{album.num_tracks} tracks</span>{album.release_date && <span>{album.release_date}</span>}<span>{album.quality}</span></div>
        </div>
        <button type="button" className="album-detail-download" onClick={() => void addToQueue(album.id, 'album', album.name, album.artist)} aria-label={`Download album ${album.name}`}>Download album</button>
      </header>

      <section aria-labelledby="album-tracks">
        <div className="album-track-heading"><h3 id="album-tracks">Tracks <span className="mono">{tracks.length}</span></h3></div>
        {tracks.length > 0 ? <div className="album-track-list">{tracks.map(renderTrack)}</div> : <div className="search-message"><p className="search-message-title">No tracks found for this album.</p><p className="search-message-copy">TIDAL did not return a track list for this release.</p></div>}
      </section>
    </div>
  );
}
