import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { listTasks } from "../api/client";
import type { Task, AgentResult } from "../api/types";

interface AgentRow extends AgentResult {
  taskId: string;
  taskTitle: string;
  taskState: string;
}

export default function Agents() {
  const { projectId } = useParams<{ projectId: string }>();
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const tasks = await listTasks(projectId).catch(() => [] as Task[]);
    const arr = Array.isArray(tasks) ? tasks : [];
    const rows: AgentRow[] = arr.flatMap((t) =>
      (t.agent_results ?? []).map((r) => ({
        ...r,
        taskId: t.task_id,
        taskTitle: t.title,
        taskState: t.state,
      }))
    );
    setAgents(rows);
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  // Derive unique agent roles with aggregated status
  const roleMap = new Map<string, { active: number; failed: number; total: number; tasks: string[] }>();
  for (const a of agents) {
    const entry = roleMap.get(a.agent_role) ?? { active: 0, failed: 0, total: 0, tasks: [] };
    entry.total++;
    if (a.ok) entry.active++;
    else entry.failed++;
    entry.tasks.push(a.taskId.slice(0, 8));
    roleMap.set(a.agent_role, entry);
  }

  return (
    <>
      <div className="page-header">
        <h2>Agents</h2>
      </div>

      {/* Agent summary cards */}
      <div className="kpi-row">
        {["engineer", "qa", "security"].map((role) => {
          const data = roleMap.get(role);
          return (
            <div className="kpi-card" key={role}>
              <div className="label" style={{ textTransform: "capitalize" }}>
                {role}
              </div>
              <div className="value">
                {data ? (
                  <span className={`status-${data.failed > 0 ? "failed" : "active"}`}>
                    {data.active}/{data.total} pass
                  </span>
                ) : (
                  <span className="text-muted" style={{ fontSize: 16 }}>idle</span>
                )}
              </div>
            </div>
          );
        })}
        <div className="kpi-card">
          <div className="label">Total Runs</div>
          <div className="value">{agents.length}</div>
        </div>
      </div>

      {/* Agent results table */}
      <div className="card">
        <h3>Agent Results</h3>
        {loading ? (
          <p className="text-muted">Loading...</p>
        ) : agents.length === 0 ? (
          <p className="text-muted">No agent results yet. Create and run a task to see agent activity.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Status</th>
                <th>Task</th>
                <th>Task State</th>
                <th>Summary</th>
                <th>Artifacts</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600, textTransform: "capitalize" }}>
                    {a.agent_role}
                  </td>
                  <td>
                    <span className={`status ${a.ok ? "status-passed" : "status-failed"}`}>
                      {a.ok ? "passed" : "failed"}
                    </span>
                  </td>
                  <td className="mono">{a.taskId.slice(0, 8)}</td>
                  <td>
                    <span className={`status status-${a.taskState}`}>{a.taskState}</span>
                  </td>
                  <td className="text-muted">{a.summary || "—"}</td>
                  <td className="text-muted mono">
                    {a.artifacts.length > 0 ? a.artifacts.join(", ") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Role descriptions */}
      <div className="card" style={{ marginTop: 20 }}>
        <h3>Agent Roles</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Responsibility</th>
              <th>Gate Phase</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 600 }}>Engineer</td>
              <td className="text-muted">Writes code, runs tests, produces diffs and test logs</td>
              <td className="mono">phase_2_engineer</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600 }}>QA</td>
              <td className="text-muted">Regression testing, spec compliance verification</td>
              <td className="mono">phase_3_qa</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600 }}>Security</td>
              <td className="text-muted">Secret scanning, dependency checks, vulnerability assessment</td>
              <td className="mono">phase_4_security</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
