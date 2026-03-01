# Milestone 1: Orchestrator Skeleton + Gated Flow

## Goal
Deliver a minimal, end-to-end, spec-gated orchestration loop that proves the control plane, state model, and gate enforcement across agent roles.

## Scope
- Orchestrator service (single process)
- Redis-backed state (Task, Agent Result, Gate Decision)
- WebSocket event stream (status updates)
- One deterministic task flow with explicit gates
 - Orchestrator chat endpoint (dashboard)
 - Artifact upload (screenshots/logs)
 - Memory write path (Postgres + pgvector)

## Non-goals
- No production-grade UI
- No autonomous deploys
- No non-Redis persistence
- No model/tool switching logic

## Deliverables
1. Orchestrator lifecycle:
   - INIT → DISPATCH → COLLECT → VALIDATE → COMMIT/ROLLBACK
   - Resumable on crash (state loaded from Redis)
2. Redis schemas implemented:
   - Task
   - Agent Result
   - Gate Decision
3. WebSocket:
   - Emits task status + gate decisions
   - Reconnect safe
4. Tests:
   - Task lifecycle
   - Agent spawn/collection
   - Gate enforcement
   - Crash recovery (resume)

## Gates (must pass)
- Phase 1: Orchestrator lifecycle tests
- Phase 2: Engineer task produces diff + local tests
- Phase 3: QA regression + spec compliance
- Phase 4: Security scan
- Phase 5: WebSocket stability

## Evidence required
- Test output logs
- Redis snapshot of task state
- WS event log transcript
- Git diff (if any changes)

## Open questions
- Which runtime framework? (e.g., Python asyncio + FastAPI/Starlette)
- Which Redis client? (sync vs async)
- WebSocket event format (JSON schema?)
