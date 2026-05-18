import { useEffect, useState } from 'react';
import { settings, quality } from '../api';
import { useApp } from '../context/AppContext';

const QUALITY_OPTIONS = [
  { value: 'hi_res_lossless', label: 'HiRes Lossless (24-bit, up to 192kHz)' },
  { value: 'high_lossless', label: 'Lossless (16-bit FLAC, 44.1kHz)' },
  { value: 'low_320k', label: 'High (320kbps AAC)' },
  { value: 'low_96k', label: 'Normal (96kbps AAC)' },
];

const FORMAT_OPTIONS = [
  { value: 'FLAC', label: 'FLAC (lossless, largest files)' },
  { value: 'MP3', label: 'MP3 (320kbps, broad compatibility)' },
  { value: 'M4A', label: 'M4A/AAC (320kbps, Apple ecosystem)' },
];

export default function SettingsView() {
  const { state, dispatch } = useApp();
  const [saving, setSaving] = useState(false);
  const [qualityCache, setQualityCache] = useState<{ preset: string; bitrate: number } | null>(null);

  useEffect(() => {
    settings.get().then((s) => dispatch({ type: 'SET_SETTINGS', payload: s }));
    quality.cache().then(setQualityCache).catch(() => {});
  }, [dispatch]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await settings.update(state.settings);
      dispatch({ type: 'SET_SETTINGS', payload: updated });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h2 className="text-xl font-bold mb-6">Settings</h2>

      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Account</h3>
        <p className="text-white">
          {state.auth.authenticated
            ? `Connected as ${state.auth.username || 'Unknown'}`
            : 'Not connected'}
        </p>
      </section>

      {qualityCache && (
        <section className="bg-gray-800 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Detected Quality</h3>
          <p className="text-white">
            {qualityCache.preset} &middot; {qualityCache.bitrate} kbps
          </p>
        </section>
      )}

      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Default Quality</h3>
        <select
          value={state.settings.default_quality}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, default_quality: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        >
          {QUALITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </section>

      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Default Format</h3>
        <select
          value={state.settings.default_format}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, default_format: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        >
          {FORMAT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </section>

      <section className="bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-2">Output Directory</h3>
        <input
          type="text"
          value={state.settings.output_dir}
          onChange={(e) =>
            dispatch({
              type: 'SET_SETTINGS',
              payload: { ...state.settings, output_dir: e.target.value },
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
        />
      </section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors"
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
