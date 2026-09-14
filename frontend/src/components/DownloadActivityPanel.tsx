import { useEffect, useRef, useState } from 'react';
import { queue } from '../api';
import type { QueueItem } from '../api';
import { useApp } from '../context/AppContext';

type ActivityStatus = QueueItem['status'] | 'reconnecting' | 'stale';

const STALE_AFTER = 20_000;

const statusConfig: Record<ActivityStatus, { label: string; color: string; background: string }> = {
  queued: { label: 'Queued', color: 'var(--text-muted)', background: 'var(--bg-surface)' },
  downloading: { label: 'Downloading', color: 'var(--accent-secondary)', background: 'rgba(155, 200, 255, 0.12)' },
  reconnecting: { label: 'Reconnecting', color: 'var(--warning)', background: 'rgba(242, 197, 114, 0.12)' },
  stale: { label: 'Stale', color: 'var(--warning)', background: 'rgba(242, 197, 114, 0.12)' },
  complete: { label: 'Complete', color: 'var(--success)', background: 'rgba(141, 231, 213, 0.12)' },
  failed: { label: 'Failed', color: 'var(--danger)', background: 'rgba(255, 129, 148, 0.12)' },
};

function displayStatus(item: QueueItem, connected: boolean, now: number, lastProgressAt: number | null): ActivityStatus {
  if (item.status === 'downloading' && lastProgressAt !== null && now - lastProgressAt >= STALE_AFTER) {
    return 'stale';
  }
  if ((item.status === 'queued' || item.status === 'downloading') && !connected) {
    return 'reconnecting';
  }
  return item.status;
}

function itemDetails(item: QueueItem) {
  return [item.artist, item.album, item.format].filter(Boolean).join(' · ');
}

