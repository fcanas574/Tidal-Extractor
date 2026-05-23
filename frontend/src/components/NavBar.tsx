import { useApp } from '../context/AppContext';

const tabs: { key: 'search' | 'queue' | 'beatport'; label: string; icon: string }[] = [
  { key: 'search', label: 'Search', icon: '⌕' },
  { key: 'beatport', label: 'Beatport', icon: '♫' },
  { key: 'queue', label: 'Queue', icon: '↓' },
];

export default function NavBar() {
  const { state, dispatch } = useApp();

  const activeDownloads = state.queue.filter((i) => i.status === 'downloading').length;
  const pendingCount = state.queue.filter((i) => i.status !== 'complete').length;

  return (
    <nav className="relative z-30 flex items-center justify-between px-6 py-4">
      <div className="flex items-center gap-8">
        <div className="flex items-center gap-3">
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

        <div className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => dispatch({ type: 'SET_TAB', payload: tab.key })}
              className="relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200"
              style={{
                color: state.activeTab === tab.key ? 'var(--text-bright)' : 'var(--text-muted)',
                background: state.activeTab === tab.key ? 'var(--accent-dim)' : 'transparent',
              }}
            >
              <span className="text-base">{tab.icon}</span>
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
      </div>

      <div className="flex items-center gap-4">
        {state.auth.username && (
          <span className="text-xs mono" style={{ color: 'var(--text-dim)' }}>
            {state.auth.username}
          </span>
        )}

        <div className="flex items-center gap-1">
          {state.wsConnected && (
            <div className="glow-dot" title="Connected" />
          )}

          <button
            onClick={() => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' })}
            className="p-2 rounded-lg transition-all duration-200"
            style={{
              color: state.settingsPanelOpen ? 'var(--accent-primary)' : 'var(--text-muted)',
              background: state.settingsPanelOpen ? 'var(--accent-dim)' : 'transparent',
              border: state.settingsPanelOpen ? '1px solid rgba(0, 229, 199, 0.15)' : '1px solid transparent',
            }}
            title="Settings"
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
