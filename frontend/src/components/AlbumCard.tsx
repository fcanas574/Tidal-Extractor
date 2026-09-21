import type { AlbumResult } from '../api';

function Cover({ src, alt, large }: { src: string | null; alt: string; large: boolean }) {
  const size = large ? 'w-20 h-20' : 'w-12 h-12';
  if (src) return <img src={src} alt={alt} className={`${size} rounded-md object-cover shrink-0`} />;
  return <div className={`${size} rounded-md shrink-0 flex items-center justify-center text-sm`} style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }} aria-hidden="true">▣</div>;
}

export interface AlbumCardProps {
  album: AlbumResult;
  variant?: 'compact' | 'release';
  onOpen?: (album: AlbumResult) => void;
  onDownload: (album: AlbumResult) => void;
}

export default function AlbumCard({ album, variant = 'compact', onOpen, onDownload }: AlbumCardProps) {
  const large = variant === 'release';
  const releaseType = album.release_type?.toUpperCase() || 'RELEASE';
  const paddingClass = large ? 'p-4' : 'p-3 sm:p-4';

  return (
    <article className={`glass glass-hover ${paddingClass} flex items-center gap-3 sm:gap-4`}>
      {onOpen ? (
        <button
          type="button"
          className="min-w-0 flex-1 flex items-center gap-3 sm:gap-4 text-left"
          style={{ background: 'transparent', border: 0, color: 'inherit', padding: 0 }}
          onClick={() => onOpen(album)}
          aria-label={`Open album ${album.name}`}
        >
          <Cover src={album.cover_url} alt={`${album.name} cover`} large={large} />
          <span className="min-w-0 flex-1">
            <span className={`${large ? 'text-sm font-semibold' : 'text-sm font-medium'} block truncate`} style={{ color: 'var(--text-bright)' }}>{album.name}</span>
            <span className="block text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}</span>
            <span className="flex items-center gap-2 mt-2">
              <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-dim)', color: 'var(--accent-primary)' }}>{releaseType}</span>
              <span className="mono text-[10px]" style={{ color: 'var(--text-dim)' }}>{album.quality}</span>
            </span>
          </span>
        </button>
      ) : (
        <div className="min-w-0 flex-1 flex items-center gap-3 sm:gap-4">
          <Cover src={album.cover_url} alt={`${album.name} cover`} large={large} />
          <span className="min-w-0 flex-1">
            <span className={`${large ? 'text-sm font-semibold' : 'text-sm font-medium'} block truncate`} style={{ color: 'var(--text-bright)' }}>{album.name}</span>
            <span className="block text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}</span>
            <span className="flex items-center gap-2 mt-2">
              <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-dim)', color: 'var(--accent-primary)' }}>{releaseType}</span>
              <span className="mono text-[10px]" style={{ color: 'var(--text-dim)' }}>{album.quality}</span>
            </span>
          </span>
        </div>
      )}
      <button type="button" className="btn-primary text-xs px-3 py-1.5 shrink-0" onClick={() => onDownload(album)} aria-label={`Download album ${album.name}`}>Download</button>
    </article>
  );
}
