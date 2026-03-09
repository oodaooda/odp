import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listTasks, listChat, sendChat, seedDemo, createTask } from "../api/client";
import { usePollingRefresh } from "../hooks/useLiveRefresh";
import { useToast } from "../components/Toast";
import type { Task, ChatMessage } from "../api/types";

function timeAgo(ms: number): string {
  const diff = Date.now() - ms;
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(ms).toLocaleDateString();
}

export default function Dashboard() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [showNewTask, setShowNewTask] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const [t, c] = await Promise.all([
      listTasks(projectId).catch(() => []),
      listChat(projectId).catch(() => ({ messages: [] })),
    ]);
    setTasks(Array.isArray(t) ? t : []);
    setChat(c.messages ?? []);
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 5s polling (dashboard has no single task for WS)
  usePollingRefresh(refresh, 5000);

  const handleSendChat = async () => {
    if (!chatInput.trim() || !projectId) return;
    await sendChat(projectId, chatInput.trim());
    setChatInput("");
    refresh();
  };

  const handleSeedDemo = async () => {
    if (!projectId) return;
    try {
      await seedDemo(projectId);
      toast("Demo data seeded", "success");
      refresh();
    } catch {
      toast("Failed to seed demo data", "error");
    }
  };

  const handleCreateTask = async () => {
    if (!newTaskTitle.trim() || !projectId) return;
    try {
      await createTask(projectId, newTaskTitle.trim(), newTaskDesc.trim());
      toast("Task created", "success");
      setNewTaskTitle("");
      setNewTaskDesc("");
      setShowNewTask(false);
      refresh();
    } catch {
      toast("Failed to create task", "error");
    }
  };

  const activeTasks = tasks.filter((t) =>
    ["INIT", "DISPATCH", "COLLECT", "VALIDATE"].includes(t.state)
  ).length;

  const allGates = tasks.flatMap((t) => t.gate_decisions ?? []);
  const passedGates = allGates.filter((g) => g.passed).length;
  const gateStatus = allGates.length > 0 ? `${passedGates}/${allGates.length} pass` : "—";

  const agentRoles = new Set(
    tasks.flatMap((t) => (t.agent_results ?? []).map((r) => r.agent_role))
  );

  const lastRun = tasks.length > 0
    ? timeAgo(Math.max(...tasks.map((t) => t.updated_at_ms)))
    : "—";

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
          <h2>Dashboard</h2>
          <span className="subtitle">Project: Orchestrated Dev Platform</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={handleSeedDemo}>
            Seed Demo
          </button>
          <button className="btn btn-primary" onClick={() => setShowNewTask(true)}>
            New Task +
          </button>
        </div>
      </div>

      {/* New Task input */}
      {showNewTask && (
        <div className="card mb-20" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input
            style={{
              background: "var(--bg-input)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 12px",
              color: "var(--text-primary)",
              fontSize: 14,
              outline: "none",
            }}
            placeholder="Task title..."
            value={newTaskTitle}
            onChange={(e) => setNewTaskTitle(e.target.value)}
            autoFocus
          />
          <textarea
            style={{
              background: "var(--bg-input)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 12px",
              color: "var(--text-primary)",
              fontSize: 13,
              outline: "none",
              minHeight: 80,
              resize: "vertical",
              fontFamily: "inherit",
            }}
            placeholder="Description (optional) — describe what the agent should implement..."
            value={newTaskDesc}
            onChange={(e) => setNewTaskDesc(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreateTask}>
              Create
            </button>
            <button className="btn" onClick={() => setShowNewTask(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* KPI Row */}
      <div className="kpi-row">
        <div className="kpi-card">
          <div className="label">Active Tasks</div>
          <div className="value">{activeTasks}</div>
        </div>
        <div className="kpi-card">
          <div className="label">Gate Status</div>
          <div className="value" style={{ color: "var(--accent-orange)" }}>
            {gateStatus}
          </div>
        </div>
        <div className="kpi-card">
          <div className="label">Agents Online</div>
          <div className="value">{agentRoles.size}</div>
        </div>
        <div className="kpi-card">
          <div className="label">Last Run</div>
          <div className="value">{lastRun}</div>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid-2col">
        {/* Task list */}
        <div className="card">
          <h3>Tasks (Task schema)</h3>
          {tasks.length === 0 ? (
            <p className="text-muted">
              No tasks yet. Click "Seed Demo" to add sample data or "New Task +" to create one.
            </p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Task ID</th>
                  <th>Status</th>
                  <th>Phase</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr
                    key={t.task_id}
                    className="clickable-row"
                    onClick={() =>
                      navigate(`/projects/${projectId}/tasks/${t.task_id}`)
                    }
                  >
                    <td className="mono">{t.task_id.slice(0, 8)}</td>
                    <td>
                      <span className={`status status-${t.state}`}>
                        {t.state === "INIT" || t.state === "DISPATCH"
                          ? "pending"
                          : t.state === "ROLLBACK"
                          ? "failed"
                          : "running"}
                      </span>
                    </td>
                    <td>{t.state}</td>
                    <td className="text-muted">
                      {new Date(t.updated_at_ms).toISOString().slice(0, 19) + "Z"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Right column */}
        <div className="gap-16">
          {/* Chat panel */}
          <div className="card">
            <h3>Orchestrator Chat</h3>
            <div
              style={{
                maxHeight: 200,
                overflowY: "auto",
                marginBottom: 12,
                padding: 8,
                background: "var(--bg-input)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              {chat.length === 0 ? (
                <p className="text-muted text-sm">No messages yet.</p>
              ) : (
                chat.slice(-10).map((m) => (
                  <div key={m.id} style={{ marginBottom: 6, fontSize: 13 }}>
                    <span style={{ fontWeight: 600 }}>
                      {m.actor === "user" ? "You" : "Orchestrator"}:
                    </span>{" "}
                    {m.text}
                  </div>
                ))
              )}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                style={{
                  flex: 1,
                  background: "var(--bg-input)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "8px 12px",
                  color: "var(--text-primary)",
                  fontSize: 13,
                  outline: "none",
                }}
                placeholder="Type a message..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
              />
              <button className="btn btn-primary btn-sm" onClick={handleSendChat}>
                Send
              </button>
            </div>
          </div>

          {/* Agents panel */}
          <div className="card">
            <h3>Agents</h3>
            {tasks.length === 0 ? (
              <p className="text-muted text-sm">No active agents.</p>
            ) : (
              <div className="gap-16">
                {tasks
                  .flatMap((t) =>
                    (t.agent_results ?? []).map((r) => ({ ...r, taskId: t.task_id }))
                  )
                  .slice(0, 6)
                  .map((a, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        paddingBottom: 8,
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, textTransform: "capitalize" }}>
                          {a.agent_role}
                        </div>
                        <div className="text-sm text-muted">
                          Task {a.taskId.slice(0, 8)}
                        </div>
                      </div>
                      <span className={`status status-${a.ok ? "active" : "failed"}`}>
                        {a.ok ? "active" : "failed"}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
