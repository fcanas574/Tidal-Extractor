import { useEffect, useCallback } from 'react';
import { AppProvider, useApp } from './context/AppContext';
import { useWebSocket } from './hooks/useWebSocket';
import { queue, settings } from './api';
import AuthGate from './components/AuthGate';
import NavBar from './components/NavBar';
import SearchView from './components/SearchView';
import QueueView from './components/QueueView';
import SettingsView from './components/SettingsView';
import type { WsMessage } from './api';

function AppContent() {
  const { state, dispatch } = useApp();

  const handleWsMessage = useCallback((msg: WsMessage) => {
    dispatch({ type: 'WS_MESSAGE', payload: msg });
  }, [dispatch]);

  useWebSocket(handleWsMessage);

  useEffect(() => {
    settings.get().then((s) => dispatch({ type: 'SET_SETTINGS', payload: s }));
    queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
  }, [dispatch]);

  const renderView = () => {
    switch (state.activeTab) {
      case 'search':
        return <SearchView />;
      case 'queue':
        return <QueueView />;
      case 'settings':
        return <SettingsView />;
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1">{renderView()}</main>
      </div>
    </AuthGate>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
