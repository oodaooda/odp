import { useState, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import TaskDetail from "./pages/TaskDetail";
import GateEvidence from "./pages/GateEvidence";
import Chat from "./pages/Chat";
import Agents from "./pages/Agents";
import Specs from "./pages/Specs";
import AuditLog from "./pages/AuditLog";
import Settings from "./pages/Settings";
import Login from "./pages/Login";

const DEFAULT_PROJECT = "00000000-0000-0000-0000-000000000001";

export default function App() {
  const [authState, setAuthState] = useState<"checking" | "needed" | "ok">("checking");

  useEffect(() => {
    // Check if auth is required by probing the API.
    const stored = localStorage.getItem("odp_token");
    fetch("/projects/default/tasks", {
      headers: stored ? { Authorization: `Bearer ${stored}` } : {},
    })
      .then((r) => {
        if (r.status === 401) {
          setAuthState("needed");
        } else {
          setAuthState("ok");
        }
      })
      .catch(() => {
        // Server unreachable — show app anyway (will show errors).
        setAuthState("ok");
      });
  }, []);

  const handleLogin = (token: string) => {
    localStorage.setItem("odp_token", token);
    setAuthState("ok");
  };

  if (authState === "checking") {
    return (
      <div className="loading-center">
        <div className="spinner" />
      </div>
    );
  }

  if (authState === "needed") {
    return (
      <ErrorBoundary>
        <Login onLogin={handleLogin} />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Navigate to={`/projects/${DEFAULT_PROJECT}`} replace />} />
            <Route path="/projects/:projectId" element={<Dashboard />} />
            <Route path="/projects/:projectId/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/projects/:projectId/gates" element={<GateEvidence />} />
            <Route path="/projects/:projectId/chat" element={<Chat />} />
            <Route path="/projects/:projectId/agents" element={<Agents />} />
            <Route path="/projects/:projectId/specs" element={<Specs />} />
            <Route path="/projects/:projectId/audit" element={<AuditLog />} />
            <Route path="/projects/:projectId/settings" element={<Settings />} />
          </Route>
        </Routes>
      </ToastProvider>
    </ErrorBoundary>
  );
}
