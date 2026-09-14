import { queue } from '../api';
import { useApp } from '../context/AppContext';
import type { AlbumResult, ArtistResult, TrackResult } from '../api';

function formatDuration(seconds: number) {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')}`;
}

function toCamelot(key: string | null, scale: string | null) {
  if (!key || !scale) return null;
  const pitchToNum: Record<string, number> = { Ab: 1, GSharp: 1, Eb: 2, DSharp: 2, Bb: 3, ASharp: 3, F: 4, C: 5, G: 6, D: 7, A: 8, E: 9, B: 10, FSharp: 11, Gb: 11, Db: 12, CSharp: 12 };
  const number = pitchToNum[key];
  return number === undefined ? null : `${number}${scale.toUpperCase() === 'MINOR' ? 'A' : 'B'}`;
}

function qualityBadgeColor(quality: string) {
  if (quality.includes('hi_res') || quality.includes('HI_RES')) return { background: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' };
  if (quality.includes('lossless') || quality.includes('LOSSLESS')) return { background: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' };
  if (quality.includes('320')) return { background: 'rgba(255, 192, 64, 0.1)', color: 'var(--warning)' };
  return { background: 'var(--bg-surface)', color: 'var(--text-dim)' };
}

function Cover({ src, alt, round = false, fallback = '♪' }: { src: string | null; alt: string; round?: boolean; fallback?: string }) {
  if (src) return <img src={src} alt={alt} className={`w-16 h-16 object-cover shrink-0 ${round ? 'rounded-full' : 'rounded-md'}`} />;
  return <div className={`w-16 h-16 flex items-center justify-center shrink-0 ${round ? 'rounded-full' : 'rounded-md'}`} style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }} aria-hidden="true">{fallback}</div>;
}

export default function ArtistView({
  artist,
  topTracks,
  albums,
  onBack,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  albums: AlbumResult[];
  onBack?: () => void;
}) {
  const { state, dispatch } = useApp();

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
    for (const track of topTracks) await handleAddToQueue(track);
  };

  const previewTrack = (track: TrackResult) => dispatch({ type: 'SET_PREVIEW', payload: { id: track.id, title: track.title, artist: track.artist, cover_url: track.cover_url, key: null, camelot: null } });

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

      <section className="mb-8" aria-labelledby="artist-top-tracks">
        <div className="flex items-center justify-between gap-3 mb-3"><div><h3 id="artist-top-tracks" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Top tracks</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Popular tracks ready for preview or download.</p></div>{topTracks.length > 0 && <button type="button" onClick={() => void handleDownloadAllTopTracks()} className="btn-primary text-xs px-3 py-1.5">Download all</button>}</div>
        {topTracks.length > 0 ? <div className="space-y-2">{topTracks.map((track) => { const camelot = toCamelot(track.key, track.key_scale); return <div key={track.id} className="glass glass-hover p-3 sm:p-4 flex flex-wrap sm:flex-nowrap items-center gap-3 sm:gap-4"><Cover src={track.cover_url} alt={`${track.title} cover`} /><div className="min-w-0 flex-1"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{track.title}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{track.artist} · {track.album} · {formatDuration(track.duration)}</p><div className="flex flex-wrap gap-1.5 mt-2">{track.bpm !== null && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255, 192, 64, 0.15)', color: 'var(--warning)' }}>{Math.round(track.bpm)} BPM</span>}{camelot && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(0, 184, 212, 0.15)', color: 'var(--info)' }}>{camelot}</span>}</div></div><span className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0" style={qualityBadgeColor(track.quality)}>{track.quality}</span><div className="flex items-center gap-2 ml-auto"><button type="button" className="btn-ghost text-xs px-2.5 py-1.5" onClick={() => previewTrack(track)} aria-label={`${state.previewTrack?.id === track.id && state.previewPlaying ? 'Pause' : 'Preview'} ${track.title}`}>{state.previewTrack?.id === track.id && state.previewPlaying ? 'Pause' : 'Preview'}</button><button type="button" className="btn-primary text-xs px-3 py-1.5" onClick={() => void handleAddToQueue(track)} aria-label={`Download ${track.title}`}>Download</button></div></div>; })}</div> : <div className="glass p-5 text-sm" style={{ color: 'var(--text-muted)' }}>No top tracks were returned for this artist.</div>}
      </section>

      <section aria-labelledby="artist-albums">
        <div className="mb-3"><h3 id="artist-albums" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Albums</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Explore the artist’s releases.</p></div>
        {albums.length > 0 ? <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{albums.map((album) => <div key={album.id} className="glass glass-hover p-3 flex items-center gap-3"><Cover src={album.cover_url} alt={`${album.name} cover`} fallback="▣" /><div className="min-w-0 flex-1"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{album.name}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}</p><span className="mono text-[10px]" style={{ color: 'var(--text-dim)' }}>{album.quality}</span></div><button type="button" className="btn-primary text-xs px-3 py-1.5 shrink-0" onClick={() => void handleAddAlbum(album)} aria-label={`Download album ${album.name}`}>Download</button></div>)}</div> : <div className="glass p-5 text-sm" style={{ color: 'var(--text-muted)' }}>No albums were returned for this artist.</div>}
      </section>
    </div>
  );
}
