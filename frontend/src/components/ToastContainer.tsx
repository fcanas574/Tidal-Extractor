import { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import type { Toast } from '../context/AppContext';

const EXIT_DURATION = 180;

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  const [exiting, setExiting] = useState(false);
  const pausedRef = useRef(false);
  const remainingRef = useRef<number | null>(toast.dismissAt ? Math.max(0, toast.dismissAt - Date.now()) : null);
  const startedAtRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const beginExit = useCallback(() => {
    if (exiting) return;
    setExiting(true);
    exitTimerRef.current = setTimeout(() => onDismiss(toast.id), EXIT_DURATION);
  }, [exiting, onDismiss, toast.id]);

  const scheduleDismiss = useCallback(() => {
    if (pausedRef.current || remainingRef.current === null || exiting) return;
    if (remainingRef.current <= 0) {
      beginExit();
      return;
    }
    startedAtRef.current = Date.now();
    timerRef.current = setTimeout(beginExit, remainingRef.current);
  }, [beginExit, exiting]);

  useEffect(() => {
    remainingRef.current = toast.dismissAt ? Math.max(0, toast.dismissAt - Date.now()) : null;
    scheduleDismiss();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
    };
  }, [toast.id, toast.dismissAt]);

  const pauseDismiss = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (remainingRef.current !== null && startedAtRef.current) {
      remainingRef.current = Math.max(0, remainingRef.current - (Date.now() - startedAtRef.current));
    }
    startedAtRef.current = 0;
    pausedRef.current = true;
  };

  const resumeDismiss = () => {
    pausedRef.current = false;
    scheduleDismiss();
  };

  const colors = toast.type === 'error'
    ? { border: 'rgba(255, 129, 148, 0.45)', icon: 'var(--danger)', background: 'rgba(255, 129, 148, 0.12)', glyph: '!' }
    : toast.type === 'success'
      ? { border: 'rgba(141, 231, 213, 0.35)', icon: 'var(--success)', background: 'rgba(141, 231, 213, 0.12)', glyph: '✓' }
      : { border: 'rgba(155, 200, 255, 0.3)', icon: 'var(--info)', background: 'rgba(155, 200, 255, 0.12)', glyph: '·' };

  return (
    <div
      className={`${exiting ? 'animate-toast-out' : 'animate-toast-in'} mb-2 toast-item`}
      role={toast.type === 'error' ? 'alert' : 'status'}
      onPointerEnter={pauseDismiss}
      onPointerLeave={resumeDismiss}
      onMouseEnter={pauseDismiss}
      onMouseLeave={resumeDismiss}
      onFocus={pauseDismiss}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) resumeDismiss();
      }}
      style={{
        background: 'var(--graphite)',
        border: `1px solid ${colors.border}`,
        borderRadius: 'var(--radius-sm)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
        minWidth: '280px',
        maxWidth: '360px',
      }}
    >
      <div className="p-3 flex items-start gap-3">
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold shrink-0 mt-0.5"
          aria-hidden="true"
          style={{ background: colors.background, color: colors.icon }}
        >
          {colors.glyph}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium" style={{ color: 'var(--text-bright)' }}>{toast.title}</p>
          {toast.detail && <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{toast.detail}</p>}
        </div>
        <button
          type="button"
          onClick={() => beginExit()}
          className="shrink-0 p-1 rounded transition-colors"
          style={{ color: 'var(--text-muted)' }}
          aria-label={`Dismiss ${toast.title}`}
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="m3 3 7 7M10 3 3 10" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export default function ToastContainer() {
  const { state, dispatch } = useApp();
  const handleDismiss = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_TOAST', payload: id });
  }, [dispatch]);

  // Progress is represented by the activity panel. Legacy progress toasts are
  // ignored here so the two surfaces cannot drift apart.
  const candidates = state.toasts.filter((toast) => toast.type !== 'downloading');
  const visibleToasts = candidates
    .map((toast, index) => ({ toast, index }))
    .sort((a, b) => Number(b.toast.type === 'error') - Number(a.toast.type === 'error') || b.index - a.index)
    .slice(0, 3)
    .map(({ toast }) => toast);

  if (visibleToasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col items-end" aria-label="Notifications">
      {visibleToasts.map((toast) => <ToastItem key={toast.id} toast={toast} onDismiss={handleDismiss} />)}
    </div>
  );
}
