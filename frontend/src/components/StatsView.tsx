import { useEffect } from "react";
import { stats as statsApi } from "../api";
import { useApp } from "../context/AppContext";

export default function StatsView() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    statsApi.get().then((data) => {
      dispatch({ type: "SET_STATS", payload: data });
    });
  }, [dispatch]);

  const s = state.stats;
  const totalTracks = s.total_tracks || 0;
  const totalBytes = s.total_bytes || 0;
  const qualityBreakdown = [
    { label: "Hi-Res", value: s.quality_hi_res || 0, key: "quality_hi_res" },
    { label: "Lossless", value: s.quality_lossless || 0, key: "quality_lossless" },
    { label: "320k", value: s.quality_320k || 0, key: "quality_320k" },
    { label: "96k", value: s.quality_96k || 0, key: "quality_96k" },
  ];
  const maxQuality = Math.max(...qualityBreakdown.map((q) => q.value), 1);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <h2 className="text-lg font-bold mb-6" style={{ color: "var(--text-bright)" }}>
        Stats
      </h2>

      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="glass p-6 text-center">
          <p className="text-3xl font-bold" style={{ color: "var(--accent-primary)" }}>
            {totalTracks}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Total Tracks
          </p>
        </div>
        <div className="glass p-6 text-center">
          <p className="text-3xl font-bold" style={{ color: "var(--accent-secondary)" }}>
            {formatSize(totalBytes)}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Total Storage
          </p>
        </div>
      </div>

      <h3 className="text-sm font-medium mb-4" style={{ color: "var(--text-bright)" }}>
        Quality Breakdown
      </h3>
      <div className="space-y-3">
        {qualityBreakdown.map((q) => (
          <div key={q.key} className="glass p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{q.label}</span>
              <span className="text-xs font-medium" style={{ color: "var(--text-bright)" }}>
                {q.value}
              </span>
            </div>
            <div className="progress-track" style={{ height: "6px" }}>
              <div
                className="progress-fill"
                style={{
                  width: `${(q.value / maxQuality) * 100}%`,
                  background: "var(--accent-primary)",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs mt-6" style={{ color: "var(--text-dim)" }}>
        Stats are stored device-wide and are not tied to your Tidal account.
      </p>
    </div>
  );
}
