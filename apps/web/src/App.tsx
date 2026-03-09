import { Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import TaskDetail from "./pages/TaskDetail";
import GateEvidence from "./pages/GateEvidence";
import Chat from "./pages/Chat";
import Agents from "./pages/Agents";
import Specs from "./pages/Specs";
import AuditLog from "./pages/AuditLog";
import Settings from "./pages/Settings";

const DEFAULT_PROJECT = "00000000-0000-0000-0000-000000000001";

export default function App() {
  return (
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
  );
}
