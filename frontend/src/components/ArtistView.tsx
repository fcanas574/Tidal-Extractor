import { queue } from '../api';
import { useApp } from '../context/AppContext';
import type { ArtistResult, TrackResult, AlbumResult } from '../api';

export default function ArtistView({
  artist,
  topTracks,
  albums,
}: {
  artist: ArtistResult;
  topTracks: TrackResult[];
  albums: AlbumResult[];
}) {
  const { state, dispatch } = useApp();

  const handleAddToQueue = async (
    tidal_id: string | number,
    item_type: string,
    title: string,
    artist: string = '',
    album: string = '',
  ) => {
    try {
      await queue.add({
        tidal_id: String(tidal_id),
        item_type,
        title,
        artist,
        album,
        quality: state.settings.default_quality,
        format: state.settings.default_format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-${Date.now()}-${tidal_id}`,
          type: 'info',
          title: 'Added to queue',
          detail: title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to add to queue',
          detail: title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const handleDownloadAllTopTracks = async () => {
    for (const track of topTracks) {
      await handleAddToQueue(track.id, 'track', track.title, track.artist, track.album);
    }
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const qualityBadgeColor = (q: string) => {
    if (q.includes('hi_res') || q.includes('HI_RES')) return { bg: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' };
    if (q.includes('lossless') || q.includes('LOSSLESS')) return { bg: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' };
    if (q.includes('320')) return { bg: 'rgba(255, 192, 64, 0.1)', color: 'var(--warning)' };
    return { bg: 'var(--bg-surface)', color: 'var(--text-dim)' };
  };

  return (
    <div className="animate-fade-in">
      {/* Artist header */}
      <div className="glass p-6 mb-6 flex items-center gap-5">
        {artist.image_url ? (
          <img
            src={artist.image_url}
            alt={artist.name}
            className="w-20 h-20 rounded-full object-cover shrink-0"
            style={{ border: '2px solid var(--glass-border)' }}
          />
        ) : (
          <div
            className="w-20 h-20 rounded-full shrink-0 flex items-center justify-center text-2xl"
            style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
          >
            &#9835;
          </div>
        )}
        <div className="min-w-0">
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>
            {artist.name}
          </h2>
          {artist.bio && (
            <p
              className="text-xs mt-1 line-clamp-2"
              style={{ color: 'var(--text-muted)' }}
            >
              {artist.bio}
            </p>
          )}
        </div>
      </div>

      {/* Top Tracks */}
      {topTracks.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h3
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: 'var(--text-dim)' }}
            >
              Top Tracks
            </h3>
            <button
              onClick={handleDownloadAllTopTracks}
              className="btn-primary text-xs px-3 py-1.5"
            >
              &#8595; Download All
            </button>
          </div>
          <div className="space-y-2">
            {topTracks.map((track, i) => {
              const qbc = qualityBadgeColor(track.quality);
              return (
                <div
                  key={track.id}
                  className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    {track.cover_url ? (
                      <img
                        src={track.cover_url}
                        alt=""
                        className="w-10 h-10 rounded-md object-cover shrink-0"
                        style={{ border: '1px solid var(--glass-border)' }}
                      />
                    ) : (
                      <div
                        className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                        style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                      >
                        &#9834;
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                        {track.title}
                      </p>
                      <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {track.artist} · {track.album} · {formatDuration(track.duration)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    <span
                      className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0"
                      style={{ background: qbc.bg, color: qbc.color }}
                    >
                      {track.quality}
                    </span>
                    <button
                      onClick={() => handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)}
                      className="btn-primary text-xs px-3 py-1.5 shrink-0"
                    >
                      &#8595; Download
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Albums */}
      {albums.length > 0 && (
        <section>
          <h3
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: 'var(--text-dim)' }}
          >
            Albums
          </h3>
          <div className="space-y-2">
            {albums.map((album, i) => (
              <div
                key={album.id}
                className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {album.cover_url ? (
                    <img
                      src={album.cover_url}
                      alt=""
                      className="w-10 h-10 rounded-md object-cover shrink-0"
                      style={{ border: '1px solid var(--glass-border)' }}
                    />
                  ) : (
                    <div
                      className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                    >
                      &#9638;
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {album.name}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {album.artist} · {album.num_tracks} tracks{album.release_date ? ` · ${album.release_date}` : ''}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleAddToQueue(album.id, 'album', album.name, album.artist)}
                  className="btn-primary text-xs px-3 py-1.5 shrink-0 ml-3"
                >
                  &#8595; Download
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
