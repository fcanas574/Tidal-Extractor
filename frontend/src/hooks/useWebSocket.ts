import { useEffect, useRef, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import type { WsMessage } from '../api';

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const { dispatch } = useApp();

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
      dispatch({ type: 'SET_WS_CONNECTED', payload: true });
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        onMessageRef.current(msg);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      dispatch({ type: 'SET_WS_CONNECTED', payload: false });
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      dispatch({ type: 'SET_WS_CONNECTED', payload: false });
    };

    wsRef.current = ws;
  }, [dispatch]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef;
}
