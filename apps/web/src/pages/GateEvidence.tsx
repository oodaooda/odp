import { useEffect, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { listTasks, listMemoryEvents } from "../api/client";
import { usePollingRefresh } from "../hooks/useLiveRefresh";
import type { Task, GateDecision, MemoryEvent } from "../api/types";
import StateTimeline from "../components/StateTimeline";

export default function GateEvidence() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const taskIdParam = searchParams.get("task_id");

  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [_events, _setEvents] = useState<MemoryEvent[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<GateDecision | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const t = await listTasks(projectId).catch(() => []);
    const taskArr = Array.isArray(t) ? t : [];
    setTasks(taskArr);

    const target = taskIdParam
      ? taskArr.find((x) => x.task_id === taskIdParam)
      : taskArr[0];
    if (target) {
      setSelectedTask(target);
      const e = await listMemoryEvents(projectId, target.task_id).catch(() => ({
        events: [],
      }));
      _setEvents(e.events ?? []);
      if (!selectedEvidence && (target.gate_decisions ?? []).length > 0) {
        setSelectedEvidence(target.gate_decisions[0]);
      }
    }
    setLoading(false);
  }, [projectId, taskIdParam, selectedEvidence]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  usePollingRefresh(refresh, 5000);

  const gates = selectedTask?.gate_decisions ?? [];

  if (loading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h2>Gate Evidence</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {tasks.length > 1 && (
            <select
              style={{
                background: "var(--bg-input)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                padding: "6px 10px",
                borderRadius: "var(--radius-sm)",
                fontSize: 13,
              }}
              value={selectedTask?.task_id ?? ""}
              onChange={(e) => {
                const t = tasks.find((x) => x.task_id === e.target.value);
                if (t) {
                  setSelectedTask(t);
                  setSelectedEvidence(null);
                }
              }}
            >
              {tasks.map((t) => (
                <option key={t.task_id} value={t.task_id}>
                  {t.task_id.slice(0, 12)}
                </option>
              ))}
            </select>
          )}
          <button className="btn btn-primary">New Task +</button>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid-2col mb-20">
        {/* Gate Decisions */}
        <div className="card">
          <h3>Gate Decisions (Gate schema)</h3>
          {gates.length === 0 ? (
            <p className="text-muted text-sm">No gate decisions yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Phase</th>
                  <th>Result</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {gates.map((g, i) => (
                  <tr
                    key={i}
                    className="clickable-row"
                    onClick={() => setSelectedEvidence(g)}
                    style={{
                      background:
                        selectedEvidence?.gate_phase === g.gate_phase
                          ? "rgba(58,121,197,0.08)"
                          : undefined,
                    }}
                  >
                    <td>{g.gate_phase.replace(/_/g, "-")}</td>
                    <td>
                      <span
                        className={`status ${
                          g.passed ? "status-pass" : "status-fail"
                        }`}
                      >
                        {g.passed ? "pass" : "fail"}
                      </span>
                    </td>
                    <td className="text-muted">
                      {typeof g.evidence === "object" && !Array.isArray(g.evidence)
                        ? (g.evidence as any)?.summary || ((g as any).reason ?? "-")
                        : Array.isArray(g.evidence) ? g.evidence.join(", ") || "-" : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Evidence Viewer */}
        <div className="card">
          <h3>Evidence Viewer</h3>
          {selectedEvidence ? (
            <div className="evidence-viewer" style={{ whiteSpace: "pre-wrap" }}>
              {typeof selectedEvidence.evidence === "object" && !Array.isArray(selectedEvidence.evidence)
                ? JSON.stringify(selectedEvidence.evidence, null, 2)
                : Array.isArray(selectedEvidence.evidence) && selectedEvidence.evidence.length > 0
                ? selectedEvidence.evidence.join("\n")
                : (selectedEvidence as any).reason || "No evidence attached."}
            </div>
          ) : (
            <p className="text-muted text-sm">
              Select a gate to view evidence.
            </p>
          )}
        </div>
      </div>

      {/* Agent Tools */}
      <div className="card mb-20">
        <h3>Agent Tools</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Tool</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 500 }}>Screenshot</td>
              <td className="text-muted">Capture UI state and attach to evidence</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 500 }}>Log Reader</td>
              <td className="text-muted">Tail error logs and parse failures</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 500 }}>Diff Viewer</td>
              <td className="text-muted">Show diffs, patches, and test output</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* State Timeline */}
      {selectedTask && (
        <div className="card">
          <h3>State Transition Timeline</h3>
          <StateTimeline current={selectedTask.state} />
        </div>
      )}
    </>
  );
}
