import { useState } from "react";
import { useParams } from "react-router-dom";

export default function Settings() {
  const { projectId } = useParams<{ projectId: string }>();
  const [apiUrl, setApiUrl] = useState(
    () => import.meta.env.VITE_API_URL || window.location.origin
  );
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    // Store in localStorage for persistence
    localStorage.setItem("odp_api_url", apiUrl);
    if (token) localStorage.setItem("odp_api_token", token);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <>
      <div className="page-header">
        <h2>Settings</h2>
      </div>

      {/* Project info */}
      <div className="card mb-20">
        <h3>Project</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <span className="text-muted text-sm">Project ID: </span>
            <span className="mono">{projectId}</span>
          </div>
          <div>
            <span className="text-muted text-sm">Version: </span>
            <span>0.1.0</span>
          </div>
          <div>
            <span className="text-muted text-sm">Backend: </span>
            <span className="mono">{apiUrl}</span>
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
