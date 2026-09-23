import { useCallback, useEffect, useState } from 'react';
import { stats as statsApi } from '../api';
import { useApp } from '../context/AppContext';

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function StatsView() {
  const { state, dispatch } = useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      dispatch({ type: 'SET_STATS', payload: await statsApi.get() });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load statistics.');
    } finally {
      setLoading(false);
    }
  }, [dispatch]);

  useEffect(() => { void loadStats(); }, [loadStats]);

  const stats = state.stats;
  const totalTracks = stats.total_tracks || 0;
  const totalBytes = stats.total_bytes || 0;
  const qualityBreakdown = [
    { label: 'Hi-Res', value: stats.quality_hi_res || 0 },
    { label: 'Lossless', value: stats.quality_lossless || 0 },
    { label: '320k', value: stats.quality_320k || 0 },
    { label: '96k', value: stats.quality_96k || 0 },
  ];
  const maxQuality = Math.max(...qualityBreakdown.map((quality) => quality.value), 1);

  return (
    <div className="stats-workspace animate-fade-in">
      <header className="stats-command">
        <h1 className="stats-page-title">Stats</h1>
      </header>

      {loading ? (
        <div className="stats-state" role="status" aria-live="polite">Loading stats…</div>
      ) : error ? (
        <div className="stats-state is-error" role="alert"><p>Could not load stats.</p><p>{error}</p><button type="button" className="history-download-button" onClick={() => void loadStats()}>Retry</button></div>
      ) : (
        <>
          <section className="stats-summary" aria-labelledby="stats-summary-heading">
            <h2 id="stats-summary-heading" className="stats-section-label">Library</h2>
            <div className="stats-metrics">
              <div className="stats-metric"><p className="stats-metric-value mono">{totalTracks.toLocaleString()}</p><p className="stats-metric-label">Downloaded tracks</p></div>
              <div className="stats-metric"><p className="stats-metric-value mono">{formatSize(totalBytes)}</p><p className="stats-metric-label">Storage used</p></div>
            </div>
          </section>

          <section className="stats-quality" aria-labelledby="quality-breakdown-heading">
            <div className="stats-section-heading"><h2 id="quality-breakdown-heading">Quality distribution</h2><span>Tracks by format</span></div>
            <ul className="stats-quality-list">
            {qualityBreakdown.map((quality) => {
              const percent = totalTracks > 0 ? Math.round((quality.value / totalTracks) * 100) : 0;
              return (
                <li key={quality.label} className="stats-quality-row">
                  <div className="stats-quality-values"><span>{quality.label}</span><span className="mono">{quality.value.toLocaleString()} <span className="stats-quality-percent">({percent}%)</span></span></div>
                  <div className="stats-quality-track" role="progressbar" aria-label={`${quality.label} quality distribution`} aria-valuemin={0} aria-valuemax={maxQuality} aria-valuenow={quality.value}>
                    <div className="stats-quality-fill" style={{ width: `${(quality.value / maxQuality) * 100}%` }} />
                  </div>
                </li>
              );
            })}
            </ul>
          </section>
          <p className="stats-note">Stats are stored device-wide and are not tied to your Tidal account.</p>
        </>
      )}
    </div>
  );
}
