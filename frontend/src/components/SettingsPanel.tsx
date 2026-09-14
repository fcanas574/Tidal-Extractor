import { useEffect, useRef, useState } from 'react';
import { settings, quality, auth } from '../api';
import type { Settings } from '../api';
import { useApp } from '../context/AppContext';

const QUALITY_OPTIONS = [
  { value: 'auto_max', label: 'Auto (max quality per track)', badge: 'AUTO' },
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

const WAVEFORM_OPTIONS: { value: Settings['waveform_color']; label: string; desc: string }[] = [
  { value: '3band', label: '3Band (Rekordbox)', desc: 'Blue / orange / white' },
  { value: 'rgb', label: 'RGB', desc: 'Red / green / blue blend' },
];

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export default function SettingsPanel() {
  const { state, dispatch } = useApp();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [draft, setDraft] = useState<Settings>(state.settings);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [qualityCache, setQualityCache] = useState<{ preset: string; bitrate: number } | null>(null);
  const [probing, setProbing] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(state.settings);

  useEffect(() => {
    if (!state.settingsPanelOpen) {
      if (!state.activityPanelOpen) triggerRef.current?.focus();
      triggerRef.current = null;
      return;
    }
    const activeElement = document.activeElement;
    triggerRef.current = activeElement instanceof HTMLElement ? activeElement : null;
    setDraft(state.settings);
    setSaveState('idle');
    setSaveError(null);
    closeButtonRef.current?.focus();
    quality.cache().then(setQualityCache).catch(() => undefined);
  }, [state.activityPanelOpen, state.settingsPanelOpen]);

  useEffect(() => {
    if (!state.settingsPanelOpen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
        return;
      }
      if (event.key !== 'Tab') return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      ));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!panel.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [dispatch, state.settingsPanelOpen]);

  const close = () => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
  const updateDraft = (changes: Partial<Settings>) => {
    setDraft((previous) => ({ ...previous, ...changes }));
    setSaveState('idle');
    setSaveError(null);
  };

  const handleSave = async () => {
    setSaveState('saving');
    setSaveError(null);
    try {
      const updated = await settings.update(draft);
      dispatch({ type: 'SET_SETTINGS', payload: updated });
      setDraft(updated);
      setSaveState('saved');
    } catch (error) {
      setSaveState('error');
      setSaveError(error instanceof Error ? error.message : 'Could not save settings.');
    }
  };

  const handleProbeQuality = async () => {
    setProbing(true);
    try {
      const result = await quality.probe();
      setQualityCache(result);
      dispatch({ type: 'ADD_TOAST', payload: { id: `probe-${Date.now()}`, type: 'success', title: 'Quality detected', detail: `${result.preset} · ${result.bitrate} kbps`, dismissAt: Date.now() + 4000 } });
    } catch (error) {
      dispatch({ type: 'ADD_TOAST', payload: { id: `probe-err-${Date.now()}`, type: 'error', title: 'Quality probe failed', detail: error instanceof Error ? error.message : undefined, dismissAt: Date.now() + 5000 } });
    } finally {
      setProbing(false);
    }
  };

  const handleLogout = async () => {
    await auth.logout();
    dispatch({ type: 'SET_AUTH', payload: { authenticated: false, username: null } });
    close();
  };

  if (!state.settingsPanelOpen) return null;

  return (
    <>
      <button type="button" className="fixed inset-0 z-40" aria-label="Dismiss settings overlay" onClick={close} style={{ background: 'rgba(4, 8, 18, 0.6)' }} />
      <aside ref={panelRef} id="settings-panel" className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-[380px] animate-slide-in-right overflow-y-auto" role="dialog" aria-modal="true" aria-labelledby="settings-title" aria-describedby="settings-save-status" style={{ background: 'var(--bg-deep)', borderLeft: '1px solid var(--glass-border)', boxShadow: '-20px 0 60px rgba(0, 0, 0, 0.5)' }}>
        <div className="p-6">
          <div className="flex items-center justify-between mb-6"><div><h2 id="settings-title" className="text-sm font-semibold uppercase tracking-widest" style={{ color: 'var(--accent-primary)' }}>Settings</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{dirty ? 'Unsaved changes' : 'Download preferences'}</p></div><button ref={closeButtonRef} type="button" onClick={close} className="btn-ghost p-2" aria-label="Close settings"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg></button></div>
          <div className="glow-line mb-6" />

          <section className="mb-7" aria-labelledby="settings-account-heading"><h3 id="settings-account-heading" className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>Account</h3><div className="glass p-4"><div className="flex items-center gap-3"><div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold" aria-hidden="true" style={{ background: 'var(--accent-dim)', color: 'var(--accent-primary)' }}>{(state.auth.username || '?')[0].toUpperCase()}</div><div className="min-w-0"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{state.auth.username || 'Unknown'}</p><p className="text-xs" style={{ color: 'var(--text-muted)' }}>Connected</p></div></div></div></section>

          <section className="mb-7" aria-labelledby="settings-download-heading"><h3 id="settings-download-heading" className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>Download defaults</h3><div className="space-y-2">{QUALITY_OPTIONS.map((option) => { const selected = draft.default_quality === option.value; return <button key={option.value} type="button" onClick={() => updateDraft({ default_quality: option.value })} className="w-full glass glass-hover p-3 flex items-center justify-between text-left" aria-pressed={selected} style={{ borderColor: selected ? 'rgba(141, 231, 213, 0.4)' : undefined }}><span className="text-sm" style={{ color: 'var(--text-primary)' }}>{option.label}</span><span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: selected ? 'var(--accent-dim)' : 'var(--bg-surface)', color: selected ? 'var(--accent-primary)' : 'var(--text-dim)' }}>{option.badge}</span></button>; })}</div><div className="mt-4"><span className="block text-xs mb-2" style={{ color: 'var(--text-muted)' }}>Default format</span><div className="grid grid-cols-3 gap-2">{FORMAT_OPTIONS.map((option) => { const selected = draft.default_format === option.value; return <button key={option.value} type="button" onClick={() => updateDraft({ default_format: option.value })} className="glass glass-hover p-3 text-center" aria-pressed={selected} style={{ borderColor: selected ? 'rgba(141, 231, 213, 0.4)' : undefined }}><span className="mono text-sm font-semibold" style={{ color: selected ? 'var(--accent-primary)' : 'var(--text-primary)' }}>{option.label}</span><span className="block text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>{option.desc}</span></button>; })}</div></div></section>

          <section className="mb-7" aria-labelledby="settings-preview-heading"><h3 id="settings-preview-heading" className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>Preview</h3><div className="grid grid-cols-2 gap-2">{WAVEFORM_OPTIONS.map((option) => { const selected = (draft.waveform_color || '3band') === option.value; return <button key={option.value} type="button" onClick={() => updateDraft({ waveform_color: option.value })} className="glass glass-hover p-3 text-center" aria-pressed={selected} style={{ borderColor: selected ? 'rgba(141, 231, 213, 0.4)' : undefined }}><span className="mono text-sm font-semibold" style={{ color: selected ? 'var(--accent-primary)' : 'var(--text-primary)' }}>{option.label}</span><span className="block text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>{option.desc}</span></button>; })}</div>{qualityCache ? <div className="glass p-4 mt-3 flex items-center justify-between"><div><p className="text-xs" style={{ color: 'var(--text-muted)' }}>Detected stream</p><p className="mono text-sm mt-1" style={{ color: 'var(--text-bright)' }}>{qualityCache.preset} · {qualityCache.bitrate} kbps</p></div><button type="button" className="btn-ghost text-xs" onClick={() => void handleProbeQuality()} disabled={probing}>{probing ? 'Probing…' : 'Re-probe'}</button></div> : <button type="button" onClick={() => void handleProbeQuality()} disabled={probing} className="btn-ghost w-full text-sm mt-3" style={{ borderColor: 'var(--glass-border)', color: 'var(--accent-primary)' }}>{probing ? 'Probing quality…' : 'Probe stream quality'}</button>}</section>

          <section className="mb-7" aria-labelledby="settings-output-heading"><h3 id="settings-output-heading" className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--text-dim)' }}>Output</h3><label htmlFor="settings-output-dir" className="text-xs" style={{ color: 'var(--text-muted)' }}>Output directory</label><input id="settings-output-dir" type="text" value={draft.output_dir} onChange={(event) => updateDraft({ output_dir: event.target.value })} className="input-abyss text-sm mono mt-2" /></section>

          <div className="glow-line mb-5" /><div id="settings-save-status" className="min-h-5 mb-2" aria-live="polite" role={saveState === 'error' ? 'alert' : 'status'}>{saveState === 'error' && <p className="text-xs" style={{ color: 'var(--danger)' }}>Could not save settings. {saveError}</p>}{saveState === 'saved' && <p className="text-xs" style={{ color: 'var(--success)' }}>Settings saved.</p>}</div><div className="flex gap-2 mb-5"><button type="button" onClick={() => void handleSave()} disabled={savingOrClean(saveState, dirty)} className="btn-primary flex-1 text-sm">{saveState === 'saving' ? 'Saving…' : saveState === 'error' ? 'Retry save' : 'Save changes'}</button>{dirty && saveState !== 'saving' && <button type="button" className="btn-ghost text-xs" onClick={() => { setDraft(state.settings); setSaveState('idle'); setSaveError(null); }}>Discard</button>}</div><button type="button" onClick={() => void handleLogout()} className="btn-danger w-full text-center py-2">Disconnect account</button>
        </div>
      </aside>
    </>
  );
}

function savingOrClean(saveState: SaveState, dirty: boolean) {
  return saveState === 'saving' || (!dirty && saveState !== 'error');
}
