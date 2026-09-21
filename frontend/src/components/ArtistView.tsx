import { queue } from '../api';
import type { AlbumResult, ArtistResult, ResolveResult, TrackResult } from '../api';
import { useApp } from '../context/AppContext';

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
  albums,
  errors,
  onBack,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  albums: AlbumResult[];
  errors?: ResolveResult['errors'];
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

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.08fr)_minmax(18rem,0.92fr)] gap-6 items-start">
        <section aria-labelledby="artist-top-tracks" className="min-w-0">
          <div className="flex items-center justify-between gap-3 mb-3"><div><h3 id="artist-top-tracks" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Top tracks</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Popular tracks ready for preview or download.</p></div>{topTracks.length > 0 && <button type="button" onClick={() => void handleDownloadAllTopTracks()} className="btn-primary text-xs px-3 py-1.5">Download all</button>}</div>
          {errors?.top_tracks && <SectionMessage tone="error">Top tracks could not be loaded: {errors.top_tracks}</SectionMessage>}
          {topTracks.length > 0 ? <div className="space-y-2">{topTracks.map((track) => { const camelot = toCamelot(track.key, track.key_scale); return <div key={track.id} className="glass glass-hover p-3 sm:p-4 flex flex-wrap sm:flex-nowrap items-center gap-3 sm:gap-4"><Cover src={track.cover_url} alt={`${track.title} cover`} /><div className="min-w-0 flex-1"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{track.title}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{track.artist} · {track.album} · {formatDuration(track.duration)}</p><div className="flex flex-wrap gap-1.5 mt-2">{track.bpm !== null && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255, 192, 64, 0.15)', color: 'var(--warning)' }}>{Math.round(track.bpm)} BPM</span>}{camelot && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(0, 184, 212, 0.15)', color: 'var(--info)' }}>{camelot}</span>}</div></div><span className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0" style={qualityBadgeColor(track.quality)}>{track.quality}</span><div className="flex items-center gap-2 ml-auto"><button type="button" className="btn-ghost text-xs px-2.5 py-1.5" onClick={() => previewTrack(track)} aria-label={`${state.previewTrack?.id === track.id && state.previewPlaying ? 'Pause' : 'Preview'} ${track.title}`}>{state.previewTrack?.id === track.id && state.previewPlaying ? 'Pause' : 'Preview'}</button><button type="button" className="btn-primary text-xs px-3 py-1.5" onClick={() => void handleAddToQueue(track)} aria-label={`Download ${track.title}`}>Download</button></div></div>; })}</div> : !errors?.top_tracks && <SectionMessage>No top tracks were returned for this artist.</SectionMessage>}
        </section>

        <section aria-labelledby="artist-releases" className="min-w-0">
          <div className="mb-3"><h3 id="artist-releases" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Latest releases</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Albums, EPs, and singles — newest first.</p></div>
          {errors?.albums && <SectionMessage tone="error">Latest releases could not be loaded: {errors.albums}</SectionMessage>}
          {albums.length > 0 ? <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">{albums.map((album) => { const releaseType = album.release_type?.toUpperCase() || 'RELEASE'; return <div key={album.id} className="glass glass-hover p-4 flex items-center gap-4"><Cover src={album.cover_url} alt={`${album.name} cover`} large fallback="▣" /><div className="min-w-0 flex-1"><p className="text-sm font-semibold truncate" style={{ color: 'var(--text-bright)' }}>{album.name}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{album.artist} · {album.num_tracks} tracks</p><div className="flex items-center gap-2 mt-2"><span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-dim)', color: 'var(--accent-primary)' }}>{releaseType}</span>{album.release_date && <span className="mono text-[10px]" style={{ color: 'var(--text-dim)' }}>{album.release_date}</span>}</div></div><button type="button" className="btn-primary text-xs px-3 py-1.5 shrink-0" onClick={() => void handleAddAlbum(album)} aria-label={`Download album ${album.name}`}>Download</button></div>; })}</div> : !errors?.albums && <SectionMessage>No latest releases were returned for this artist.</SectionMessage>}
        </section>
      </div>
    </div>
  );
}
