import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { listProjects, type Project } from "../api/client";
import { useToast } from "../components/Toast";

const inputStyle: React.CSSProperties = {
  width: "100%", maxWidth: 500, background: "var(--bg-input)",
  border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
  padding: "8px 12px", color: "var(--text-primary)", fontSize: 14, outline: "none",
};

// Common timezones for the selector.
const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Toronto",
  "America/Vancouver",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Australia/Sydney",
  "Australia/Melbourne",
  "Pacific/Auckland",
];

export default function Settings() {
  const { projectId } = useParams<{ projectId: string }>();
  const { toast } = useToast();
  const [apiUrl] = useState(
    () => import.meta.env.VITE_API_URL || window.location.origin
  );
  const [project, setProject] = useState<Project | null>(null);
  const [projName, setProjName] = useState("");
  const [projRepo, setProjRepo] = useState("");
  const [projBranch, setProjBranch] = useState("main");
  const [timezone, setTimezone] = useState(
    () => localStorage.getItem("odp_timezone") || Intl.DateTimeFormat().resolvedOptions().timeZone
  );
  const [ghToken, setGhToken] = useState("");
  const [ghTokenStatus, setGhTokenStatus] = useState<{ set: boolean; masked: string }>({ set: false, masked: "" });
  const [ghSaving, setGhSaving] = useState(false);

  const loadGhStatus = useCallback(async () => {
    if (!projectId) return;
    try {
      const stored = localStorage.getItem("odp_token");
      const headers: Record<string, string> = {};
      if (stored) headers["Authorization"] = `Bearer ${stored}`;
      const res = await fetch(`/projects/${projectId}/secrets/github_token`, { headers });
      if (res.ok) setGhTokenStatus(await res.json());
    } catch { /* ignore */ }
  }, [projectId]);

  const loadProject = useCallback(async () => {
    if (!projectId) return;
    try {
      const res = await listProjects();
      const p = (res.projects ?? []).find((pr) => pr.project_id === projectId);
      if (p) {
        setProject(p);
        setProjName(p.name);
        setProjRepo(p.github_repo ?? "");
        setProjBranch(p.default_branch ?? "main");
      }
    } catch { /* ignore */ }
  }, [projectId]);

  useEffect(() => { loadProject(); loadGhStatus(); }, [loadProject, loadGhStatus]);

  const handleSaveProject = async () => {
    if (!projectId) return;
    try {
      const stored = localStorage.getItem("odp_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (stored) headers["Authorization"] = `Bearer ${stored}`;
      const res = await fetch(`/projects/${projectId}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ name: projName, github_repo: projRepo, default_branch: projBranch }),
      });
      if (res.ok) {
        toast("Project settings saved", "success");
        loadProject();
      } else {
        toast("Failed to save project settings", "error");
      }
    } catch {
      toast("Failed to save project settings", "error");
    }
  };

  const handleTimezoneChange = (tz: string) => {
    setTimezone(tz);
    localStorage.setItem("odp_timezone", tz);
    toast(`Timezone set to ${tz}`, "success");
  };

  const handleSaveGhToken = async () => {
    if (!projectId || !ghToken.trim()) return;
    setGhSaving(true);
    try {
      const stored = localStorage.getItem("odp_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (stored) headers["Authorization"] = `Bearer ${stored}`;
      const res = await fetch(`/projects/${projectId}/secrets/github_token`, {
        method: "PUT", headers,
        body: JSON.stringify({ value: ghToken.trim() }),
      });
      if (res.ok) {
        toast("GitHub token saved", "success");
        setGhToken("");
        loadGhStatus();
      } else {
        toast("Failed to save token", "error");
      }
    } catch {
      toast("Failed to save token", "error");
    } finally {
      setGhSaving(false);
    }
  };

  const handleRemoveGhToken = async () => {
    if (!projectId) return;
    try {
      const stored = localStorage.getItem("odp_token");
      const headers: Record<string, string> = {};
      if (stored) headers["Authorization"] = `Bearer ${stored}`;
      await fetch(`/projects/${projectId}/secrets/github_token`, { method: "DELETE", headers });
      toast("GitHub token removed", "info");
      loadGhStatus();
    } catch { /* ignore */ }
  };

  return (
    <>
      <div className="page-header">
        <h2>Settings</h2>
      </div>

      {/* Project Settings */}
      <div className="card mb-20">
        <h3>Project Settings</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <span className="text-muted text-sm">Project ID: </span>
            <span className="mono">{projectId}</span>
          </div>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>Project Name</label>
            <input style={inputStyle} value={projName} onChange={(e) => setProjName(e.target.value)} placeholder="Project name..." />
          </div>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>GitHub Repository URL</label>
            <input style={{ ...inputStyle, fontFamily: "'SF Mono', 'Fira Code', monospace" }} value={projRepo} onChange={(e) => setProjRepo(e.target.value)} placeholder="https://github.com/owner/repo" />
          </div>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>Default Branch</label>
            <input style={{ ...inputStyle, fontFamily: "'SF Mono', 'Fira Code', monospace" }} value={projBranch} onChange={(e) => setProjBranch(e.target.value)} placeholder="main" />
          </div>
          <div>
            <button className="btn btn-primary" onClick={handleSaveProject}>Save Project Settings</button>
            {project && <span className="text-muted text-sm" style={{ marginLeft: 12 }}>Backend: {apiUrl}</span>}
          </div>
        </div>
      </div>

      {/* GitHub Token */}
      <div className="card mb-20">
        <h3>GitHub Integration</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="text-muted text-sm">
            A Personal Access Token (PAT) with <strong>Contents</strong> and <strong>Pull requests</strong> read/write permissions.
            Stored server-side only — never sent back to the browser.
          </div>
          {ghTokenStatus.set ? (
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="status status-passed">Set</span>
              <span className="mono text-muted">{ghTokenStatus.masked}</span>
              <button className="btn btn-sm" style={{ fontSize: 12, background: "var(--accent-red)", color: "#fff" }} onClick={handleRemoveGhToken}>
                Remove
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="password"
                style={{ ...inputStyle, maxWidth: 400 }}
                placeholder="github_pat_xxxxxxxxxxxx"
                value={ghToken}
                onChange={(e) => setGhToken(e.target.value)}
              />
              <button className="btn btn-primary" onClick={handleSaveGhToken} disabled={ghSaving || !ghToken.trim()}>
                {ghSaving ? "Saving..." : "Save Token"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Display Settings */}
      <div className="card mb-20">
        <h3>Display</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>
              Timezone
            </label>
            <select
              style={{
                ...inputStyle,
                maxWidth: 300,
                cursor: "pointer",
              }}
              value={timezone}
              onChange={(e) => handleTimezoneChange(e.target.value)}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz.replace(/_/g, " ")}</option>
              ))}
            </select>
            <div className="text-muted text-sm" style={{ marginTop: 4 }}>
              Current time: {new Date().toLocaleString("en-US", { timeZone: timezone, hour12: false })}
            </div>
          </div>
        </div>
      </div>

      {/* Environment Info */}
      <div className="card mb-20">
        <h3>Environment</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Variable</th>
              <th>Description</th>
              <th>Default</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["ODP_ORCH_LLM_PROVIDER", "Orchestrator LLM provider (anthropic)", "none"],
              ["ODP_AGENT_LLM_PROVIDER", "Agent LLM provider (openai)", "none"],
              ["ODP_REDIS_URL", "Redis connection string", "redis://localhost:6379/0"],
              ["ODP_DATABASE_URL", "Postgres connection string", "sqlite+aiosqlite:///:memory:"],
              ["ODP_EMBEDDINGS_PROVIDER", "Embeddings provider (openai or none)", "none"],
              ["ODP_ENABLE_MERGE", "Enable automatic merge on commit", "0"],
              ["ODP_API_TOKEN", "Single admin token (back-compat)", "\u2014"],
              ["ODP_LOG_REQUESTS", "Log all HTTP requests", "0"],
              ["ODP_AGENT_TIMEOUT_S", "Agent execution timeout (seconds)", "1200"],
            ].map(([key, desc, def]) => (
              <tr key={key}>
                <td className="mono" style={{ fontWeight: 500 }}>{key}</td>
                <td className="text-muted">{desc}</td>
                <td className="mono text-muted">{def}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Architecture */}
      <div className="card">
        <h3>Architecture</h3>
        <div className="evidence-viewer">
{`FastAPI Application
  \u251C\u2500 React SPA (apps/web/)
  \u251C\u2500 REST API endpoints
  \u2514\u2500 WebSocket event stream
        \u2502
  \u250C\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u252C\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u252C\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
  Redis       Postgres     Orchestrator
  (State)     (Memory)     (Logic)
  6379        5432
                \u2502
       \u250C\u2500\u2500\u2500\u2500\u2500\u2534\u2500\u2500\u2500\u2500\u2500\u252C\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
    Agents          Memory
    (subprocess)    (append-only)
    Engineer        pgvector
    QA / Security`}
        </div>
      </div>
    </>
  );
}
