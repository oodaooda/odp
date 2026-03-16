import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { listMemoryEvents } from "../api/client";
import { usePollingRefresh } from "../hooks/useLiveRefresh";
import type { MemoryEvent } from "../api/types";
import { formatTime } from "../utils/date";

export default function AuditLog() {
  const { projectId } = useParams<{ projectId: string }>();
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const e = await listMemoryEvents(projectId, undefined, 500).catch(() => ({
      events: [],
    }));
    setEvents(e.events ?? []);
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  usePollingRefresh(refresh, 5000);

  return (
    <>
      <div className="page-header">
        <h2>Audit Log</h2>
      </div>

      <div className="card">
        {loading ? (
          <div className="loading-center"><div className="spinner" /></div>
        ) : events.length === 0 ? (
          <p className="text-muted">No events recorded yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Detail</th>
                <th>Task</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td className="mono">
                    {formatTime(e.created_at)}
                  </td>
                  <td>
                    <span
                      className={`status status-${typeColor(e.event_type)}`}
                    >
                      {(e.event_type ?? "unknown").toUpperCase()}
                    </span>
                  </td>
                  <td>{summarize(e)}</td>
                  <td className="text-muted mono">
                    {e.task_id ? e.task_id.slice(0, 8) : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function typeColor(t: string): string {
  if (t === "state_transition") return "active";
  if (t === "decision") return "pass";
  if (t === "artifact") return "pending";
  return "idle";
}

function summarize(e: MemoryEvent): string {
  const p = e.payload as Record<string, any>;
  if (!p) return "";
  if (e.event_type === "state_transition") {
    // Payload may have {from, to} or just {state}
    if (p.from && p.to) return `${p.from} -> ${p.to}`;
    if (p.state) return `-> ${p.state}`;
    return JSON.stringify(p).slice(0, 80);
  }
  if (e.event_type === "message") return String(p.text ?? "").slice(0, 100);
  if (e.event_type === "decision") return String(p.decision ?? p.summary ?? "").slice(0, 100);
  if (e.event_type === "summary") return String(p.summary ?? "").slice(0, 100);
  return JSON.stringify(p).slice(0, 80);
}
