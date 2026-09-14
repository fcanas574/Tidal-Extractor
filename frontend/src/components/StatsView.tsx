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
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <div className="mb-6"><h1 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>Stats</h1><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>A quiet view of your local download library.</p></div>

      {loading ? (
        <div className="glass p-8 text-center" role="status" aria-live="polite"><span className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading stats…</span></div>
      ) : error ? (
        <div className="glass p-8 text-center" role="alert"><p className="text-sm" style={{ color: 'var(--text-bright)' }}>Could not load stats.</p><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{error}</p><button type="button" className="btn-primary text-xs mt-4" onClick={() => void loadStats()}>Retry</button></div>
      ) : (
        <>
          <section className="glass p-5 mb-7" aria-labelledby="stats-summary-heading">
            <h2 id="stats-summary-heading" className="text-xs font-medium uppercase tracking-wider mb-5" style={{ color: 'var(--text-muted)' }}>Library summary</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div><p className="mono text-3xl font-semibold" style={{ color: 'var(--text-bright)' }}>{totalTracks.toLocaleString()}</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Downloaded tracks</p></div>
              <div><p className="mono text-3xl font-semibold" style={{ color: 'var(--text-bright)' }}>{formatSize(totalBytes)}</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Storage used</p></div>
            </div>
          </section>

          <section aria-labelledby="quality-breakdown-heading"><div className="flex items-center justify-between mb-4"><h2 id="quality-breakdown-heading" className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>Quality distribution</h2><span className="text-xs" style={{ color: 'var(--text-dim)' }}>Tracks by format</span></div><div className="space-y-3">
            {qualityBreakdown.map((quality) => {
              const percent = totalTracks > 0 ? Math.round((quality.value / totalTracks) * 100) : 0;
              return <div key={quality.label} className="glass p-3"><div className="flex items-center justify-between gap-4 mb-2"><span className="text-xs" style={{ color: 'var(--text-muted)' }}>{quality.label}</span><span className="mono text-xs" style={{ color: 'var(--text-bright)' }}>{quality.value.toLocaleString()} <span style={{ color: 'var(--text-dim)' }}>({percent}%)</span></span></div><div className="progress-track" role="progressbar" aria-label={`${quality.label} quality distribution`} aria-valuemin={0} aria-valuemax={maxQuality} aria-valuenow={quality.value}><div className="progress-fill" style={{ width: `${(quality.value / maxQuality) * 100}%`, background: 'var(--accent-primary)' }} /></div></div>;
            })}
          </div></section>
          <p className="text-xs mt-6" style={{ color: 'var(--text-dim)' }}>Stats are stored device-wide and are not tied to your Tidal account.</p>
        </>
      )}
    </div>
  );
}
