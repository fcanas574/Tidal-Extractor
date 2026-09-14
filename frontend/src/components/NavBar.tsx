import { useApp } from '../context/AppContext';

const tabs: { key: 'search' | 'queue' | 'history' | 'stats'; label: string }[] = [
  { key: 'search', label: 'Search' },
  { key: 'queue', label: 'Queue' },
  { key: 'history', label: 'History' },
  { key: 'stats', label: 'Stats' },
];

function TabIcon({ tab }: { tab: (typeof tabs)[number]['key'] }) {
  const paths = {
    search: <><circle cx="7.5" cy="7.5" r="4.5" /><path d="m11 11 4 4" /></>,
    queue: <><path d="M10 3v10m0 0 3.5-3.5M10 13 6.5 9.5M4 16.5h12" /></>,
    history: <><path d="M3 10a7 7 0 1 0 2-4.9" /><path d="M3 4v6h6M10 6v4l2.5 1.5" /></>,
    stats: <><path d="M4 16V9m4 7V5m4 11v-4m4 4V3" /></>,
  };

  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[tab]}
    </svg>
  );
}

export default function NavBar() {
  const { state, dispatch } = useApp();

  const activeDownloads = state.queue.filter((i) => i.status === 'downloading').length;
  const pendingCount = state.queue.filter((i) => i.status !== 'complete').length;

  return (
    <nav
      aria-label="Primary navigation"
      className="safe-area-top relative z-30 overflow-x-auto border-b"
      style={{ background: 'var(--obsidian)', borderColor: 'var(--glass-border)' }}
    >
      <div className="mx-auto flex min-w-max w-full max-w-[1280px] items-center gap-5 px-4 py-3 sm:gap-8 sm:px-6">
        <div className="flex shrink-0 items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 8C2 4.686 4.686 2 8 2s6 2.686 6 6-2.686 6-6 6" stroke="var(--bg-abyss)" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="8" cy="8" r="2" fill="var(--bg-abyss)"/>
            </svg>
          </div>
          <h1 className="text-base font-bold tracking-wide" style={{ color: 'var(--text-bright)' }}>
            Tidal<span style={{ color: 'var(--accent-primary)' }}>Extractor</span>
          </h1>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => dispatch({ type: 'SET_TAB', payload: tab.key })}
              className="relative flex min-h-10 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 sm:px-4"
              style={{
                color: state.activeTab === tab.key ? 'var(--text-bright)' : 'var(--text-muted)',
                background: state.activeTab === tab.key ? 'var(--accent-dim)' : 'transparent',
              }}
              aria-current={state.activeTab === tab.key ? 'page' : undefined}
            >
              <TabIcon tab={tab.key} />
              <span>{tab.label}</span>
              {tab.key === 'queue' && pendingCount > 0 && (
                <span
                  className="mono text-xs px-1.5 py-0.5 rounded-md"
                  style={{
                    background: activeDownloads > 0 ? 'rgba(0, 229, 199, 0.15)' : 'var(--bg-surface)',
                    color: activeDownloads > 0 ? 'var(--accent-primary)' : 'var(--text-muted)',
                  }}
                >
                  {pendingCount}
                </span>
              )}
              {state.activeTab === tab.key && (
                <span
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 h-[2px] w-6 rounded-full"
                  style={{ background: 'var(--accent-primary)' }}
                />
              )}
            </button>
          ))}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-4">
        {state.auth.username && (
          <span className="hidden max-w-36 truncate text-xs mono sm:inline" style={{ color: 'var(--text-dim)' }}>
            {state.auth.username}
          </span>
        )}

          <div
            className="flex items-center gap-2 text-xs whitespace-nowrap"
            style={{ color: state.wsConnected ? 'var(--success)' : 'var(--warning)' }}
            title={state.wsConnected ? 'Realtime connected' : 'Realtime reconnecting'}
            role="status"
            aria-live="polite"
          >
            <span className="glow-dot shrink-0" aria-hidden="true" style={{ background: state.wsConnected ? 'var(--success)' : 'var(--warning)' }} />
            <span>{state.wsConnected ? 'Live' : 'Reconnecting'}</span>
          </div>

          <button
            type="button"
            onClick={() => {
              if (state.settingsPanelOpen) dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
              dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' });
            }}
            className="relative flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all duration-200"
            style={{
              color: state.activityPanelOpen ? 'var(--accent-primary)' : 'var(--text-muted)',
              background: state.activityPanelOpen ? 'var(--accent-dim)' : 'transparent',
              border: state.activityPanelOpen ? '1px solid rgba(141, 231, 213, 0.2)' : '1px solid transparent',
            }}
            aria-expanded={state.activityPanelOpen}
            aria-controls="download-activity-panel"
            title="Download activity"
          >
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M10 3v10m0 0 3.5-3.5M10 13 6.5 9.5M4 16.5h12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Activity</span>
            {pendingCount > 0 && (
              <span
                className="mono text-[10px] min-w-5 px-1 py-0.5 rounded-md text-center"
                style={{
                  background: activeDownloads > 0 ? 'rgba(141, 231, 213, 0.15)' : 'var(--bg-surface)',
                  color: activeDownloads > 0 ? 'var(--accent-primary)' : 'var(--text-muted)',
                }}
                aria-label={`${pendingCount} downloads needing attention`}
              >
                {pendingCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => {
              if (state.activityPanelOpen) dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' });
              dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
            }}
            className="p-2 rounded-lg transition-all duration-200"
            style={{
              color: state.settingsPanelOpen ? 'var(--accent-primary)' : 'var(--text-muted)',
              background: state.settingsPanelOpen ? 'var(--accent-dim)' : 'transparent',
              border: state.settingsPanelOpen ? '1px solid rgba(0, 229, 199, 0.15)' : '1px solid transparent',
            }}
            title="Settings"
            aria-label="Settings"
            aria-expanded={state.settingsPanelOpen}
            aria-controls="settings-panel"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 13a3 3 0 100-6 3 3 0 000 6z"/>
              <path d="M17.4 12.4a1.6 1.6 0 00.3 1.8l.1.1a1.9 1.9 0 11-2.7 2.7l-.1-.1a1.6 1.6 0 00-1.8-.3 1.6 1.6 0 00-1 1.5v.3a1.9 1.9 0 11-3.8 0v-.1a1.6 1.6 0 00-1-1.5 1.6 1.6 0 00-1.8.3l-.1.1a1.9 1.9 0 11-2.7-2.7l.1-.1a1.6 1.6 0 00.3-1.8 1.6 1.6 0 00-1.5-1h-.3a1.9 1.9 0 110-3.8h.1a1.6 1.6 0 001.5-1 1.6 1.6 0 00-.3-1.8l-.1-.1A1.9 1.9 0 114.9 2.7l.1.1a1.6 1.6 0 001.8.3h.1a1.6 1.6 0 001-1.5v-.3a1.9 1.9 0 013.8 0v.1a1.6 1.6 0 001 1.5 1.6 1.6 0 001.8-.3l.1-.1a1.9 1.9 0 112.7 2.7l-.1.1a1.6 1.6 0 00-.3 1.8v.1a1.6 1.6 0 001.5 1h.3a1.9 1.9 0 010 3.8h-.1a1.6 1.6 0 00-1.5 1z"/>
            </svg>
          </button>
          </div>
        </div>
    </nav>
  );
}
