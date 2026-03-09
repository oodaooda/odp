import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { getTask, listMemoryEvents, listArtifacts } from "../api/client";
import { useTaskWebSocket } from "../hooks/useWebSocket";
import type { Task, MemoryEvent, Artifact } from "../api/types";
import StateTimeline from "../components/StateTimeline";

export default function TaskDetail() {
  const { projectId, taskId } = useParams<{
    projectId: string;
    taskId: string;
  }>();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  const refresh = useCallback(async () => {
    if (!projectId || !taskId) return;
    const [t, e, a] = await Promise.all([
      getTask(projectId, taskId).catch(() => null),
      listMemoryEvents(projectId, taskId).catch(() => ({ events: [] })),
      listArtifacts(projectId, taskId).catch(() => ({ artifacts: [] })),
    ]);
    if (t) setTask(t);
    setEvents(e.events ?? []);
    setArtifacts(a.artifacts ?? []);
  }, [projectId, taskId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // WebSocket for live updates
  useTaskWebSocket(projectId, taskId, () => {
    refresh();
  });

  if (!task) {
    return <p className="text-muted">Loading task...</p>;
  }

  // Derive spec refs from task title / events
  const specRefs = ["01_PRD.md", "02_SRD.md", "04_ICD.md", "06_VV_PLAN.md"];

  return (
    <>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h2>Task Detail: {task.task_id.slice(0, 12)}</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
        <button className="btn btn-primary">New Task +</button>
      </div>

      {/* Main grid */}
      <div className="grid-2col mb-20">
        {/* Task info */}
        <div className="card">
          <h3>Task (Task schema)</h3>
          <div className="gap-16">
            <div>
              <span className="text-muted text-sm">task-id: </span>
              <span className="mono">{task.task_id}</span>
            </div>
            <div>
              <span className="text-muted text-sm">status: </span>
              <span className={`status status-${task.state}`}>
                {["INIT", "DISPATCH", "COLLECT", "VALIDATE"].includes(task.state)
                  ? "running"
                  : task.state.toLowerCase()}
              </span>
            </div>
            <div>
              <span className="text-muted text-sm">phase: </span>
              {task.state}
            </div>
            <div>
              <span className="text-muted text-sm">created_at: </span>
              {new Date(task.created_at_ms).toISOString().slice(0, 19) + "Z"}
            </div>
            <div>
              <span className="text-muted text-sm">updated_at: </span>
              {new Date(task.updated_at_ms).toISOString().slice(0, 19) + "Z"}
            </div>
            {task.title && (
              <div>
                <span className="text-muted text-sm">title: </span>
                {task.title}
              </div>
            )}
          </div>
        </div>

        {/* Spec Refs */}
        <div className="card">
          <h3>Spec Refs</h3>
          <div className="gap-16">
            {specRefs.map((s) => (
              <div key={s} className="mono">
                {s}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Agent Results + State Transitions */}
      <div className="grid-2col mb-20">
        <div className="card">
          <h3>Agent Results (Agent Result schema)</h3>
          {(task.agent_results ?? []).length === 0 ? (
            <p className="text-muted text-sm">No agent results yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Artifacts</th>
                </tr>
              </thead>
              <tbody>
                {(task.agent_results ?? []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.agent_role}</td>
                    <td>
                      <span
                        className={`status ${
                          r.ok ? "status-passed" : "status-failed"
                        }`}
                      >
                        {r.ok ? "passed" : "failed"}
                      </span>
                    </td>
                    <td className="text-muted">
                      artifacts: {r.artifacts.length > 0 ? r.artifacts.join(", ") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h3>State Transitions</h3>
          {events
            .filter((e) => e.event_type === "state_transition")
            .map((e, i) => (
              <div key={i} className="text-sm" style={{ marginBottom: 4 }}>
                {String((e.payload as Record<string, string>).from ?? "?")} →{" "}
                {String((e.payload as Record<string, string>).to ?? "?")}
              </div>
            ))}
          {events.filter((e) => e.event_type === "state_transition").length ===
            0 && <p className="text-muted text-sm">No transitions yet.</p>}
        </div>
      </div>

      {/* State Timeline */}
      <div className="card mb-20">
        <StateTimeline current={task.state} />
      </div>

      {/* Audit Log */}
      <div className="card">
        <h3>Audit Log</h3>
        {events.length === 0 ? (
          <p className="text-muted text-sm">No events yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Detail</th>
                <th>Ref</th>
              </tr>
            </thead>
            <tbody>
              {events.slice(-20).map((e) => (
                <tr key={e.id}>
                  <td className="mono">
                    {new Date(e.created_at).toISOString().slice(11, 19)}
                  </td>
                  <td>
                    <span
                      className={`status status-${
                        e.event_type === "state_transition"
                          ? "active"
                          : e.event_type === "decision"
                          ? "pass"
                          : "pending"
                      }`}
                    >
                      {e.event_type.toUpperCase()}
                    </span>
                  </td>
                  <td>{summarizePayload(e)}</td>
                  <td className="text-muted mono">
                    {e.task_id ? `task:${e.task_id.slice(0, 8)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Artifacts */}
      {artifacts.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <h3>Artifacts</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>URI</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a) => (
                <tr key={a.id}>
                  <td>{a.artifact_type}</td>
                  <td className="mono">{a.uri}</td>
                  <td className="text-muted">
                    {new Date(a.created_at).toISOString().slice(0, 19)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function summarizePayload(e: MemoryEvent): string {
  const p = e.payload as Record<string, string>;
  if (e.event_type === "state_transition") return `${p.from} -> ${p.to}`;
  if (e.event_type === "message") return String(p.text ?? p.summary ?? "");
  if (e.event_type === "decision") return String(p.decision ?? p.summary ?? "");
  return JSON.stringify(p).slice(0, 80);
}
