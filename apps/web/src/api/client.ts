/* ── REST client for ODP Orchestrator API ── */

import type {
  Task,
  ChatMessage,
  MemoryEvent,
  AgentMemory,
  Artifact,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
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

export const createTask = (projectId: string, title: string) =>
  api<Task>(`/projects/${projectId}/tasks`, {
    method: "POST",
    body: JSON.stringify({ title }),
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
