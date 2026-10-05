import type { TrackResult } from '../api';
import DownloadButton, { type DownloadStatus } from './DownloadButton';

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

function Cover({ src, alt, isPreviewing, onClick }: { src: string | null; alt: string; isPreviewing: boolean; onClick: () => void }) {
  return (
    <button type="button" className="track-row-cover-button" onClick={(event) => { event.stopPropagation(); onClick(); }} aria-label={`${isPreviewing ? 'Pause' : 'Play'} ${alt.replace(/ cover$/, '')}`}>
      {src ? <img src={src} alt={alt} className="track-row-cover" loading="lazy" /> : <span className="track-row-cover track-row-cover-fallback" aria-hidden="true">
      <svg width="19" height="19" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12.8 4v9.3a2.7 2.7 0 1 1-1.6-2.5V6l5-1.2v6.8a2.7 2.7 0 1 1-1.6-2.5V3.7L12.8 4Z" />
      </svg>
      </span>}
      <span className="track-row-cover-overlay" aria-hidden="true">
        {isPreviewing ? <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="2" width="3" height="12" rx=".7" /><rect x="10" y="2" width="3" height="12" rx=".7" /></svg> : <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="m4 2.5 9 5.5-9 5.5v-11Z" /></svg>}
      </span>
    </button>
  );
}

export interface TrackRowProps {
  track: TrackResult;
  isPreviewing: boolean;
  isActive?: boolean;
  onPreview: () => void;
  onDownload: () => void;
  downloadStatus?: DownloadStatus;
  downloadProgress?: number;
  downloadError?: string | null;
  onOpenArtist?: (artistId: number) => void;
  onOpenAlbum?: (albumId: number) => void;
}

export default function TrackRow({
  track,
  isPreviewing,
  isActive = isPreviewing,
  onPreview,
  onDownload,
  downloadStatus = 'idle',
  downloadProgress = 0,
  downloadError = null,
  onOpenArtist,
  onOpenAlbum,
}: TrackRowProps) {
  const camelot = track.camelot || toCamelot(track.key, track.key_scale);
  const hasFreqBlogMetadata = track.bpm_source === 'freqblog'
    || track.key_source === 'freqblog'
    || track.genre_source === 'freqblog';
  const canOpenArtist = track.artist_id !== null && onOpenArtist;
  const canOpenAlbum = track.album_id !== null && onOpenAlbum;

  const metadata = [
    track.bpm !== null ? { value: `${Math.round(track.bpm)} BPM` } : null,
    camelot ? { value: camelot } : null,
    track.genre ? { value: track.genre } : null,
    track.quality ? { value: track.quality } : null,
    hasFreqBlogMetadata ? { value: 'FreqBlog', label: 'FreqBlog metadata' } : null,
  ].filter((value): value is { value: string; label?: string } => Boolean(value));

  return (
    <article
      className={`track-row${isActive ? ' is-active' : ''}`}
      role="article"
      aria-label={`${isPreviewing ? 'Pause' : 'Play'} ${track.title}`}
      tabIndex={0}
      onClick={() => { if (window.getSelection()?.toString()) return; onPreview(); }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onPreview(); }
      }}
    >
      <Cover src={track.cover_url} alt={`${track.title} cover`} isPreviewing={isPreviewing} onClick={onPreview} />
      <div className="track-row-copy">
        <p className="track-row-title" title={track.title}>{track.title}</p>
        <div className="track-row-context">
          {canOpenArtist ? (
            <button type="button" className="track-row-link" onClick={(event) => { event.stopPropagation(); onOpenArtist(track.artist_id!); }} aria-label={`Open artist ${track.artist}`}>
              {track.artist}
            </button>
          ) : <span className="track-row-context-name" title={track.artist}>{track.artist}</span>}
          <span aria-hidden="true">·</span>
          {canOpenAlbum ? (
            <button type="button" className="track-row-link" onClick={(event) => { event.stopPropagation(); onOpenAlbum(track.album_id!); }} aria-label={`Open album ${track.album}`}>
              {track.album}
            </button>
          ) : <span className="track-row-context-name" title={track.album}>{track.album}</span>}
          <span className="track-row-duration">{formatDuration(track.duration)}</span>
        </div>
        {metadata.length > 0 && (
          <div className="track-row-metadata mono" role="group" aria-label={`Technical details for ${track.title}`}>
            {metadata.map((value, index) => (
              <span className="track-row-metadata-item" key={`${value.value}-${index}`}>
                {index > 0 && <span aria-hidden="true" className="track-row-metadata-separator">·</span>}
                <span aria-label={value.label}>{value.value}</span>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="track-row-actions">
        <DownloadButton title={track.title} status={downloadStatus} progress={downloadProgress} error={downloadError} onDownload={onDownload} className="track-row-download" />
      </div>
    </article>
  );
}
