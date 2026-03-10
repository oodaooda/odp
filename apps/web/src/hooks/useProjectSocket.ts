import { useEffect, useRef, useCallback, useState } from "react";

export interface ProjectEvent {
  type?: string;
  event_type?: string;
  [key: string]: unknown;
}

type Listener = (evt: ProjectEvent) => void;

/**
 * Project-level WebSocket — subscribes to ALL task events for a project.
 * Maintains a set of listeners so multiple components can react to events.
 * Falls back gracefully when no tasks have WebSocket channels yet.
 */
export function useProjectSocket(projectId: string | undefined) {
  const [connected, setConnected] = useState(false);
  const listenersRef = useRef<Set<Listener>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const subscribe = useCallback((fn: Listener) => {
    listenersRef.current.add(fn);
    return () => {
      listenersRef.current.delete(fn);
    };
  }, []);

  const connect = useCallback(() => {
    if (!projectId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = import.meta.env.VITE_API_URL
      ? new URL(import.meta.env.VITE_API_URL).host
      : window.location.host;
    // Project-level WebSocket endpoint — broadcasts all task events.
    // Pass auth token as query param since WS doesn't support custom headers natively.
    const token = localStorage.getItem("odp_token");
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = `${protocol}//${host}/ws/projects/${projectId}${qs}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        listenersRef.current.forEach((fn) => fn(data));
      } catch {
        /* ignore non-json */
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      const delay = Math.min(1000 * 2 ** retriesRef.current, 15000);
      retriesRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [projectId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, subscribe };
}
