import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { listProjects, type Project } from "../api/client";
import { useToast } from "../components/Toast";

const inputStyle: React.CSSProperties = {
  width: "100%", maxWidth: 500, background: "var(--bg-input)",
  border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
  padding: "8px 12px", color: "var(--text-primary)", fontSize: 14, outline: "none",
};

export default function Settings() {
  const { projectId } = useParams<{ projectId: string }>();
  const { toast } = useToast();
  const [apiUrl, setApiUrl] = useState(
    () => import.meta.env.VITE_API_URL || window.location.origin
  );
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [projName, setProjName] = useState("");
  const [projRepo, setProjRepo] = useState("");
  const [projBranch, setProjBranch] = useState("main");

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

  useEffect(() => { loadProject(); }, [loadProject]);

  const handleSave = () => {
    localStorage.setItem("odp_api_url", apiUrl);
    if (token) localStorage.setItem("odp_api_token", token);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

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

      {/* Connection */}
      <div className="card mb-20">
        <h3>Connection</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>
              API URL
            </label>
            <input
              style={{
                width: "100%",
                maxWidth: 500,
                background: "var(--bg-input)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 12px",
                color: "var(--text-primary)",
                fontSize: 14,
                outline: "none",
                fontFamily: "'SF Mono', 'Fira Code', monospace",
              }}
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm text-muted" style={{ display: "block", marginBottom: 4 }}>
              API Token (optional — for RBAC-enabled backends)
            </label>
            <input
              type="password"
              style={{
                width: "100%",
                maxWidth: 500,
                background: "var(--bg-input)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 12px",
                color: "var(--text-primary)",
                fontSize: 14,
                outline: "none",
              }}
              placeholder="Bearer token..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="btn btn-primary" onClick={handleSave}>
              Save
            </button>
            {saved && <span className="status status-passed">Saved</span>}
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
              ["ODP_REDIS_URL", "Redis connection string", "redis://localhost:6379/0"],
              ["ODP_DATABASE_URL", "Postgres connection string", "sqlite+aiosqlite:///:memory:"],
              ["ODP_EMBEDDINGS_PROVIDER", "Embeddings provider (openai or none)", "none"],
              ["ODP_ENABLE_MERGE", "Enable automatic merge on commit", "0"],
              ["ODP_API_TOKEN", "Single admin token (back-compat)", "—"],
              ["ODP_RBAC_ADMIN_TOKENS", "Comma-separated admin tokens", "—"],
              ["ODP_RBAC_WRITE_TOKENS", "Comma-separated writer tokens", "—"],
              ["ODP_RBAC_READ_TOKENS", "Comma-separated reader tokens", "—"],
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
{`┌─────────────────────────────────────────────────────┐
│              FastAPI Application                     │
│  ┌─ React SPA (apps/web/)                           │
│  ├─ REST API endpoints                               │
│  └─ WebSocket event stream                           │
└──────────────┬──────────────────────────────────────┘
               │
        ┌──────┴──────┬──────────────┐
        │             │              │
    ┌───▼────┐   ┌───▼─────┐   ┌───▼──────┐
    │ Redis  │   │Postgres │   │Orchestr. │
    │(State) │   │(Memory) │   │(Logic)   │
    │ 6379   │   │ 5432    │   │          │
    └────────┘   └─────────┘   └──────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
    ┌────▼──────┐          ┌──────▼───┐
    │  Agents   │          │  Memory  │
    │(subprocess)│         │(append-  │
    │ Engineer  │          │  only)   │
    │ QA/QC     │          │ pgvector │
    │ Security  │          └──────────┘
    └───────────┘`}
        </div>
      </div>
    </>
  );
}
