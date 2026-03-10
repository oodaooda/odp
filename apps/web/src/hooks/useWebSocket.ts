import { useEffect, useRef, useCallback, useState } from "react";

export interface WsEvent {
  [key: string]: unknown;
}

/**
 * Live WebSocket hook — connects to the orchestrator event stream.
 * Automatically reconnects on disconnect with exponential backoff.
 */
export function useTaskWebSocket(
  projectId: string | undefined,
  taskId: string | undefined,
  onEvent?: (evt: WsEvent) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

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
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        setEvents((prev) => [...prev, data]);
        onEvent?.(data);
      } catch {
        /* ignore non-json frames */
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Reconnect with backoff (max 10s)
      const delay = Math.min(1000 * 2 ** retriesRef.current, 10000);
      retriesRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [projectId, taskId, onEvent]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, events, ws: wsRef };
}
