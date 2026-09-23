import type { AlbumResult } from '../api';

function Cover({ src, alt }: { src: string | null; alt: string }) {
  if (src) return <img src={src} alt={alt} className="album-row-cover" loading="lazy" />;
  return (
    <span className="album-row-cover album-row-cover-fallback" aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4">
        <rect x="2.5" y="2.5" width="15" height="15" rx="2.5" />
        <circle cx="10" cy="10" r="3" />
        <circle cx="10" cy="10" r=".7" fill="currentColor" />
      </svg>
    </span>
  );
}

export interface AlbumCardProps {
  album: AlbumResult;
  variant?: 'compact' | 'release';
  onOpen?: (album: AlbumResult) => void;
  onDownload: (album: AlbumResult) => void;
}

export default function AlbumCard({ album, variant = 'compact', onOpen, onDownload }: AlbumCardProps) {
  const releaseType = album.release_type?.toUpperCase() || 'RELEASE';
  const identity = (
    <>
      <Cover src={album.cover_url} alt={`${album.name} cover`} />
      <span className="album-row-copy">
        <span className="album-row-title" title={album.name}>{album.name}</span>
        <span className="album-row-context" title={`${album.artist} · ${album.num_tracks} tracks${album.release_date ? ` · ${album.release_date}` : ''}`}>
          {album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}
        </span>
        <span className="album-row-metadata mono">
          <span>{releaseType}</span>
          <span>{album.quality}</span>
        </span>
      </span>
    </>
  );

  return (
    <article className={`album-row${variant === 'release' ? ' is-release' : ''}`}>
      {onOpen ? (
        <button type="button" className="album-row-identity" onClick={() => onOpen(album)} aria-label={`Open album ${album.name}`}>
          {identity}
        </button>
      ) : (
        <div className="album-row-identity">{identity}</div>
      )}
      <button type="button" className="album-row-download" onClick={() => onDownload(album)} aria-label={`Download album ${album.name}`}>
        Download
      </button>
    </article>
  );
}
