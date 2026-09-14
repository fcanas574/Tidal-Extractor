import { useCallback, useEffect, useState } from 'react';
import { history as historyApi } from '../api';
import type { HistoryItem } from '../api';
import { useApp } from '../context/AppContext';

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function HistoryView() {
  const { state, dispatch } = useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<Record<number, 'loading' | 'success' | 'error'>>({});

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    dispatch({ type: 'SET_HISTORY_LOADING', payload: true });
    try {
      const items = await historyApi.list(0, 50);
      dispatch({ type: 'SET_HISTORY', payload: items });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load download history.');
      dispatch({ type: 'SET_HISTORY_LOADING', payload: false });
    } finally {
      setLoading(false);
    }
  }, [dispatch]);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const handleReDownload = async (item: HistoryItem) => {
    setActionState((previous) => ({ ...previous, [item.id]: 'loading' }));
    try {
      const added = await historyApi.reDownload({
        tidal_id: item.tidal_id,
        item_type: item.item_type,
        title: item.title,
        artist: item.artist,
        album: item.album || undefined,
        quality: item.quality,
        format: item.format,
      });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      setActionState((previous) => ({ ...previous, [item.id]: 'success' }));
      dispatch({ type: 'ADD_TOAST', payload: { id: `re-dl-${Date.now()}`, type: 'info', title: 'Re-added to queue', detail: item.title, dismissAt: Date.now() + 3000 } });
    } catch (actionError) {
      setActionState((previous) => ({ ...previous, [item.id]: 'error' }));
      dispatch({ type: 'ADD_TOAST', payload: { id: `re-dl-err-${Date.now()}`, type: 'error', title: 'Failed to re-download', detail: actionError instanceof Error ? actionError.message : item.title, dismissAt: Date.now() + 5000 } });
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <div className="flex items-end justify-between gap-4 mb-6">
        <div><h1 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>Download History</h1><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Previously saved tracks, ready to download again.</p></div>
        {!loading && !error && state.history.length > 0 && <span className="mono text-xs" style={{ color: 'var(--text-dim)' }}>{state.history.length} items</span>}
      </div>

      {loading ? (
        <div className="glass p-8 text-center" role="status" aria-live="polite"><span className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading download history…</span></div>
      ) : error ? (
        <div className="glass p-8 text-center" role="alert"><p className="text-sm" style={{ color: 'var(--text-bright)' }}>Could not load history.</p><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>{error}</p><button type="button" className="btn-primary text-xs mt-4" onClick={() => void loadHistory()}>Retry</button></div>
      ) : state.history.length === 0 ? (
        <div className="glass p-10 text-center" role="status"><p className="text-sm" style={{ color: 'var(--text-muted)' }}>No download history yet.</p><p className="text-xs mt-2" style={{ color: 'var(--text-dim)' }}>Completed downloads will appear here.</p></div>
      ) : (
        <ul className="space-y-3" aria-label="Download history">
          {state.history.map((item) => {
            const status = actionState[item.id];
            return (
              <li key={item.id} className="glass p-4 flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0 flex-1"><p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{item.title}</p><p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{[item.artist, item.album, item.quality, item.format].filter(Boolean).join(' · ')}</p><p className="text-xs mt-2" style={{ color: 'var(--text-dim)' }}>{formatSize(item.file_size)} · {new Date(item.downloaded_at).toLocaleDateString()}</p></div>
                <div className="flex items-center gap-3"><span className="text-xs" role={status === 'error' ? 'alert' : undefined} style={{ color: status === 'success' ? 'var(--success)' : status === 'error' ? 'var(--danger)' : 'var(--text-muted)' }}>{status === 'success' ? 'Added to queue' : status === 'error' ? 'Try again' : ''}</span><button type="button" className="btn-primary text-xs px-3 py-1.5" disabled={status === 'loading'} onClick={() => void handleReDownload(item)}>{status === 'loading' ? 'Adding…' : status === 'error' ? 'Retry re-download' : 'Re-download'}</button></div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
