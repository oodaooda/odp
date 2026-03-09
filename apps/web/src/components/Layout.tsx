import { useEffect, useState, useCallback } from "react";
import { NavLink, Outlet, useParams, useNavigate } from "react-router-dom";
import { useProjectSocket } from "../hooks/useProjectSocket";
import { listProjects, type Project } from "../api/client";

const NAV_ITEMS = [
  { label: "Dashboard", path: "" },
  { label: "Chat", path: "/chat" },
  { label: "Gates", path: "/gates" },
  { label: "Agents", path: "/agents" },
  { label: "Specs", path: "/specs" },
  { label: "Audit Log", path: "/audit" },
  { label: "Settings", path: "/settings" },
];

export default function Layout() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const base = `/projects/${projectId}`;
  const { connected } = useProjectSocket(projectId);
  const [projects, setProjects] = useState<Project[]>([]);

  const loadProjects = useCallback(async () => {
    try {
      const res = await listProjects();
      setProjects(res.projects ?? []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleProjectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const pid = e.target.value;
    if (pid) navigate(`/projects/${pid}`);
  };

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="sidebar-brand">
          <h1>ODP</h1>
          <p>Orchestrated Dev Platform</p>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, fontSize: 11 }}>
            <span className={`ws-indicator ${connected ? "connected" : "disconnected"}`} />
            <span style={{ color: "var(--text-muted)" }}>{connected ? "Live" : "Polling"}</span>
          </div>
        </div>
        {projects.length > 0 && (
          <div style={{ padding: "8px 16px" }}>
            <select
              value={projectId ?? ""}
              onChange={handleProjectChange}
              style={{
                width: "100%", background: "var(--bg-input)",
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                padding: "6px 8px", color: "var(--text-primary)", fontSize: 12,
              }}
            >
              <option value="">Select project...</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.label}
            to={`${base}${item.path}`}
            end={item.path === ""}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
