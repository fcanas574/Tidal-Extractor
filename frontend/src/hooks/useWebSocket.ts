import { useEffect, useRef, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import type { WsMessage } from '../api';

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disposedRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const { dispatch } = useApp();

  const connect = useCallback(() => {
    if (disposedRef.current) return;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
      if (disposedRef.current || wsRef.current !== ws) return;
      dispatch({ type: 'SET_WS_CONNECTED', payload: true });
    };

    ws.onmessage = (event) => {
      if (disposedRef.current || wsRef.current !== ws) return;
      try {
        const msg: WsMessage = JSON.parse(event.data);
        onMessageRef.current(msg);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      if (disposedRef.current || wsRef.current !== ws) return;
      dispatch({ type: 'SET_WS_CONNECTED', payload: false });
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
      }
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        if (!disposedRef.current) connect();
      }, 3000);
    };

    ws.onerror = () => {
      if (disposedRef.current || wsRef.current !== ws) return;
      dispatch({ type: 'SET_WS_CONNECTED', payload: false });
    };

    wsRef.current = ws;
  }, [dispatch]);

  useEffect(() => {
    disposedRef.current = false;
    connect();
    return () => {
      disposedRef.current = true;
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [connect]);

  return wsRef;
}
