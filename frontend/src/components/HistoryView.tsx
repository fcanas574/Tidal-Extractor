import { useCallback, useEffect, useRef, useState } from 'react';
import { history as historyApi } from '../api';
import type { HistoryItem } from '../api';
import { useApp } from '../context/AppContext';
import WorkspaceInspector from './WorkspaceInspector';

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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const detailTitleRef = useRef<HTMLHeadingElement>(null);
  const detailTriggerRefs = useRef(new Map<number, HTMLButtonElement>());

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

  const selectedItem = state.history.find((item) => item.id === selectedId) ?? null;

  useEffect(() => {
    if (!selectedItem) return undefined;
    const frame = window.requestAnimationFrame(() => detailTitleRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [selectedId, selectedItem]);

  const closeInspector = () => {
    const previousId = selectedId;
    setSelectedId(null);
    if (previousId !== null) {
      window.requestAnimationFrame(() => detailTriggerRefs.current.get(previousId)?.focus());
    }
  };

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

  const renderReDownloadButton = (item: HistoryItem) => {
    const status = actionState[item.id];
    return (
      <div className="history-row-action">
        <span
          className="history-action-status"
          role={status === 'error' ? 'alert' : status === 'success' ? 'status' : undefined}
        >
          {status === 'success' ? 'Added to queue' : status === 'error' ? 'Try again' : ''}
        </span>
        <button
          type="button"
          className="history-download-button"
          disabled={status === 'loading'}
          onClick={() => void handleReDownload(item)}
        >
          {status === 'loading' ? 'Adding…' : status === 'error' ? 'Retry re-download' : 'Re-download'}
        </button>
      </div>
    );
  };

  const historyList = (
    <ul className="history-items" aria-label="Download history">
      {state.history.map((item) => {
        const isSelected = selectedItem?.id === item.id;
        const context = [item.artist, item.album, item.quality, item.format].filter(Boolean).join(' · ');
        const status = actionState[item.id];
        return (
          <li key={item.id} className={`history-item${isSelected ? ' is-selected' : ''}`}>
            <div className="history-item-main">
              <button
                ref={(node) => {
                  if (node) detailTriggerRefs.current.set(item.id, node);
                  else detailTriggerRefs.current.delete(item.id);
                }}
                type="button"
                className="history-item-details"
                aria-label={`Details for ${item.title}`}
                aria-pressed={isSelected}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="history-item-title" title={item.title}>{item.title}</span>
                {context && <span className="history-item-context" title={context}>{context}</span>}
                <span className="history-item-date">{formatSize(item.file_size)} · {new Date(item.downloaded_at).toLocaleDateString()}</span>
              </button>
              {isSelected ? (
                <span className="history-action-status" role={status === 'error' ? 'alert' : status === 'success' ? 'status' : undefined}>
                  {status === 'success' ? 'Added to queue' : status === 'error' ? 'Try again' : ''}
                </span>
              ) : renderReDownloadButton(item)}
            </div>
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className="history-workspace animate-fade-in">
      <header className="history-command">
        <div><h1 className="history-page-title">History</h1><p className="history-page-subtitle">Your saved files, ready to add again.</p></div>
        {!loading && !error && state.history.length > 0 && <span className="history-count mono">{state.history.length} items</span>}
      </header>

      <div className={`history-workspace-body${selectedItem ? ' has-inspector' : ''}`}>
        <section className="history-results-column" aria-label="History items">
          {loading ? (
            <div className="history-state" role="status" aria-live="polite">Loading download history…</div>
          ) : error ? (
            <div className="history-state is-error" role="alert">
              <p>Could not load history.</p><p>{error}</p>
              <button type="button" className="history-download-button" onClick={() => void loadHistory()}>Retry</button>
            </div>
          ) : state.history.length === 0 ? (
            <div className="history-state" role="status"><p>No download history yet.</p><span>Completed downloads will appear here.</span></div>
          ) : historyList}
        </section>

        {selectedItem && (
          <WorkspaceInspector
            label="History"
            title={selectedItem.title}
            eyebrow="Download history"
            returnLabel="← Back to history"
            onClose={closeInspector}
          >
            <div className="history-inspector-content">
              <h2 ref={detailTitleRef} id="history-inspector-title" className="history-inspector-track-title" tabIndex={-1}>{selectedItem.title}</h2>
              {selectedItem.artist && <p className="history-inspector-artist">{selectedItem.artist}</p>}
              <dl className="history-metadata">
                {selectedItem.album && <div><dt>Album</dt><dd>{selectedItem.album}</dd></div>}
                {selectedItem.quality && <div><dt>Quality</dt><dd>{selectedItem.quality}</dd></div>}
                {selectedItem.format && <div><dt>Format</dt><dd>{selectedItem.format}</dd></div>}
                <div><dt>File size</dt><dd>{formatSize(selectedItem.file_size)}</dd></div>
                {selectedItem.downloaded_at && <div><dt>Downloaded</dt><dd>{new Date(selectedItem.downloaded_at).toLocaleDateString()}</dd></div>}
              </dl>
              {renderReDownloadButton(selectedItem)}
            </div>
          </WorkspaceInspector>
        )}
      </div>
    </div>
  );
}
