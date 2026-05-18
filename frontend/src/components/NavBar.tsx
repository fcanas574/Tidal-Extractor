import { useApp } from '../context/AppContext';
import { auth } from '../api';

export default function NavBar() {
  const { state, dispatch } = useApp();

  const tabs: { key: typeof state.activeTab; label: string }[] = [
    { key: 'search', label: 'Search' },
    { key: 'queue', label: `Queue (${state.queue.length})` },
    { key: 'settings', label: 'Settings' },
  ];

  const handleLogout = async () => {
    await auth.logout();
    dispatch({ type: 'SET_AUTH', payload: { authenticated: false, username: null } });
  };

  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-bold text-white">TidalExtractor</h1>
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => dispatch({ type: 'SET_TAB', payload: tab.key })}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                state.activeTab === tab.key
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {state.auth.username && (
          <span className="text-sm text-gray-400">{state.auth.username}</span>
        )}
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
