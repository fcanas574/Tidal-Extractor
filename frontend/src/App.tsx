import { useEffect, useCallback } from 'react';
import { AppProvider, useApp } from './context/AppContext';
import { useWebSocket } from './hooks/useWebSocket';
import { queue, settings } from './api';
import AuthGate from './components/AuthGate';
import NavBar from './components/NavBar';
import SearchView from './components/SearchView';
import QueueView from './components/QueueView';
import HistoryView from './components/HistoryView';
import StatsView from './components/StatsView';
import SettingsPanel from './components/SettingsPanel';
import ToastContainer from './components/ToastContainer';
import AudioPlayerFooter from './components/AudioPlayerFooter';
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

  useEffect(() => {
    if (!state.wsConnected) return;

    const id = setInterval(() => {
      queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
    }, 5000);

    return () => clearInterval(id);
  }, [state.wsConnected, dispatch]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore if typing in an input field
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.code) {
        case 'Space':
          if (state.previewTrack) {
            e.preventDefault();
            // Toggle play/pause - dispatch custom event for AudioPlayerFooter to catch
            window.dispatchEvent(new CustomEvent('preview-toggle-play'));
          }
          break;
        case 'Escape':
          if (state.previewTrack) {
            e.preventDefault();
            dispatch({ type: 'CLEAR_PREVIEW' });
          }
          break;
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.previewTrack, dispatch]);

  const renderView = () => {
    switch (state.activeTab) {
      case 'search':
        return <SearchView />;
      case 'queue':
        return <QueueView />;
      case 'history':
        return <HistoryView />;
      case 'stats':
        return <StatsView />;
    }
  };

  return (
    <AuthGate>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1" style={{ paddingBottom: state.previewTrack ? '120px' : 0 }}>{renderView()}</main>
        <SettingsPanel />
        <ToastContainer />
        <AudioPlayerFooter />
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
