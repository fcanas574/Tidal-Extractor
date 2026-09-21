import type { TrackResult } from '../api';

function formatDuration(seconds: number) {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')}`;
}

function toCamelot(key: string | null, scale: string | null) {
  if (!key || !scale) return null;
  const pitchToNum: Record<string, number> = {
    Ab: 1, GSharp: 1, Eb: 2, DSharp: 2, Bb: 3, ASharp: 3,
    F: 4, C: 5, G: 6, D: 7, A: 8, E: 9, B: 10,
    FSharp: 11, Gb: 11, Db: 12, CSharp: 12,
  };
  const number = pitchToNum[key];
  return number === undefined ? null : `${number}${scale.toUpperCase() === 'MINOR' ? 'A' : 'B'}`;
}

function qualityBadgeColor(quality: string) {
  if (quality.includes('hi_res') || quality.includes('HI_RES')) return { background: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' };
  if (quality.includes('lossless') || quality.includes('LOSSLESS')) return { background: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' };
  if (quality.includes('320')) return { background: 'rgba(255, 192, 64, 0.1)', color: 'var(--warning)' };
  return { background: 'var(--bg-surface)', color: 'var(--text-dim)' };
}

function Cover({ src, alt }: { src: string | null; alt: string }) {
  if (src) return <img src={src} alt={alt} className="w-12 h-12 rounded-md object-cover shrink-0" />;
  return (
    <div className="w-12 h-12 rounded-md shrink-0 flex items-center justify-center text-sm" style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }} aria-hidden="true">
      ♪
    </div>
  );
}

export interface TrackRowProps {
  track: TrackResult;
  isPreviewing: boolean;
  onPreview: () => void;
  onDownload: () => void;
  onOpenArtist?: (artistId: number) => void;
  onOpenAlbum?: (albumId: number) => void;
}

export default function TrackRow({
  track,
  isPreviewing,
  onPreview,
  onDownload,
  onOpenArtist,
  onOpenAlbum,
}: TrackRowProps) {
  const camelot = track.camelot || toCamelot(track.key, track.key_scale);
  const hasFreqBlogMetadata = track.bpm_source === 'freqblog'
    || track.key_source === 'freqblog'
    || track.genre_source === 'freqblog';
  const canOpenArtist = track.artist_id !== null && onOpenArtist;
  const canOpenAlbum = track.album_id !== null && onOpenAlbum;

  return (
    <div className="glass glass-hover p-3 sm:p-4 flex flex-wrap sm:flex-nowrap items-center gap-3 sm:gap-4">
      <Cover src={track.cover_url} alt={`${track.title} cover`} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{track.title}</p>
        <div className="text-xs truncate mt-1 flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
          {canOpenArtist ? (
            <button type="button" className="hover:underline focus-visible:underline text-left truncate" style={{ color: 'inherit' }} onClick={() => onOpenArtist(track.artist_id!)} aria-label={`Open artist ${track.artist}`}>
              {track.artist}
            </button>
          ) : <span className="truncate">{track.artist}</span>}
          <span aria-hidden="true">·</span>
          {canOpenAlbum ? (
            <button type="button" className="hover:underline focus-visible:underline text-left truncate" style={{ color: 'inherit' }} onClick={() => onOpenAlbum(track.album_id!)} aria-label={`Open album ${track.album}`}>
              {track.album}
            </button>
          ) : <span className="truncate">{track.album}</span>}
          <span aria-hidden="true">·</span>
          <span className="shrink-0">{formatDuration(track.duration)}</span>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2 min-h-5 items-start">
          {track.bpm !== null && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255, 192, 64, 0.15)', color: 'var(--warning)' }}>{Math.round(track.bpm)} BPM</span>}
          {camelot && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(0, 184, 212, 0.15)', color: 'var(--info)' }}>{camelot}</span>}
          {track.genre && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}>{track.genre}</span>}
          {hasFreqBlogMetadata && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(176, 120, 255, 0.12)', color: 'var(--text-muted)' }} aria-label="FreqBlog metadata">FreqBlog</span>}
        </div>
      </div>
      <span className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0" style={qualityBadgeColor(track.quality)}>{track.quality}</span>
      <div className="flex items-center gap-2 ml-auto">
        <button type="button" className="btn-ghost text-xs px-2.5 py-1.5" onClick={onPreview} aria-label={`${isPreviewing ? 'Pause' : 'Preview'} ${track.title}`}>
          {isPreviewing ? 'Pause' : 'Preview'}
        </button>
        <button type="button" className="btn-primary text-xs px-3 py-1.5" onClick={onDownload} aria-label={`Download ${track.title}`}>Download</button>
      </div>
    </div>
  );
}
