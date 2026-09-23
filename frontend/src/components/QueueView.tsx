import { useState } from 'react';
import { queue } from '../api';
import type { QueueItem } from '../api';
import { useApp } from '../context/AppContext';

const statusConfig: Record<QueueItem['status'], { label: string; color: string; background: string }> = {
  queued: { label: 'Queued', color: 'var(--text-muted)', background: 'var(--bg-surface)' },
  downloading: { label: 'Downloading', color: 'var(--accent-secondary)', background: 'rgba(155, 200, 255, 0.12)' },
  complete: { label: 'Complete', color: 'var(--success)', background: 'rgba(141, 231, 213, 0.12)' },
  failed: { label: 'Failed', color: 'var(--danger)', background: 'rgba(255, 129, 148, 0.12)' },
};

function itemDetails(item: QueueItem) {
  return [item.artist, item.album, item.quality, item.format].filter(Boolean).join(' · ');
}

export default function QueueView() {
  const { state, dispatch } = useApp();
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [clearAllConfirm, setClearAllConfirm] = useState(false);
  const [bulkConfirm, setBulkConfirm] = useState(false);
  const [completedCollapsed, setCompletedCollapsed] = useState(true);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [retryingIds, setRetryingIds] = useState<Set<number>>(new Set());

  const activeItems = state.queue
    .filter((item) => item.status === 'downloading' || item.status === 'queued')
    .sort((a, b) => Number(b.status === 'downloading') - Number(a.status === 'downloading'));
  const failedItems = state.queue.filter((item) => item.status === 'failed');
  const completedItems = state.queue.filter((item) => item.status === 'complete');
  const selectedItems = state.queue.filter((item) => selectedIds.has(item.id));
  const selectedActive = selectedItems.some((item) => item.status === 'downloading');
  const hasCompleted = completedItems.length > 0;

  const notifyError = (title: string, detail?: string) => {
    dispatch({
      type: 'ADD_TOAST',
      payload: { id: `${title}-${Date.now()}`, type: 'error', title, detail, dismissAt: Date.now() + 5000 },
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(selectedItems.length === state.queue.length
      ? new Set()
      : new Set(state.queue.map((item) => item.id)));
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
    setBulkConfirm(false);
  };

  const removeItem = async (item: QueueItem) => {
    try {
      await queue.remove(item.id);
      dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: item.id });
      setConfirmingId(null);
    } catch (error) {
      notifyError('Could not remove download', error instanceof Error ? error.message : item.title);
    }
  };

  const handleRetry = async (item: QueueItem) => {
    setRetryingIds((previous) => new Set(previous).add(item.id));
    try {
      const added = await queue.add({
        tidal_id: item.tidal_id,
        item_type: item.item_type,
        title: item.title,
        artist: item.artist,
        album: item.album,
        quality: item.quality,
        format: item.format,
      });
      dispatch({ type: 'UPDATE_QUEUE_ITEM', payload: added });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `retry-${item.id}-${Date.now()}`,
          type: 'info',
          title: 'Re-added to queue',
          detail: item.title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch (error) {
      notifyError('Could not retry download', error instanceof Error ? error.message : item.title);
    } finally {
      setRetryingIds((previous) => {
        const next = new Set(previous);
        next.delete(item.id);
        return next;
      });
    }
  };

  const handleRetryAllFailed = async () => {
    for (const item of failedItems) await handleRetry(item);
  };

  const handleClearCompleted = async () => {
    try {
      await queue.clearCompleted();
      dispatch({ type: 'SET_QUEUE', payload: state.queue.filter((item) => item.status !== 'complete') });
    } catch (error) {
      notifyError('Failed to clear completed', error instanceof Error ? error.message : undefined);
    }
  };

  const handleClearAll = async () => {
    if (!clearAllConfirm) {
      setClearAllConfirm(true);
      return;
    }
    try {
      await queue.clearAll();
      dispatch({ type: 'SET_QUEUE', payload: [] });
      setClearAllConfirm(false);
      exitSelectMode();
    } catch (error) {
      notifyError('Failed to clear queue', error instanceof Error ? error.message : undefined);
    }
  };

  const handleRemoveSelected = async () => {
    if (selectedActive && !bulkConfirm) {
      setBulkConfirm(true);
      return;
    }
    try {
      await queue.removeBatch(Array.from(selectedIds));
      dispatch({ type: 'SET_QUEUE', payload: state.queue.filter((item) => !selectedIds.has(item.id)) });
      exitSelectMode();
    } catch (error) {
      notifyError('Failed to remove selected', error instanceof Error ? error.message : undefined);
    }
  };

  const renderItem = (item: QueueItem, dimmed = false) => {
    const config = statusConfig[item.status];
    const active = item.status === 'queued' || item.status === 'downloading';
    const confirming = confirmingId === item.id;

    return (
      <li key={item.id} className={`queue-item${dimmed ? ' is-complete' : ''}`}>
        <div className="queue-item-header">
          <div className="queue-item-identity">
            {selectMode && (
              <input
                type="checkbox"
                aria-label={`Select ${item.title}`}
                checked={selectedIds.has(item.id)}
                onChange={() => toggleSelect(item.id)}
                style={{ accentColor: 'var(--accent-primary)' }}
                className="queue-item-checkbox"
              />
            )}
            <div className="queue-item-copy">
              <p className="queue-item-title" title={item.title}>{item.title}</p>
              <p className="queue-item-context" title={itemDetails(item)}>{itemDetails(item)}</p>
            </div>
          </div>

          <span className={`queue-item-status status-${item.status}`} style={{ color: config.color, background: config.background }}>
            {config.label}
          </span>
        </div>

        {item.status === 'downloading' && (
          <div className="queue-item-progress" aria-label={`${Math.round(item.progress)} percent downloaded`}>
            <div className="queue-item-progress-labels">
              <span>Downloading</span>
              <span className="mono">{Math.round(item.progress)}%</span>
            </div>
            <div className="progress-track queue-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(item.progress)} aria-label={`Download progress for ${item.title}`}>
              <div className="progress-fill active" style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} />
            </div>
          </div>
        )}

        {item.error && item.status === 'failed' && <p className="queue-item-error" role="alert">{item.error}</p>}

        {!selectMode && !confirming && (
          <div className="queue-item-actions">
            {item.status === 'failed' && (
              <button type="button" className="queue-item-action" onClick={() => handleRetry(item)} disabled={retryingIds.has(item.id)}>
                {retryingIds.has(item.id) ? 'Retrying…' : 'Retry'}
              </button>
            )}
            {item.status !== 'complete' && (
              <button
                type="button"
                className="queue-item-action is-danger"
                onClick={() => active && item.status === 'downloading' ? setConfirmingId(item.id) : removeItem(item)}
                aria-label={`${active && item.status === 'downloading' ? 'Cancel' : 'Remove'} ${item.title}`}
              >
                {item.status === 'downloading' ? 'Cancel' : 'Remove'}
              </button>
            )}
          </div>
        )}

        {confirming && (
          <div className="queue-item-confirmation" role="group" aria-label={`Cancel ${item.title}`}>
            <span>Cancel this download?</span>
            <div>
              <button type="button" className="btn-danger text-xs" onClick={() => removeItem(item)}>Cancel download</button>
              <button type="button" className="btn-ghost text-xs" onClick={() => setConfirmingId(null)}>Keep downloading</button>
            </div>
          </div>
        )}
      </li>
    );
  };

  const activeCount = activeItems.filter((item) => item.status === 'downloading').length;
  const queuedCount = activeItems.filter((item) => item.status === 'queued').length;

  return (
    <div className="queue-workspace animate-fade-in">
      <header className="queue-command">
        <h1 className="queue-page-title">Download queue</h1>
        {state.queue.length > 0 && (
          <div className="queue-command-actions">
            <button type="button" className="queue-toolbar-action" onClick={() => selectMode ? exitSelectMode() : setSelectMode(true)} aria-pressed={selectMode}>{selectMode ? 'Done selecting' : 'Select items'}</button>
            {failedItems.length > 0 && !selectMode && <button type="button" className="queue-toolbar-action" onClick={handleRetryAllFailed}>Retry failed</button>}
            {hasCompleted && !selectMode && <button type="button" className="queue-toolbar-action" onClick={handleClearCompleted}>Clear completed</button>}
            {!selectMode && <button type="button" className={`queue-toolbar-action${clearAllConfirm ? ' is-danger' : ''}`} onClick={handleClearAll}>{clearAllConfirm ? 'Confirm clear all' : 'Clear all'}</button>}
          </div>
        )}
        {state.queue.length > 0 && <div className="queue-summary" role="region" aria-label="Queue summary">
          <span className="queue-summary-item"><span className="mono">{activeCount}</span> downloading</span>
          <span className="queue-summary-item"><span className="mono">{queuedCount}</span> queued</span>
          <span className="queue-summary-item"><span className="mono">{failedItems.length}</span> failed</span>
          <span className="queue-summary-item"><span className="mono">{completedItems.length}</span> completed</span>
        </div>}
      </header>

      {selectMode && state.queue.length > 0 && (
        <div className="queue-bulk-toolbar" role="region" aria-label="Bulk queue actions">
          <label><input type="checkbox" aria-label="Select all queue items" checked={state.queue.length > 0 && selectedItems.length === state.queue.length} onChange={toggleSelectAll} style={{ accentColor: 'var(--accent-primary)' }} />Select all</label>
          <span>{selectedItems.length} selected</span>
          {selectedItems.length > 0 && (bulkConfirm ? (
            <div className="queue-bulk-confirmation" role="group" aria-label="Confirm selected cancellation"><span>Cancel active downloads too?</span><button type="button" className="queue-item-action is-danger" onClick={handleRemoveSelected}>Cancel selected</button><button type="button" className="queue-item-action" onClick={() => setBulkConfirm(false)}>Keep downloads</button></div>
          ) : <button type="button" className="queue-bulk-remove" onClick={handleRemoveSelected}>Remove selected</button>)}
        </div>
      )}

      <div className="queue-list-scroll">
        {state.queue.length === 0 ? (
          <div className="queue-empty" role="status">
            <p>Queue is empty.</p>
            <span>Tracks you add will appear here while they download.</span>
            <button type="button" className="queue-bulk-remove" onClick={() => dispatch({ type: 'SET_TAB', payload: 'search' })}>Go to Search</button>
          </div>
        ) : (
          <div className="queue-sections">
            {activeItems.length > 0 && (
              <section className="queue-section" aria-labelledby="queue-active-heading">
                <div className="queue-section-heading"><h2 id="queue-active-heading">Active</h2><span className="mono">{activeItems.length}</span></div>
                <ul className="queue-items">{activeItems.map((item) => renderItem(item))}</ul>
              </section>
            )}

            {failedItems.length > 0 && (
              <section className="queue-section" aria-labelledby="queue-attention-heading">
                <div className="queue-section-heading is-attention"><h2 id="queue-attention-heading">Needs attention</h2><span className="mono">{failedItems.length}</span></div>
                <ul className="queue-items">{failedItems.map((item) => renderItem(item))}</ul>
              </section>
            )}

            {hasCompleted && (
              <section className="queue-section queue-completed-section" aria-labelledby="queue-completed-heading">
                <button type="button" className="queue-completed-toggle" onClick={() => setCompletedCollapsed((collapsed) => !collapsed)} aria-expanded={!completedCollapsed} aria-controls="queue-completed-list">
                  <span><span id="queue-completed-heading">Completed</span><span className="mono">{completedItems.length}</span></span>
                  <span aria-hidden="true">{completedCollapsed ? '+' : '−'}</span>
                </button>
                {!completedCollapsed && <ul id="queue-completed-list" className="queue-items">{completedItems.map((item) => renderItem(item, true))}</ul>}
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
