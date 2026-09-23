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
      <button type="button" className="settings-overlay" aria-label="Dismiss settings overlay" onClick={close} />
      <aside
        ref={panelRef}
        id="settings-panel"
        className="settings-panel animate-slide-in-right"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        aria-describedby="settings-save-status"
      >
        <header className="settings-panel-header">
          <div>
            <h2 id="settings-title">Settings</h2>
            <p>{dirty ? 'Unsaved changes' : 'Download and preview preferences'}</p>
          </div>
          <button ref={closeButtonRef} type="button" onClick={close} className="settings-close" aria-label="Close settings">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
          </button>
        </header>

        <div className="settings-body">
          <nav className="settings-section-nav" aria-label="Settings sections">
            <a href="#settings-section-account">Account</a>
            <a href="#settings-section-download">Download</a>
            <a href="#settings-section-preview">Preview</a>
            <a href="#settings-section-output">Output</a>
          </nav>

          <div className="settings-sections">
            <section id="settings-section-account" className="settings-section" aria-labelledby="settings-account-heading">
              <h3 id="settings-account-heading">Account</h3>
              <div className="settings-account-card">
                <div className="settings-avatar" aria-hidden="true">{(state.auth.username || '?')[0].toUpperCase()}</div>
                <div className="min-w-0"><p className="settings-account-name">{state.auth.username || 'Unknown'}</p><p className="settings-account-status">Connected</p></div>
              </div>
            </section>

            <section id="settings-section-download" className="settings-section" aria-labelledby="settings-download-heading">
              <h3 id="settings-download-heading">Download</h3>
              <span className="settings-choice-label">Default quality</span>
              <div className="settings-quality-list" role="group" aria-label="Default quality">
                {QUALITY_OPTIONS.map((option) => {
                  const selected = draft.default_quality === option.value;
                  return (
                    <button key={option.value} type="button" onClick={() => updateDraft({ default_quality: option.value })} className="settings-quality-option" aria-pressed={selected}>
                      <span>{option.label}</span><span className="settings-quality-badge">{option.badge}</span>
                    </button>
                  );
                })}
              </div>
              <div className="settings-choice-block">
                <span className="settings-choice-label">Default format</span>
                <div className="settings-format-options" role="group" aria-label="Default format">
                  {FORMAT_OPTIONS.map((option) => {
                    const selected = draft.default_format === option.value;
                    return <button key={option.value} type="button" onClick={() => updateDraft({ default_format: option.value })} className="settings-choice-option" aria-pressed={selected}><span>{option.label}</span><small>{option.desc}</small></button>;
                  })}
                </div>
              </div>
            </section>

            <section id="settings-section-preview" className="settings-section" aria-labelledby="settings-preview-heading">
              <h3 id="settings-preview-heading">Preview</h3>
              <div className="settings-waveform-options" role="group" aria-label="Waveform color">
                {WAVEFORM_OPTIONS.map((option) => {
                  const selected = (draft.waveform_color || '3band') === option.value;
                  return <button key={option.value} type="button" onClick={() => updateDraft({ waveform_color: option.value })} className="settings-choice-option" aria-pressed={selected}><span>{option.label}</span><small>{option.desc}</small></button>;
                })}
              </div>
              {qualityCache ? (
                <div className="settings-stream-info"><div><span>Detected stream</span><strong className="mono">{qualityCache.preset} · {qualityCache.bitrate} kbps</strong></div><button type="button" className="settings-probe-button" onClick={() => void handleProbeQuality()} disabled={probing}>{probing ? 'Probing…' : 'Re-probe'}</button></div>
              ) : (
                <button type="button" onClick={() => void handleProbeQuality()} disabled={probing} className="settings-probe-button is-wide">{probing ? 'Probing quality…' : 'Probe stream quality'}</button>
              )}
            </section>

            <section id="settings-section-output" className="settings-section" aria-labelledby="settings-output-heading">
              <h3 id="settings-output-heading">Output</h3>
              <label htmlFor="settings-output-dir" className="settings-choice-label">Output directory</label>
              <input id="settings-output-dir" type="text" value={draft.output_dir} onChange={(event) => updateDraft({ output_dir: event.target.value })} className="settings-output-input mono" />
            </section>
          </div>
        </div>

        <footer className="settings-footer">
          <div id="settings-save-status" className="settings-save-status" aria-live="polite" role={saveState === 'error' ? 'alert' : 'status'}>
            {saveState === 'error' && <p>Could not save settings. {saveError}</p>}
            {saveState === 'saved' && <p>Settings saved.</p>}
          </div>
          <div className="settings-save-actions">
            <button type="button" onClick={() => void handleSave()} disabled={savingOrClean(saveState, dirty)} className="settings-save-button">
              {saveState === 'saving' ? 'Saving…' : saveState === 'error' ? 'Retry save' : 'Save changes'}
            </button>
            {dirty && saveState !== 'saving' && <button type="button" className="settings-discard-button" onClick={() => { setDraft(state.settings); setSaveState('idle'); setSaveError(null); }}>Discard</button>}
          </div>
          <div className="settings-disconnect">
            <div><strong>Account</strong><span>Disconnect this device from Tidal.</span></div>
            <button type="button" onClick={() => void handleLogout()}>Disconnect account</button>
          </div>
        </footer>
      </aside>
    </>
  );
}

function savingOrClean(saveState: SaveState, dirty: boolean) {
  return saveState === 'saving' || (!dirty && saveState !== 'error');
}
