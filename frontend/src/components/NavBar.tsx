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
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[tab]}
    </svg>
  );
}

function BrandMark() {
  return (
    <span className="studio-brand-mark" aria-hidden="true">
      <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
        <path d="M2 8C2 4.686 4.686 2 8 2s6 2.686 6 6-2.686 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="8" r="2" fill="currentColor" />
      </svg>
    </span>
  );
}

export default function NavBar() {
  const { state, dispatch } = useApp();

  const activeDownloads = state.queue.filter((item) => item.status === 'downloading').length;
  const pendingCount = state.queue.filter((item) => item.status !== 'complete').length;

  return (
    <aside className="studio-rail safe-area-top" aria-label="Studio navigation">
      <div className="studio-rail-inner">
        <div className="studio-brand">
          <BrandMark />
          <span className="studio-brand-name"><span>Tidal</span><span>Extractor</span></span>
        </div>

        <nav aria-label="Primary navigation" className="studio-primary-nav">
          <div className="studio-nav-list">
            {tabs.map((tab) => {
              const current = state.activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => dispatch({ type: 'SET_TAB', payload: tab.key })}
                  className={`studio-nav-tab${current ? ' is-current' : ''}`}
                  aria-current={current ? 'page' : undefined}
                  aria-label={tab.key === 'queue' && pendingCount > 0 ? `Queue, ${pendingCount} downloads needing attention` : undefined}
                >
                  <TabIcon tab={tab.key} />
                  <span>{tab.label}</span>
                  {tab.key === 'queue' && pendingCount > 0 && (
                    <span className={`studio-queue-count${activeDownloads > 0 ? ' is-active' : ''}`} aria-hidden="true">
                      {pendingCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </nav>

        <div className="studio-rail-utilities">
          <div
            className={`studio-connection${state.wsConnected ? ' is-live' : ' is-reconnecting'}`}
            title={state.wsConnected ? 'Realtime connected' : 'Realtime reconnecting'}
            role="status"
            aria-live="polite"
          >
            <span className="studio-connection-dot" aria-hidden="true" />
            <span>{state.wsConnected ? 'Live' : 'Reconnecting'}</span>
          </div>

          <button
            type="button"
            onClick={() => {
              if (state.settingsPanelOpen) dispatch({ type: 'TOGGLE_SETTINGS_PANEL' });
              dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' });
            }}
            className={`studio-utility-button${state.activityPanelOpen ? ' is-current' : ''}`}
            aria-label={pendingCount > 0 ? `Activity, ${pendingCount} downloads needing attention` : 'Activity'}
            aria-expanded={state.activityPanelOpen}
            aria-controls="download-activity-panel"
            title="Download activity"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M10 3v10m0 0 3.5-3.5M10 13 6.5 9.5M4 16.5h12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Activity</span>
            {pendingCount > 0 && (
              <span className="studio-activity-count" aria-label={`${pendingCount} downloads needing attention`}>
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
            className={`studio-utility-button${state.settingsPanelOpen ? ' is-current' : ''}`}
            title="Settings"
            aria-label="Settings"
            aria-expanded={state.settingsPanelOpen}
            aria-controls="settings-panel"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M10 13a3 3 0 100-6 3 3 0 000 6z" />
              <path d="M17.4 12.4a1.6 1.6 0 00.3 1.8l.1.1a1.9 1.9 0 11-2.7 2.7l-.1-.1a1.6 1.6 0 00-1.8-.3 1.6 1.6 0 00-1 1.5v.3a1.9 1.9 0 11-3.8 0v-.1a1.6 1.6 0 00-1-1.5 1.6 1.6 0 00-1.8.3l-.1.1a1.9 1.9 0 11-2.7-2.7l.1-.1a1.6 1.6 0 00.3-1.8 1.6 1.6 0 00-1.5-1h-.3a1.9 1.9 0 110-3.8h.1a1.6 1.6 0 001.5-1 1.6 1.6 0 00-.3-1.8l-.1-.1A1.9 1.9 0 114.9 2.7l.1.1a1.6 1.6 0 001.8.3h.1a1.6 1.6 0 001-1.5v-.3a1.9 1.9 0 013.8 0v.1a1.6 1.6 0 001 1.5 1.6 1.6 0 001.8-.3l.1-.1a1.9 1.9 0 112.7 2.7l-.1.1a1.6 1.6 0 00-.3 1.8v.1a1.6 1.6 0 001.5 1h.3a1.9 1.9 0 010 3.8h-.1a1.6 1.6 0 00-1.5 1z" />
            </svg>
            <span>Settings</span>
          </button>

          {state.auth.username && (
            <span className="studio-account-name" title={state.auth.username}>{state.auth.username}</span>
          )}
        </div>
      </div>
    </aside>
  );
}
