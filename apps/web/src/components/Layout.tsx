import { NavLink, Outlet, useParams } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Dashboard", path: "" },
  { label: "Chat", path: "/chat" },
  { label: "Tasks", path: "" },
  { label: "Gates", path: "/gates" },
  { label: "Agents", path: "/agents" },
  { label: "Audit Log", path: "/audit" },
  { label: "Settings", path: "/settings" },
];

export default function Layout() {
  const { projectId } = useParams();
  const base = `/projects/${projectId}`;

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="sidebar-brand">
          <h1>ODP</h1>
          <p>Orchestrated Dev Platform</p>
        </div>
        {NAV_ITEMS.map((item) => {
          // "Tasks" and "Dashboard" share the same base path
          if (item.label === "Tasks") {
            return (
              <NavLink
                key={item.label}
                to={base}
                end
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                {item.label}
              </NavLink>
            );
          }
          return (
            <NavLink
              key={item.label}
              to={`${base}${item.path}`}
              end={item.path === ""}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              {item.label}
            </NavLink>
          );
        })}
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
