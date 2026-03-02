# Scope of Work

## Task
- Task ID: milestone_1
- Title: Orchestrator Skeleton + Gated Flow
- Spec refs:
  - docs/MILESTONE_1.md
  - docs/INDEX.md
  - docs/UI_SPEC.md
  - docs/PROCESS.md

## Objectives
- Deliver a minimal orchestrator service implementing the lifecycle: INIT → DISPATCH → COLLECT → VALIDATE → COMMIT/ROLLBACK.
- Persist task state + gate decisions + agent results in Redis.
- Provide reconnect-safe WebSocket event stream (replay + live).
- Implement artifact upload endpoint.
- Implement orchestrator-only write path to memory store (Postgres + pgvector), with append-only tables.

## Deliverables
- services/orchestrator/odp_orchestrator/* (FastAPI app + orchestrator loop + Redis store + WS event bus + DB writer)
- tests/test_milestone_1.py (end-to-end tests)
- docs/milestone_1/* (scope, roadmap, verification evidence)

## Constraints
- Python only.
- Redis required.
- Postgres required for real runs (tests may use sqlite fallback).
- No production-grade UI.

## Risks
- Local environments without Docker cannot run testcontainers-based integration tests.
- pgvector extension may not be installed in some dev/test Postgres instances.

## Acceptance Criteria
- `pytest` passes for Milestone 1 test suite.
- Task state transitions and gate decisions are emitted to WebSocket and persisted in Redis event log.
- Memory events + artifacts can be written by orchestrator.
