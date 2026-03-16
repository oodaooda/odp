import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { getTask, listMemoryEvents, listArtifacts, listAgentMemory, promoteMemory, resumeTasks, cancelTask } from "../api/client";
import { useLiveRefresh } from "../hooks/useLiveRefresh";
import { useToast } from "../components/Toast";
import type { Task, MemoryEvent, Artifact, AgentMemory, TokenUsage } from "../api/types";
import StateTimeline from "../components/StateTimeline";
import { formatDate, formatTime } from "../utils/date";

export default function TaskDetail() {
  const { projectId, taskId } = useParams<{
    projectId: string;
    taskId: string;
  }>();
  const { toast } = useToast();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [pendingMemory, setPendingMemory] = useState<AgentMemory[]>([]);
  const [prevState, setPrevState] = useState<string | null>(null);
  const [expandedArtifact, setExpandedArtifact] = useState<string | null>(null);
  const [liveTokens, setLiveTokens] = useState<TokenUsage | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId || !taskId) return;
    const [t, e, a, m] = await Promise.all([
      getTask(projectId, taskId).catch(() => null),
      listMemoryEvents(projectId, taskId).catch(() => ({ events: [] })),
      listArtifacts(projectId, taskId).catch(() => ({ artifacts: [] })),
      listAgentMemory(projectId, "pending").catch(() => ({ agent_memory: [] })),
    ]);
    if (t) {
      if (prevState && t.state !== prevState) {
        toast(`Task state: ${prevState} → ${t.state}`, t.state === "COMMIT" ? "success" : t.state === "ROLLBACK" ? "error" : "info");
      }
      setPrevState(t.state);
      setTask(t);
    }
    setEvents(e.events ?? []);
    setArtifacts(a.artifacts ?? []);
    // Filter pending memory to this task.
    const allPending = m.agent_memory ?? [];
    setPendingMemory(allPending.filter((pm) => pm.task_id === taskId));
  }, [projectId, taskId, prevState, toast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const { wsConnected } = useLiveRefresh(projectId, taskId, refresh, 30_000, (type, data) => {
    if (type === "token_update" && data.token_usage) {
      setLiveTokens(data.token_usage as TokenUsage);
    }
  });

  const handlePromote = async (memoryId: string, decision: "approved" | "rejected") => {
    if (!projectId) return;
    try {
      await promoteMemory(projectId, memoryId, decision);
      toast(`Memory ${decision}`, decision === "approved" ? "success" : "info");
      refresh();
    } catch {
      toast("Failed to promote memory", "error");
    }
  };

  const handleResume = async () => {
    if (!projectId) return;
    try {
      await resumeTasks(projectId);
      toast("Tasks resumed", "success");
      refresh();
    } catch {
      toast("Failed to resume tasks", "error");
    }
  };

  const handleCancel = async () => {
    if (!projectId || !taskId) return;
    try {
      await cancelTask(projectId, taskId);
      toast("Task cancelled", "info");
      refresh();
    } catch {
      toast("Failed to cancel task", "error");
    }
  };

  if (!task) {
    return (
      <div className="loading-center">
        <div className="spinner" />
      </div>
    );
  }

  const isRunning = ["INIT", "DISPATCH", "COLLECT", "VALIDATE"].includes(task.state);
  const specRefs = ["01_PRD.md", "02_SRD.md", "04_ICD.md", "06_VV_PLAN.md"];

  return (
    <>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h2>Task Detail: {task.task_id?.slice(0, 12)}</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className={`ws-indicator ${wsConnected ? "connected" : "disconnected"}`} title={wsConnected ? "WebSocket connected" : "WebSocket disconnected"} />
          {!isRunning && task.state !== "COMMIT" && (
            <button className="btn btn-primary" onClick={handleResume}>
              Re-run Task
            </button>
          )}
          {isRunning && (
            <>
              <button className="btn" style={{ background: "var(--accent-red)", color: "#fff" }} onClick={handleCancel}>
                Cancel
              </button>
              <span className="status status-active">Running...</span>
            </>
          )}
        </div>
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
                {isRunning ? "running" : task.state.toLowerCase()}
              </span>
            </div>
            <div>
              <span className="text-muted text-sm">phase: </span>
              {task.state}
            </div>
            <div>
              <span className="text-muted text-sm">created_at: </span>
              {formatDate(task.created_at_ms)}
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
            {task.description && (
              <div>
                <span className="text-muted text-sm">description: </span>
                <div style={{ marginTop: 4, whiteSpace: "pre-wrap", fontSize: 13, color: "var(--text-secondary)" }}>
                  {task.description}
                </div>
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
            <p className="text-muted text-sm">
              {isRunning ? "Agents running..." : "No agent results yet."}
            </p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {(task.agent_results ?? []).map((r, i) => (
                  <tr key={i}>
                    <td style={{ textTransform: "capitalize" }}>{r.agent_role}</td>
                    <td>
                      <span className={`status ${r.ok ? "status-passed" : "status-failed"}`}>
                        {r.ok ? "passed" : "failed"}
                      </span>
                    </td>
                    <td className="text-muted text-sm">
                      {r.summary || `artifacts: ${r.artifacts?.length ?? 0}`}
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
          {events.filter((e) => e.event_type === "state_transition").length === 0 && (
            <p className="text-muted text-sm">No transitions yet.</p>
          )}
        </div>
      </div>

      {/* State Timeline */}
      <div className="card mb-20">
        <StateTimeline current={task.state} />
      </div>

      {/* Live Token Usage */}
      {(() => {
        const tokens = liveTokens ?? task.token_usage;
        if (!tokens) return null;
        const roles = ["engineer", "qa", "security", "orchestrator"] as const;
        const total = roles.reduce(
          (acc, r) => {
            const b = tokens[r];
            acc.input += b.input; acc.output += b.output; acc.cost += b.cost;
            return acc;
          },
          { input: 0, output: 0, cost: 0 }
        );
        const hasUsage = total.input > 0 || total.output > 0;
        if (!hasUsage) return null;
        return (
          <div className="card mb-20">
            <h3>
              Token Usage
              {liveTokens && isRunning && (
                <span style={{ marginLeft: 8, fontSize: 11, color: "var(--accent-green)", fontWeight: 400 }}>● live</span>
              )}
            </h3>
            <table className="data-table">
              <thead>
                <tr><th>Actor</th><th>Input</th><th>Output</th><th>Total</th><th>Est. Cost</th></tr>
              </thead>
              <tbody>
                {roles.map((r) => {
                  const b = tokens[r];
                  if (!b.input && !b.output) return null;
                  return (
                    <tr key={r}>
                      <td style={{ textTransform: "capitalize", fontWeight: 500 }}>{r}</td>
                      <td className="mono">{b.input.toLocaleString()}</td>
                      <td className="mono">{b.output.toLocaleString()}</td>
                      <td className="mono">{(b.input + b.output).toLocaleString()}</td>
                      <td className="mono" style={{ color: "var(--accent-orange)" }}>${b.cost.toFixed(4)}</td>
                    </tr>
                  );
                })}
                <tr style={{ borderTop: "1px solid var(--border)", fontWeight: 600 }}>
                  <td>Total</td>
                  <td className="mono">{total.input.toLocaleString()}</td>
                  <td className="mono">{total.output.toLocaleString()}</td>
                  <td className="mono">{(total.input + total.output).toLocaleString()}</td>
                  <td className="mono" style={{ color: "var(--accent-orange)" }}>${total.cost.toFixed(4)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        );
      })()}

      {/* Pending Agent Memory */}
      {pendingMemory.length > 0 && (
        <div className="card mb-20">
          <h3>Pending Agent Memory</h3>
          <p className="text-muted text-sm" style={{ marginBottom: 12 }}>
            Agents proposed these memory entries. Approve to persist or reject to discard.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Type</th>
                <th>Content</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pendingMemory.map((pm) => (
                <tr key={pm.id}>
                  <td style={{ textTransform: "capitalize" }}>{pm.agent_role}</td>
                  <td>{pm.memory_type}</td>
                  <td className="text-sm" style={{ maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {(pm.content ?? "").slice(0, 200)}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        className="btn btn-sm"
                        style={{ background: "var(--accent-green)", color: "#000", fontSize: 12, padding: "2px 8px" }}
                        onClick={() => handlePromote(pm.id, "approved")}
                      >
                        Approve
                      </button>
                      <button
                        className="btn btn-sm"
                        style={{ background: "var(--accent-red)", color: "#fff", fontSize: 12, padding: "2px 8px" }}
                        onClick={() => handlePromote(pm.id, "rejected")}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Audit Log */}
      <div className="card mb-20">
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
                    {formatTime(e.created_at)}
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
                    {e.task_id ? `task:${e.task_id?.slice(0, 8)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Artifacts */}
      {artifacts.length > 0 && (
        <div className="card">
          <h3>Artifacts</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>URI</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((a) => (
                <tr key={a.id}>
                  <td>{a.artifact_type}</td>
                  <td className="mono text-sm" style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {a.uri.split("/").pop() || a.uri}
                  </td>
                  <td className="text-muted">
                    {formatDate(a.created_at)}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        className="btn btn-sm"
                        style={{ fontSize: 12, padding: "2px 8px" }}
                        onClick={() => setExpandedArtifact(expandedArtifact === a.id ? null : a.id)}
                      >
                        {expandedArtifact === a.id ? "Hide" : "View"}
                      </button>
                      {a.uri && (
                        <a
                          href={a.uri}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-sm"
                          style={{ fontSize: 12, padding: "2px 8px", textDecoration: "none" }}
                        >
                          Download
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {expandedArtifact && (
            <div style={{ marginTop: 12, padding: 12, background: "var(--bg-input)", borderRadius: "var(--radius-sm)", maxHeight: 300, overflowY: "auto" }}>
              <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", margin: 0, color: "var(--text-secondary)" }}>
                {artifacts.find((a) => a.id === expandedArtifact)?.uri ?? "No content available"}
              </pre>
            </div>
          )}
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
