import { useEffect, useState } from 'react';
import { settings, quality, auth } from '../api';
import { useApp } from '../context/AppContext';

const QUALITY_OPTIONS = [
  { value: 'hi_res_lossless', label: 'HiRes Lossless (24-bit, up to 192kHz)', badge: 'HI-RES' },
  { value: 'high_lossless', label: 'Lossless (16-bit FLAC, 44.1kHz)', badge: 'LOSSLESS' },
  { value: 'low_320k', label: 'High (320kbps AAC)', badge: '320K' },
  { value: 'low_96k', label: 'Normal (96kbps AAC)', badge: '96K' },
];

const FORMAT_OPTIONS = [
  { value: 'FLAC', label: 'FLAC', desc: 'Lossless, largest files' },
  { value: 'MP3', label: 'MP3', desc: '320kbps, broad compat' },
  { value: 'M4A', label: 'M4A', desc: '320kbps, Apple ecosystem' },
];

export default function SettingsPanel() {
  const { state, dispatch } = useApp();
  const [saving, setSaving] = useState(false);
  const [qualityCache, setQualityCache] = useState<{ preset: string; bitrate: number } | null>(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    if (state.settingsPanelOpen) {
      quality.cache().then(setQualityCache).catch(() => {});
    }
  }, [state.settingsPanelOpen]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await settings.update(state.settings);
      dispatch({ type: 'SET_SETTINGS', payload: updated });
    } finally {
      setSaving(false);
    }
  };

  const handleProbeQuality = async () => {
    setProbing(true);
    try {
      const result = await quality.probe();
      setQualityCache(result);
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `probe-${Date.now()}`,
          type: 'success',
          title: 'Quality detected',
          detail: `${result.preset} · ${result.bitrate} kbps`,
          dismissAt: Date.now() + 4000,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `probe-err-${Date.now()}`,
          type: 'error',
          title: 'Quality probe failed',
          dismissAt: Date.now() + 4000,
        },
      });
    } finally {
      setProbing(false);
    }
  };

  const handleLogout = async () => {
    await auth.logout();
    dispatch({ type: 'SET_AUTH', payload: { authenticated: false, username: null } });
    dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
  };

  if (!state.settingsPanelOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        style={{ background: 'rgba(4, 8, 18, 0.6)' }}
        onClick={() => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' })}
      />
      <aside
        className="fixed top-0 right-0 bottom-0 z-50 w-[340px] animate-slide-in-right overflow-y-auto"
        style={{
          background: 'var(--bg-deep)',
          borderLeft: '1px solid var(--glass-border)',
          boxShadow: '-20px 0 60px rgba(0, 0, 0, 0.5)',
        }}
      >
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-widest" style={{ color: 'var(--accent-primary)' }}>
              Settings
            </h2>
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' })}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4l8 8M12 4l-8 8"/>
              </svg>
            </button>
          </div>

          <div className="glow-line mb-6" />

          {/* Account */}
          <section className="mb-6">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>
              Account
            </h3>
            <div className="glass p-4">
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
                  style={{ background: 'var(--accent-dim)', color: 'var(--accent-primary)' }}
                >
                  {(state.auth.username || '?')[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                    {state.auth.username || 'Unknown'}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Connected</p>
                </div>
              </div>
            </div>
          </section>

          {/* Detected Quality */}
          {qualityCache && (
            <section className="mb-6">
              <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>
                Detected Quality
              </h3>
              <div className="glass p-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>
                    {qualityCache.preset}
                  </p>
                  <p className="mono text-xs" style={{ color: 'var(--text-muted)' }}>
                    {qualityCache.bitrate} kbps
                  </p>
                </div>
                <button
                  onClick={handleProbeQuality}
                  disabled={probing}
                  className="btn-ghost text-xs"
                  style={{ color: 'var(--accent-primary)' }}
                >
                  {probing ? 'Probing...' : 'Re-probe'}
                </button>
              </div>
            </section>
          )}

          {!qualityCache && (
            <section className="mb-6">
              <button
                onClick={handleProbeQuality}
                disabled={probing}
                className="btn-ghost w-full text-sm text-center py-3"
                style={{ color: 'var(--accent-primary)', borderColor: 'var(--glass-border)' }}
              >
                {probing ? 'Probing quality...' : 'Probe Stream Quality'}
              </button>
            </section>
          )}

          {/* Quality Preset */}
          <section className="mb-6">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>
              Default Quality
            </h3>
            <div className="space-y-2">
              {QUALITY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() =>
                    dispatch({
                      type: 'SET_SETTINGS',
                      payload: { ...state.settings, default_quality: opt.value },
                    })
                  }
                  className="w-full glass glass-hover p-3 flex items-center justify-between transition-all"
                  style={{
                    borderColor:
                      state.settings.default_quality === opt.value
                        ? 'rgba(0, 229, 199, 0.3)'
                        : undefined,
                  }}
                >
                  <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                    {opt.label}
                  </span>
                  <span
                    className="mono text-[10px] px-1.5 py-0.5 rounded"
                    style={{
                      background:
                        state.settings.default_quality === opt.value
                          ? 'rgba(0, 229, 199, 0.15)'
                          : 'var(--bg-surface)',
                      color:
                        state.settings.default_quality === opt.value
                          ? 'var(--accent-primary)'
                          : 'var(--text-dim)',
                    }}
                  >
                    {opt.badge}
                  </span>
                </button>
              ))}
            </div>
          </section>

          {/* Format */}
          <section className="mb-6">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>
              Default Format
            </h3>
            <div className="flex gap-2">
              {FORMAT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() =>
                    dispatch({
                      type: 'SET_SETTINGS',
                      payload: { ...state.settings, default_format: opt.value },
                    })
                  }
                  className="flex-1 glass glass-hover p-3 text-center transition-all"
                  style={{
                    borderColor:
                      state.settings.default_format === opt.value
                        ? 'rgba(0, 229, 199, 0.3)'
                        : undefined,
                  }}
                >
                  <p
                    className="mono text-sm font-semibold"
                    style={{
                      color:
                        state.settings.default_format === opt.value
                          ? 'var(--accent-primary)'
                          : 'var(--text-primary)',
                    }}
                  >
                    {opt.label}
                  </p>
                  <p className="text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>
                    {opt.desc}
                  </p>
                </button>
              ))}
            </div>
          </section>

          {/* Output Directory */}
          <section className="mb-6">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>
              Output Directory
            </h3>
            <input
              type="text"
              value={state.settings.output_dir}
              onChange={(e) =>
                dispatch({
                  type: 'SET_SETTINGS',
                  payload: { ...state.settings, output_dir: e.target.value },
                })
              }
              className="input-abyss text-sm mono"
            />
          </section>

          <div className="glow-line mb-6" />

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary w-full mb-4 text-sm"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>

          {/* Logout */}
          <button
            onClick={handleLogout}
            className="btn-danger w-full text-center py-2"
          >
            Disconnect Account
          </button>
        </div>
      </aside>
    </>
  );
}
