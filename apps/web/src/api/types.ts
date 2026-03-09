/* ── ODP Data Types ── */

export type TaskState = "INIT" | "DISPATCH" | "COLLECT" | "VALIDATE" | "COMMIT" | "ROLLBACK";
export type AgentRole = "engineer" | "qa" | "security";
export type GatePhase =
  | "phase_1_lifecycle"
  | "phase_2_engineer"
  | "phase_3_qa"
  | "phase_4_security"
  | "phase_5_ws";

export interface AgentResult {
  agent_role: AgentRole;
  ok: boolean;
  summary: string;
  artifacts: string[];
  logs: string[];
  memory_entries: string[];
}

export interface GateDecision {
  gate_phase: GatePhase;
  passed: boolean;
  evidence: string[];
}

export interface Task {
  project_id: string;
  task_id: string;
  title: string;
  description: string;
  spec_hash: string;
  state: TaskState;
  created_at_ms: number;
  updated_at_ms: number;
  attempt: number;
  agent_results: AgentResult[];
  gate_decisions: GateDecision[];
}

export interface ChatMessage {
  id: string;
  project_id: string;
  task_id: string | null;
  actor: "user" | "orchestrator";
  text: string;
  created_at: string;
  compaction_of: string[] | null;
}

export interface MemoryEvent {
  id: string;
  project_id: string;
  task_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AgentMemory {
  id: string;
  project_id: string;
  task_id: string;
  agent_role: AgentRole;
  memory_type: string;
  content: string;
  status: string;
  created_at: string;
}

export interface Artifact {
  id: string;
  project_id: string;
  task_id: string;
  artifact_type: string;
  uri: string;
  meta: Record<string, unknown>;
  created_at: string;
}
