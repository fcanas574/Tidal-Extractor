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
      <li key={item.id} className="glass p-4" style={{ opacity: dimmed ? 0.72 : 1 }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            {selectMode && (
              <input
                type="checkbox"
                aria-label={`Select ${item.title}`}
                checked={selectedIds.has(item.id)}
                onChange={() => toggleSelect(item.id)}
                style={{ accentColor: 'var(--accent-primary)' }}
                className="mt-1 shrink-0"
              />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate" style={{ color: dimmed ? 'var(--text-muted)' : 'var(--text-bright)' }}>{item.title}</p>
              <p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{itemDetails(item)}</p>
            </div>
          </div>

          <span className="shrink-0 text-[11px] px-2 py-1 rounded-md" style={{ color: config.color, background: config.background }}>
            {config.label}
          </span>
        </div>

        {item.status === 'downloading' && (
          <div className="mt-4" aria-label={`${Math.round(item.progress)} percent downloaded`}>
            <div className="flex justify-between text-[11px] mb-1">
              <span style={{ color: 'var(--text-muted)' }}>Downloading</span>
              <span className="mono" style={{ color: 'var(--text-primary)' }}>{Math.round(item.progress)}%</span>
            </div>
            <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(item.progress)} aria-label={`Download progress for ${item.title}`}>
              <div className="progress-fill active" style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} />
            </div>
          </div>
        )}

        {item.error && item.status === 'failed' && <p className="text-xs mt-3" role="alert" style={{ color: 'var(--danger)' }}>{item.error}</p>}

        {!selectMode && !confirming && (
          <div className="flex justify-end gap-2 mt-3">
            {item.status === 'failed' && (
              <button type="button" className="btn-ghost text-xs" onClick={() => handleRetry(item)} disabled={retryingIds.has(item.id)}>
                {retryingIds.has(item.id) ? 'Retrying…' : 'Retry'}
              </button>
            )}
            {item.status !== 'complete' && (
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => active && item.status === 'downloading' ? setConfirmingId(item.id) : removeItem(item)}
                style={{ color: 'var(--danger)' }}
                aria-label={`${active && item.status === 'downloading' ? 'Cancel' : 'Remove'} ${item.title}`}
              >
                {item.status === 'downloading' ? 'Cancel' : 'Remove'}
              </button>
            )}
          </div>
        )}

        {confirming && (
          <div className="mt-3 p-3 flex flex-wrap items-center justify-between gap-3" role="group" aria-label={`Cancel ${item.title}`} style={{ background: 'rgba(255, 129, 148, 0.08)', border: '1px solid rgba(255, 129, 148, 0.25)', borderRadius: 'var(--radius-sm)' }}>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Cancel this download?</span>
            <div className="flex gap-2">
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
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div>
          <h1 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>Download Queue</h1>
          {state.queue.length > 0 && <p className="text-xs mt-1" style={{ color: 'var(--text-dim)' }}>{activeCount} active · {queuedCount} queued · {failedItems.length} need attention · {completedItems.length} completed</p>}
        </div>

        {state.queue.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn-ghost text-xs" onClick={() => selectMode ? exitSelectMode() : setSelectMode(true)} aria-pressed={selectMode}>{selectMode ? 'Done selecting' : 'Select items'}</button>
            {failedItems.length > 0 && !selectMode && <button type="button" className="btn-ghost text-xs" onClick={handleRetryAllFailed}>Retry failed</button>}
            {hasCompleted && !selectMode && <button type="button" className="btn-ghost text-xs" onClick={handleClearCompleted}>Clear completed</button>}
            {!selectMode && <button type="button" className="btn-ghost text-xs" onClick={handleClearAll} style={{ color: clearAllConfirm ? 'var(--danger)' : 'var(--text-muted)' }}>{clearAllConfirm ? 'Confirm clear all' : 'Clear all'}</button>}
          </div>
        )}
      </div>

      {state.queue.length === 0 ? (
        <div className="text-center py-24" role="status">
          <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center" style={{ background: 'var(--bg-mid)', border: '1px solid var(--glass-border)' }} aria-hidden="true"><span className="text-2xl" style={{ color: 'var(--text-dim)' }}>↓</span></div>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>Queue is empty. Search and add tracks to download.</p>
        </div>
      ) : (
        <div className="space-y-7">
          {activeItems.length > 0 && (
            <section aria-labelledby="queue-active-heading">
              <div className="flex items-baseline justify-between mb-3"><h2 id="queue-active-heading" className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-bright)' }}>Active</h2><span className="mono text-[11px]" style={{ color: 'var(--text-muted)' }}>{activeItems.length}</span></div>
              <ul className="space-y-3">{activeItems.map((item) => renderItem(item))}</ul>
            </section>
          )}

          {failedItems.length > 0 && (
            <section aria-labelledby="queue-attention-heading">
              <div className="flex items-baseline justify-between mb-3"><h2 id="queue-attention-heading" className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--danger)' }}>Needs attention</h2><span className="mono text-[11px]" style={{ color: 'var(--text-muted)' }}>{failedItems.length}</span></div>
              <ul className="space-y-3">{failedItems.map((item) => renderItem(item))}</ul>
            </section>
          )}

          {hasCompleted && (
            <section aria-labelledby="queue-completed-heading">
              <button type="button" className="w-full flex items-center justify-between py-2" onClick={() => setCompletedCollapsed((collapsed) => !collapsed)} aria-expanded={!completedCollapsed} aria-controls="queue-completed-list">
                <span className="flex items-center gap-2"><span id="queue-completed-heading" className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Completed</span><span className="mono text-[11px]" style={{ color: 'var(--text-dim)' }}>({completedItems.length})</span></span>
                <span aria-hidden="true" style={{ color: 'var(--text-dim)' }}>{completedCollapsed ? '+' : '−'}</span>
              </button>
              {!completedCollapsed && <ul id="queue-completed-list" className="space-y-3 mt-2">{completedItems.map((item) => renderItem(item, true))}</ul>}
            </section>
          )}
        </div>
      )}

      {selectMode && (
        <div className="mt-6 p-3 flex flex-wrap items-center justify-between gap-3" role="region" aria-label="Bulk queue actions" style={{ background: 'rgba(141, 231, 213, 0.06)', border: '1px solid rgba(141, 231, 213, 0.18)', borderRadius: 'var(--radius)' }}>
          <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}><input type="checkbox" aria-label="Select all queue items" checked={state.queue.length > 0 && selectedItems.length === state.queue.length} onChange={toggleSelectAll} style={{ accentColor: 'var(--accent-primary)' }} />Select all</label>
          <span className="text-xs" style={{ color: 'var(--text-primary)' }}>{selectedItems.length} selected</span>
          {selectedItems.length > 0 && (bulkConfirm ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Confirm selected cancellation"><span className="text-xs" style={{ color: 'var(--text-muted)' }}>Cancel active downloads too?</span><button type="button" className="btn-danger text-xs" onClick={handleRemoveSelected}>Cancel selected</button><button type="button" className="btn-ghost text-xs" onClick={() => setBulkConfirm(false)}>Keep downloads</button></div>
          ) : <button type="button" className="btn-primary text-xs px-3 py-1.5" onClick={handleRemoveSelected}>Remove selected</button>)}
        </div>
      )}
    </div>
  );
}
