# ODP Roadmap

This file is the high-level progress tracker (checkboxes). Keep it up to date as milestones land.

## Milestones

- [x] **M1** – Minimal orchestrator lifecycle + Redis schemas + WebSocket event stream + basic tests
- [x] **M2** – Real agent execution (multi-process), isolated workspaces, evidence artifacts, local infra (Redis/Postgres)
- [x] **M3** – Pending agent memory + promotion workflow + chat history API + basic retries
- [x] **M4** – Chat compaction summary + vector index wiring stub (best-effort) + tests

## Post-milestone hardening / backlog

- [x] **M5** – Real embeddings (config-gated) + git workflow hardening + UI build-out

- [x] **M6** – Retrieval (pgvector) + merge automation + UI for evidence/promotion

- [ ] Replace fake embeddings with a real embedding pipeline (configurable; keep local/dev safe)
- [ ] Git hardening: branch-per-task + worktree cleanup + stricter sandbox guarantees
- [ ] UI upgrades (dashboard pages for evidence + pending memory + compaction)
- [ ] Performance pass (orchestrator loop latency + WS throughput)
