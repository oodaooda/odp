import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import TaskDetail from "./pages/TaskDetail";
import GateEvidence from "./pages/GateEvidence";
import Chat from "./pages/Chat";
import AuditLog from "./pages/AuditLog";

// Default project ID — for single-project use.
// In production this would come from a project selector or URL.
const DEFAULT_PROJECT = "00000000-0000-0000-0000-000000000001";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to={`/projects/${DEFAULT_PROJECT}`} replace />} />
        <Route path="/projects/:projectId" element={<Dashboard />} />
        <Route path="/projects/:projectId/tasks/:taskId" element={<TaskDetail />} />
        <Route path="/projects/:projectId/gates" element={<GateEvidence />} />
        <Route path="/projects/:projectId/chat" element={<Chat />} />
        <Route path="/projects/:projectId/agents" element={<Dashboard />} />
        <Route path="/projects/:projectId/audit" element={<AuditLog />} />
        <Route path="/projects/:projectId/settings" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
