/**
 * useWebSocket — 帶自動重連的 WebSocket Hook
 */
import { useState, useEffect, useCallback, useRef } from 'react';

interface Options {
  url?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (event: MessageEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

interface Return {
  isConnected: boolean;
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'failed';
  sendMessage: (data: unknown) => void;
  connect: () => void;
  disconnect: () => void;
}

export function useWebSocket(options: Options = {}): Return {
  const wsBase = import.meta.env.VITE_WS_URL
    || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
  const {
    url = `${wsBase}/ws/gps`,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    onMessage,
    onConnect,
    onDisconnect,
  } = options;

  const cbRef = useRef({ onMessage, onConnect, onDisconnect });
  useEffect(() => { cbRef.current = { onMessage, onConnect, onDisconnect }; });

  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<Return['connectionStatus']>('disconnected');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number>(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (reconnectRef.current >= maxReconnectAttempts) {
      setConnectionStatus('failed');
      return;
    }

    setConnectionStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectRef.current = 0;
      setIsConnected(true);
      setConnectionStatus('connected');
      cbRef.current.onConnect?.();
    };

    ws.onmessage = (e) => cbRef.current.onMessage?.(e);

    ws.onclose = () => {
      setIsConnected(false);
      setConnectionStatus('disconnected');
      cbRef.current.onDisconnect?.();
      if (mountedRef.current) {
        reconnectRef.current += 1;
        retryTimerRef.current = setTimeout(connect, reconnectInterval);
      }
    };

    ws.onerror = () => { ws.close(); };
  }, [url, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    mountedRef.current = false;
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => { disconnect(); };
  }, [connect, disconnect]);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  return { isConnected, connectionStatus, sendMessage, connect, disconnect };
}
