import { useEffect, useRef, useCallback, useState } from "react";

/**
 * Combines WebSocket-driven instant refresh with a slow polling fallback.
 *
 * When a WS event arrives, the refresh callback fires immediately.
 * The polling fallback runs every `fallbackMs` (default 30s) in case the
 * WebSocket is disconnected or the server doesn't publish to the channel.
 */
export function useLiveRefresh(
  projectId: string | undefined,
  taskId: string | undefined,
  refresh: () => Promise<void> | void,
  fallbackMs = 30_000
) {
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  const connect = useCallback(() => {
    if (!projectId || !taskId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = import.meta.env.VITE_API_URL
      ? new URL(import.meta.env.VITE_API_URL).host
      : window.location.host;
    const url = `${protocol}//${host}/ws/projects/${projectId}/tasks/${taskId}?since=0`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = () => {
      // Any WS message = something changed, refresh immediately
      refreshRef.current();
    };

    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;
      const delay = Math.min(1000 * 2 ** retriesRef.current, 15000);
      retriesRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [projectId, taskId]);

  // WebSocket connection
  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // Slow polling fallback
  useEffect(() => {
    const interval = setInterval(() => {
      refreshRef.current();
    }, fallbackMs);
    return () => clearInterval(interval);
  }, [fallbackMs]);

  return { wsConnected };
}

/**
 * Simplified version for pages that don't have a specific task to subscribe to.
 * Uses only polling (configurable interval) since the WebSocket endpoint
 * requires a task_id.
 */
export function usePollingRefresh(
  refresh: () => Promise<void> | void,
  intervalMs = 5000
) {
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    const interval = setInterval(() => {
      refreshRef.current();
    }, intervalMs);
    return () => clearInterval(interval);
  }, [intervalMs]);
}