export default function DownloadActivityPanel() {
  const { state, dispatch } = useApp();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [completedCollapsed, setCompletedCollapsed] = useState(true);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);

  const activeItems = state.queue.filter((item) => item.status === 'queued' || item.status === 'downloading');
  const failedItems = state.queue.filter((item) => item.status === 'failed');
  const completedItems = state.queue.filter((item) => item.status === 'complete');
  const hasActiveWork = activeItems.length > 0;

  useEffect(() => {
    if (!state.activityPanelOpen) {
      if (!state.settingsPanelOpen) triggerRef.current?.focus();
      triggerRef.current = null;
      return;
    }
    const activeElement = document.activeElement;
    triggerRef.current = activeElement instanceof HTMLElement ? activeElement : null;
    closeButtonRef.current?.focus();
  }, [state.activityPanelOpen, state.settingsPanelOpen]);

  useEffect(() => {
    if (!state.activityPanelOpen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' });
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [dispatch, state.activityPanelOpen]);

  useEffect(() => {
    if (!hasActiveWork) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [hasActiveWork]);

  const addErrorToast = (title: string, detail?: string) => {
    dispatch({
      type: 'ADD_TOAST',
      payload: { id: `${title}-${Date.now()}`, type: 'error', title, detail, dismissAt: Date.now() + 5000 },
    });
  };

  const removeItem = async (item: QueueItem) => {
    try {
      await queue.remove(item.id);
      dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: item.id });
      setConfirmingId(null);
    } catch (error) {
      addErrorToast('Could not remove download', error instanceof Error ? error.message : item.title);
    }
  };

  const retryItem = async (item: QueueItem) => {
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
        payload: { id: `retry-${item.id}-${Date.now()}`, type: 'info', title: 'Re-added to queue', detail: item.title, dismissAt: Date.now() + 3000 },
      });
    } catch (error) {
      addErrorToast('Could not retry download', error instanceof Error ? error.message : item.title);
    }
  };

  if (!state.activityPanelOpen) return null;

  const renderItem = (item: QueueItem) => {
    const status = displayStatus(item, state.wsConnected, now, state.queueMeta[item.id]?.lastProgressAt ?? null);
    const config = statusConfig[status];
    const active = item.status === 'queued' || item.status === 'downloading';

    return (
      <li key={item.id} className="activity-item">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>{item.title}</p>
            <p className="text-xs truncate mt-1" style={{ color: 'var(--text-muted)' }}>{itemDetails(item)}</p>
          </div>
          <span
            className="shrink-0 text-[11px] px-2 py-1 rounded-md"
            style={{ color: config.color, background: config.background }}
          >
            {config.label}
          </span>
        </div>

        {item.status === 'downloading' && (
          <div className="mt-3" aria-label={`${Math.round(item.progress)} percent downloaded`}>
            <div className="flex justify-between text-[11px] mb-1">
              <span style={{ color: status === 'stale' ? 'var(--warning)' : 'var(--text-muted)' }}>
                {status === 'stale' ? 'No progress observed for 20 seconds' : 'Downloading'}
              </span>
              <span className="mono" style={{ color: 'var(--text-primary)' }}>{Math.round(item.progress)}%</span>
            </div>
            <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(item.progress)}>
              <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} />
            </div>
          </div>
        )}

        {item.error && item.status === 'failed' && (
          <p className="text-xs mt-2" style={{ color: 'var(--danger)' }}>{item.error}</p>
        )}

        <div className="flex justify-end gap-2 mt-3">
          {item.status === 'failed' && (
            <button type="button" className="activity-action" onClick={() => retryItem(item)}>Retry</button>
          )}
          {item.status === 'complete' && (
            <button type="button" className="activity-action" onClick={() => removeItem(item)}>Remove</button>
          )}
          {active && confirmingId !== item.id && (
            <button
              type="button"
              className="activity-action activity-action-danger"
              onClick={() => item.status === 'queued' ? removeItem(item) : setConfirmingId(item.id)}
              aria-label={`Cancel ${item.title}`}
            >
              {item.status === 'queued' ? 'Remove' : 'Cancel'}
            </button>
          )}
        </div>

        {active && confirmingId === item.id && (
          <div className="activity-confirmation" role="group" aria-label={`Cancel ${item.title}`}>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Cancel this download?</span>
            <div className="flex gap-2">
              <button type="button" className="activity-action activity-action-danger" onClick={() => removeItem(item)}>Cancel download</button>
              <button type="button" className="activity-action" onClick={() => setConfirmingId(null)}>Keep downloading</button>
            </div>
          </div>
        )}
      </li>
    );
  };

  return (
    <>
      <button
        type="button"
        className="activity-backdrop"
        aria-label="Close download activity"
        onClick={() => dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' })}
      />
      <aside
        id="download-activity-panel"
        className="activity-panel"
        role="dialog"
        aria-modal="false"
        aria-labelledby="download-activity-title"
        aria-live="polite"
      >
        <div className="flex items-center justify-between gap-4 px-5 py-4">
          <div>
            <h2 id="download-activity-title" className="text-sm font-semibold" style={{ color: 'var(--text-bright)' }}>Download activity</h2>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              {activeItems.length} active · {failedItems.length} failed
            </p>
          </div>
          <button ref={closeButtonRef} type="button" className="activity-close" onClick={() => dispatch({ type: 'TOGGLE_ACTIVITY_PANEL' })} aria-label="Close download activity">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m4 4 8 8M12 4 4 12" /></svg>
          </button>
        </div>

        <div className="activity-panel-body">
          {state.queue.length === 0 && <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>No downloads yet.</p>}

          {activeItems.length > 0 && (
            <section aria-labelledby="activity-active-title">
              <h3 id="activity-active-title" className="activity-section-title">In progress</h3>
              <ul className="space-y-2">{activeItems.map(renderItem)}</ul>
            </section>
          )}

          {failedItems.length > 0 && (
            <section className="mt-5" aria-labelledby="activity-failed-title">
              <h3 id="activity-failed-title" className="activity-section-title">Needs attention</h3>
              <ul className="space-y-2">{failedItems.map(renderItem)}</ul>
            </section>
          )}

          {completedItems.length > 0 && (
            <section className="mt-5" aria-labelledby="activity-completed-title">
              <button type="button" className="activity-section-toggle" onClick={() => setCompletedCollapsed((collapsed) => !collapsed)} aria-expanded={!completedCollapsed}>
                <span id="activity-completed-title" className="activity-section-title">Completed ({completedItems.length})</span>
                <span aria-hidden="true">{completedCollapsed ? '+' : '−'}</span>
              </button>
              {!completedCollapsed && <ul className="space-y-2 mt-2">{completedItems.map(renderItem)}</ul>}
            </section>
          )}
        </div>
      </aside>
    </>
  );
}
