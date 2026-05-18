import { useEffect } from 'react';
import { queue } from '../api';
import { useApp } from '../context/AppContext';

const statusConfig: Record<string, { label: string; color: string; bg: string; dot: string }> = {
  queued: { label: 'Queued', color: 'var(--text-muted)', bg: 'var(--bg-surface)', dot: 'var(--text-dim)' },
  downloading: { label: 'Downloading', color: 'var(--accent-secondary)', bg: 'rgba(0, 184, 212, 0.1)', dot: 'var(--accent-secondary)' },
  complete: { label: 'Complete', color: 'var(--accent-primary)', bg: 'rgba(0, 229, 199, 0.1)', dot: 'var(--accent-primary)' },
  failed: { label: 'Failed', color: 'var(--danger)', bg: 'rgba(255, 64, 96, 0.1)', dot: 'var(--danger)' },
};

export default function QueueView() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
  }, [dispatch]);

  const handleRemove = async (id: number) => {
    await queue.remove(id);
    dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: id });
  };

  const activeCount = state.queue.filter((i) => i.status === 'downloading').length;
  const completedCount = state.queue.filter((i) => i.status === 'complete').length;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>
            Download Queue
          </h2>
          {state.queue.length > 0 && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-dim)' }}>
              {activeCount > 0 && `${activeCount} active`}
              {activeCount > 0 && completedCount > 0 && ' · '}
              {completedCount > 0 && `${completedCount} complete`}
              {!activeCount && !completedCount && `${state.queue.length} items`}
            </p>
          )}
        </div>
      </div>

      {state.queue.length === 0 ? (
        <div className="text-center py-24">
          <div
            className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'var(--bg-mid)', border: '1px solid var(--glass-border)' }}
          >
            <span className="text-2xl" style={{ color: 'var(--text-dim)' }}>↓</span>
          </div>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Queue is empty. Search and add tracks to download.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {state.queue.map((item) => {
            const cfg = statusConfig[item.status] || statusConfig.queued;
            return (
              <div key={item.id} className="glass p-4">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {item.title}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {item.artist}
                      {item.album && ` · ${item.album}`}
                      {' · '}
                      <span className="mono" style={{ color: 'var(--text-dim)' }}>{item.quality}</span>
                      {' · '}
                      <span className="mono" style={{ color: 'var(--text-dim)' }}>{item.format}</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    <span
                      className="flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-md"
                      style={{ background: cfg.bg, color: cfg.color }}
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{
                          background: cfg.dot,
                          boxShadow: item.status === 'downloading' ? `0 0 6px ${cfg.dot}` : 'none',
                          animation: item.status === 'downloading' ? 'pulse-glow 1.5s ease-in-out infinite' : 'none',
                        }}
                      />
                      {cfg.label}
                    </span>
                    <button
                      onClick={() => handleRemove(item.id)}
                      className="text-xs transition-colors"
                      style={{ color: 'var(--text-dim)' }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--danger)')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-dim)')}
                    >
                      Cancel
                    </button>
                  </div>
                </div>

                {/* Progress bar for active downloads */}
                {item.status === 'downloading' && (
                  <div className="progress-track mt-3">
                    <div
                      className="progress-fill active"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                )}

                {/* Error message */}
                {item.status === 'failed' && item.error && (
                  <p className="text-xs mt-2" style={{ color: 'var(--danger)' }}>{item.error}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
