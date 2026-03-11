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
  fallbackMs = 30_000,
  onEvent?: (type: string, data: Record<string, unknown>) => void
) {
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    if (!projectId || !taskId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = import.meta.env.VITE_API_URL
      ? new URL(import.meta.env.VITE_API_URL).host
      : window.location.host;
    const token = localStorage.getItem("odp_token");
    const params = new URLSearchParams({ since: "0" });
    if (token) params.set("token", token);
    const url = `${protocol}//${host}/ws/projects/${projectId}/tasks/${taskId}?${params}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        const evtType = parsed.event_type ?? parsed.type ?? "";
        // For token updates, call handler directly without full refresh.
        if (evtType === "token_update" && onEventRef.current) {
          onEventRef.current(evtType, parsed);
          return;
        }
        if (evtType === "chat_message" && onEventRef.current) {
          onEventRef.current(evtType, parsed);
          return;
        }
      } catch { /* ignore parse errors */ }
      // Everything else triggers a refresh.
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
