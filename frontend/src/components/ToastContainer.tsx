import { useEffect, useCallback, useRef } from 'react';
import { useApp } from '../context/AppContext';

function ToastItem({ toast, onDismiss }: { toast: any; onDismiss: (id: string) => void }) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (toast.dismissAt) {
      const delay = toast.dismissAt - Date.now();
      if (delay > 0) {
        timerRef.current = setTimeout(() => onDismiss(toast.id), delay);
      } else {
        onDismiss(toast.id);
      }
    }
    return () => clearTimeout(timerRef.current);
  }, [toast.id, toast.dismissAt, onDismiss]);

  const iconMap: Record<string, string> = {
    success: '✓',
    error: '✕',
    downloading: '↓',
    info: '●',
  };

  const colorMap: Record<string, { border: string; icon: string; glow: string }> = {
    success: { border: 'rgba(0, 229, 199, 0.3)', icon: 'var(--accent-primary)', glow: 'rgba(0, 229, 199, 0.15)' },
    error: { border: 'rgba(255, 64, 96, 0.3)', icon: 'var(--danger)', glow: 'rgba(255, 64, 96, 0.15)' },
    downloading: { border: 'rgba(0, 184, 212, 0.3)', icon: 'var(--accent-secondary)', glow: 'rgba(0, 184, 212, 0.15)' },
    info: { border: 'var(--glass-border)', icon: 'var(--text-muted)', glow: 'transparent' },
  };

  const colors = colorMap[toast.type] || colorMap.info;
  const icon = iconMap[toast.type] || '●';

  return (
    <div
      className="animate-toast-in mb-2"
      style={{
        background: 'var(--bg-mid)',
        border: `1px solid ${colors.border}`,
        borderRadius: 'var(--radius-sm)',
        boxShadow: `0 8px 32px rgba(0, 0, 0, 0.4), 0 0 24px ${colors.glow}`,
        minWidth: '280px',
        maxWidth: '360px',
      }}
    >
      <div className="p-3 flex items-start gap-3">
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold shrink-0 mt-0.5"
          style={{ background: colors.glow, color: colors.icon }}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
            {toast.title}
          </p>
          {toast.detail && (
            <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
              {toast.detail}
            </p>
          )}
          {toast.type === 'downloading' && toast.progress !== undefined && (
            <div className="progress-track mt-2">
              <div
                className="progress-fill active"
                style={{ width: `${toast.progress}%` }}
              />
            </div>
          )}
        </div>
        {!toast.dismissAt && toast.type !== 'downloading' && (
          <button
            onClick={() => onDismiss(toast.id)}
            className="shrink-0 p-0.5 rounded transition-colors"
            style={{ color: 'var(--text-dim)' }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l6 6M9 3l-6 6"/>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

export default function ToastContainer() {
  const { state, dispatch } = useApp();

  const handleDismiss = useCallback(
    (id: string) => {
      dispatch({ type: 'REMOVE_TOAST', payload: id });
    },
    [dispatch]
  );

  if (state.toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col items-end">
      {state.toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={handleDismiss} />
      ))}
    </div>
  );
}
