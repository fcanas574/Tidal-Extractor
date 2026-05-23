import type { BeatportTrack, MatchCandidate } from '../api';

interface Props {
  beatportTrack: BeatportTrack;
  candidates: MatchCandidate[];
  onSelect: (candidate: MatchCandidate) => void;
  onCancel: () => void;
}

export default function MatchConfirmDialog({ beatportTrack, candidates, onSelect, onCancel }: Props) {
  const diffColor = (detail: string) => {
    if (detail === 'within_5pct') return 'var(--accent-primary)';
    if (detail === 'within_10pct') return 'var(--warning)';
    return 'var(--danger)';
  };

  const artistStr = beatportTrack.artists.join(', ');

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)' }}
      onClick={onCancel}
    >
      <div
        className="mx-4 p-6 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        style={{
          background: 'var(--bg-mid)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius)',
          boxShadow: '0 16px 64px rgba(0, 0, 0, 0.5)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-1" style={{ color: 'var(--text-bright)' }}>
          Confirm Match
        </h2>
        <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
          Multiple versions found on Tidal. Select the correct one.
        </p>

        {/* Beatport reference */}
        <div
          className="flex items-center gap-3 p-3 rounded-md mb-4"
          style={{
            background: 'var(--accent-dim)',
            border: '1px solid rgba(0, 229, 199, 0.2)',
          }}
        >
          {beatportTrack.cover_url ? (
            <img
              src={beatportTrack.cover_url}
              alt=""
              className="w-10 h-10 rounded object-cover shrink-0"
            />
          ) : (
            <div
              className="w-10 h-10 rounded shrink-0 flex items-center justify-center text-xs"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
            >
              BP
            </div>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
              {beatportTrack.name}
              {beatportTrack.mix_name ? ` (${beatportTrack.mix_name})` : ''}
            </p>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
              {artistStr} · {beatportTrack.length} · {beatportTrack.bpm} BPM · {beatportTrack.key}
            </p>
          </div>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded shrink-0 mono"
            style={{ background: 'rgba(0, 229, 199, 0.15)', color: 'var(--accent-primary)' }}
          >
            Beatport
          </span>
        </div>

        {/* Tidal candidates */}
        <div className="space-y-2 mb-4">
          {candidates.map((c, i) => {
            const t = c.tidal_track;
            const qMap: Record<string, { bg: string; color: string }> = {
              HI_RES: { bg: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' },
              LOSSLESS: { bg: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' },
            };
            const qStyle = qMap[t.quality] || { bg: 'var(--bg-surface)', color: 'var(--text-dim)' };

            return (
              <div
                key={i}
                className="glass p-3 flex items-center gap-3"
                style={{ border: '1px solid var(--glass-border)' }}
              >
                {t.cover_url ? (
                  <img
                    src={t.cover_url}
                    alt=""
                    className="w-10 h-10 rounded object-cover shrink-0"
                  />
                ) : (
                  <div
                    className="w-10 h-10 rounded shrink-0 flex items-center justify-center text-xs"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                  >
                    &#9834;
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                    {t.title}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                    {t.artist} · {t.album}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    {t.duration > 0 && (
                      <span
                        className="text-[10px] mono"
                        style={{ color: diffColor(c.match_details.duration_match) }}
                      >
                        {Math.floor(t.duration / 60)}:{String(t.duration % 60).padStart(2, '0')}
                      </span>
                    )}
                    <span
                      className="text-[10px] px-1 py-0.5 rounded mono"
                      style={{ background: qStyle.bg, color: qStyle.color }}
                    >
                      {t.quality}
                    </span>
                    <span
                      className="text-[10px] mono"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      Score: {c.score}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => onSelect(c)}
                  className="btn-primary text-xs px-3 py-1.5 shrink-0"
                >
                  Select
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex justify-end">
          <button
            onClick={onCancel}
            className="text-sm px-4 py-1.5 rounded"
            style={{ color: 'var(--text-dim)', border: '1px solid var(--glass-border)' }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
