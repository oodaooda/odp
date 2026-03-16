/* ── REST client for ODP Orchestrator API ── */

import type {
  Task,
  ChatMessage,
  MemoryEvent,
  AgentMemory,
  Artifact,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("odp_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    // Token expired or invalid — clear and reload to show login.
    localStorage.removeItem("odp_token");
    window.location.reload();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/* ── Tasks ── */

export const listTasks = (projectId: string) =>
  api<Task[]>(`/projects/${projectId}/tasks`);

export const getTask = (projectId: string, taskId: string) =>
  api<Task>(`/projects/${projectId}/tasks/${taskId}`);

export const createTask = (projectId: string, title: string, description = "") =>
  api<Task>(`/projects/${projectId}/tasks`, {
    method: "POST",
    body: JSON.stringify({ title, description }),
  });

/* ── Chat ── */

export const listChat = (projectId: string, taskId?: string, limit = 200) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (taskId) params.set("task_id", taskId);
  return api<{ messages: ChatMessage[] }>(
    `/projects/${projectId}/chat?${params}`
  );
};

export const sendChat = (
  projectId: string,
  text: string,
  taskId?: string
) =>
  api<{ ok: boolean }>(`/projects/${projectId}/chat`, {
    method: "POST",
    body: JSON.stringify({ text, task_id: taskId ?? null, actor: "user" }),
  });

export const clearChat = (projectId: string, taskId?: string) => {
  const params = taskId ? `?task_id=${taskId}` : "";
  return api<{ ok: boolean }>(`/projects/${projectId}/chat${params}`, { method: "DELETE" });
};

/* ── Memory Events ── */

export const listMemoryEvents = (
  projectId: string,
  taskId?: string,
  limit = 200
) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (taskId) params.set("task_id", taskId);
  return api<{ events: MemoryEvent[] }>(
    `/projects/${projectId}/memory-events?${params}`
  );
};

/* ── Agent Memory ── */

export const listAgentMemory = (projectId: string, status?: string) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  return api<{ agent_memory: AgentMemory[] }>(
    `/projects/${projectId}/agent-memory?${params}`
  );
};

export const promoteMemory = (
  projectId: string,
  memoryId: string,
  decision: "approved" | "rejected",
  note?: string
) =>
  api<{ ok: boolean; promotion_id: string }>(
    `/projects/${projectId}/agent-memory/${memoryId}/promote`,
    {
      method: "POST",
      body: JSON.stringify({ decision, note: note ?? null }),
    }
  );

/* ── Artifacts ── */

export const listArtifacts = (projectId: string, taskId: string) =>
  api<{ artifacts: Artifact[] }>(
    `/projects/${projectId}/tasks/${taskId}/artifacts`
  );

/* ── Memory Search ── */

export const searchMemory = (projectId: string, query: string, limit = 20) =>
  api<{ events: MemoryEvent[] }>(
    `/projects/${projectId}/memory-events?q=${encodeURIComponent(query)}&limit=${limit}`
  );

/* ── Projects ── */

export interface Project {
  project_id: string;
  name: string;
  github_repo: string;
  default_branch: string;
}

export const listProjects = () =>
  api<{ projects: Project[] }>("/projects");

export const createProject = (name: string, githubRepo = "", defaultBranch = "main") =>
  api<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ name, github_repo: githubRepo, default_branch: defaultBranch }),
  });

/* ── Demo / Admin ── */

export const seedDemo = (projectId: string) =>
  api<{ ok: boolean; task_ids: string[] }>(
    `/projects/${projectId}/demo`,
    { method: "POST" }
  );

export const resumeTasks = (projectId: string) =>
  api<{ resumed: number }>(`/projects/${projectId}/resume`, {
    method: "POST",
  });

export const cancelTask = (projectId: string, taskId: string) =>
  api<{ ok: boolean }>(`/projects/${projectId}/tasks/${taskId}/cancel`, {
    method: "POST",
  });

export const deleteTask = (projectId: string, taskId: string) =>
  api<{ ok: boolean }>(`/projects/${projectId}/tasks/${taskId}`, {
    method: "DELETE",
  });

export const getRole = async (): Promise<string | null> => {
  try {
    const res = await fetch("/healthz", {
      headers: { ...authHeaders() },
    });
    const data = await res.json();
    return data.role ?? null;
  } catch {
    return null;
  }
};
