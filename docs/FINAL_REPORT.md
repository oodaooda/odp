# ODP Final Report (v0.1.0)

Date: 2026-03-02

## Summary
ODP is now a working, local-first orchestrator prototype with:
- A gated task lifecycle (INIT→…→COMMIT/ROLLBACK) and crash recovery
- Multi-role agent execution (engineer/qa/security) with evidence artifacts
- Postgres/SQLite-backed, append-only memory events + artifact records
- Pending agent memory proposals + promotion workflow
- Chat persistence + auditable compaction summaries
- WebSocket event stream with replay
- Optional embeddings pipeline (config-gated) + vector index best-effort
- Retrieval/search endpoint with evidence linking (pgvector or text fallback)
- Optional merge automation with evidence logs
- Auth/RBAC (optional), audit UI, observability endpoints, CI workflow

This release is intended as a **milestone-complete prototype**, not a production system.

## Milestones

### Milestone 1 — Orchestrator skeleton + gated flow
- State machine implemented (Redis-backed)
- WebSocket event stream + replay
- Core lifecycle + crash recovery tests

### Milestone 2 — Real agent execution + infra + evidence
- Agent runner executes role agents; captures logs/diffs/reports as artifacts
- Per-task, per-role workspace directories
- Local docker-compose for Redis + Postgres with schema init
- Evidence artifacts recorded in DB and emitted via WS

### Milestone 3 — Pending agent memory + promotion + chat history + retries
- Agents propose structured memory entries in their output (`memory_entries`)
- Orchestrator records them as pending and supports approve/reject promotion
- Chat history query endpoint
- Best-effort retry/backoff for retryable agent failures

### Milestone 4 — Compaction + vector index wiring + hardening
- Auditable chat compaction endpoint writes `memory_events` summaries with `compaction_of`
- Vector index table + best-effort derived upsert (pgvector optional)
- Worktree-based isolation for agent workspaces (real mode)

### Milestone 5 — Embeddings + git hardening + UI build-out
- Config-gated embeddings module with pgvector best-effort
- Branch-per-task + worktree cleanup
- UI pages for task detail, evidence, and pending memory

### Milestone 6 — Retrieval + merge automation + UI evidence/promotion
- Retrieval/search endpoint with pgvector-first, text fallback
- Optional merge automation with evidence logging
- UI supports artifacts + promotion workflows

### Milestone 7 — Production hardening
- Optional auth/RBAC
- Audit UI
- Deployment hardening doc
- /healthz, /metrics, request logging
- CI workflow

## Test status
All tests are green and run warning-free:

```bash
# inside the conda env `odp`
pytest -q
```

Latest observed result:
- `7 passed`
- `0 warnings`

## Notable implementation details
- FastAPI app uses lifespan handlers (startup/shutdown) instead of deprecated `on_event`.
- Resources are explicitly closed on shutdown (DB engine dispose; redis aclose when supported).
- In `ODP_AGENT_TEST_MODE=1`, agents run **in-process** to keep pytest stable/clean.
  - In normal mode, agents execute in subprocesses.

## Known issues / limitations
- Embeddings are **config-gated** and disabled by default (requires provider + API key).
- Merge automation is **optional** and disabled by default.
- UI is functional but not yet at full product polish (see `docs/ROADMAP.md` remaining items).

## Release tag
Target release tag: `v0.1.0`
