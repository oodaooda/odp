from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TaskState(StrEnum):
    INIT = "INIT"
    DISPATCH = "DISPATCH"
    COLLECT = "COLLECT"
    VALIDATE = "VALIDATE"
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"


class AgentRole(StrEnum):
    engineer = "engineer"
    qa = "qa"
    security = "security"


class GatePhase(StrEnum):
    PHASE_1_LIFECYCLE = "phase_1_lifecycle"
    PHASE_2_ENGINEER = "phase_2_engineer"
    PHASE_3_QA = "phase_3_qa"
    PHASE_4_SECURITY = "phase_4_security"
    PHASE_5_WS = "phase_5_ws"


class GateDecision(BaseModel):
    project_id: UUID
    task_id: UUID
    phase: GatePhase
    passed: bool
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    decided_at_ms: int


class AgentResult(BaseModel):
    project_id: UUID
    task_id: UUID
    role: AgentRole
    ok: bool
    summary: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    # Agent-proposed memory entries (pending promotion). Orchestrator remains the only writer to
    # source-of-truth memory_events.
    memory_entries: list[dict[str, Any]] = Field(default_factory=list)
    created_at_ms: int


class TokenBucket(BaseModel):
    """Token usage for a single actor (agent role or orchestrator)."""
    input: int = 0
    output: int = 0
    cost: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self.input += input_tokens
        self.output += output_tokens
        self.cost += cost


class TokenUsage(BaseModel):
    """Per-actor token tracking for a task."""
    engineer: TokenBucket = Field(default_factory=TokenBucket)
    qa: TokenBucket = Field(default_factory=TokenBucket)
    security: TokenBucket = Field(default_factory=TokenBucket)
    orchestrator: TokenBucket = Field(default_factory=TokenBucket)

    @property
    def total(self) -> TokenBucket:
        t = TokenBucket()
        for b in (self.engineer, self.qa, self.security, self.orchestrator):
            t.input += b.input
            t.output += b.output
            t.cost += b.cost
        return t


class Task(BaseModel):
    project_id: UUID
    task_id: UUID
    title: str
    description: str = ""
    spec_hash: str
    state: TaskState = TaskState.INIT
    created_at_ms: int
    updated_at_ms: int
    attempt: int = 0

    # IDs are tracked so the task is fully reconstructable from Redis alone.
    agent_results: list[str] = Field(default_factory=list)
    gate_decisions: list[str] = Field(default_factory=list)

    # Token usage across all LLM calls for this task.
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=50_000)


class ChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    task_id: UUID | None = None
    actor: Literal["user", "orchestrator"] = "user"
