import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { listMemoryEvents } from "../api/client";
import type { MemoryEvent } from "../api/types";

export default function AuditLog() {
  const { projectId } = useParams<{ projectId: string }>();
  const [events, setEvents] = useState<MemoryEvent[]>([]);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const e = await listMemoryEvents(projectId, undefined, 500).catch(() => ({
      events: [],
    }));
    setEvents(e.events ?? []);
  }, [projectId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <>
      <div className="page-header">
        <h2>Audit Log</h2>
      </div>

      <div className="card">
        {events.length === 0 ? (
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
                    {new Date(e.created_at).toISOString().slice(11, 19)}
                  </td>
                  <td>
                    <span
                      className={`status status-${typeColor(e.event_type)}`}
                    >
                      {e.event_type.toUpperCase()}
                    </span>
                  </td>
                  <td>{summarize(e)}</td>
                  <td className="text-muted mono">
                    {e.task_id ? e.task_id.slice(0, 8) : "—"}
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
  const p = e.payload as Record<string, string>;
  if (e.event_type === "state_transition") return `${p.from} -> ${p.to}`;
  if (e.event_type === "message") return String(p.text ?? "").slice(0, 100);
  if (e.event_type === "decision") return String(p.decision ?? p.summary ?? "").slice(0, 100);
  if (e.event_type === "summary") return String(p.summary ?? "").slice(0, 100);
  return JSON.stringify(p).slice(0, 80);
}
