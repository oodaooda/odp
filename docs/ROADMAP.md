# ODP Roadmap

This file is the high-level progress tracker (checkboxes). Keep it up to date as milestones land.

## Milestones

- [x] **M1** – Minimal orchestrator lifecycle + Redis schemas + WebSocket event stream + basic tests
- [x] **M2** – Real agent execution (multi-process), isolated workspaces, evidence artifacts, local infra (Redis/Postgres)
- [x] **M3** – Pending agent memory + promotion workflow + chat history API + basic retries
- [x] **M4** – Chat compaction summary + vector index wiring stub (best-effort) + tests
- [x] **M5** – Real embeddings (config-gated) + git workflow hardening + UI build-out
- [x] **M6** – Retrieval (pgvector) + merge automation + UI for evidence/promotion
- [x] **M7** – Production hardening (auth/RBAC, audit UI, deployment, observability, CI/CD)
- [x] **M8** – UI parity with dark-mode prototypes + live data bindings
- [x] **M9** – React SPA frontend (replaced embedded HTML with React + TypeScript + Vite)
- [x] **M10** – Frontend polish & real-time (Agents/Specs/Settings pages, WebSocket live refresh, toasts, error boundary)
- [ ] **M11** – Agent orchestration end-to-end (task execution flow, memory promotion, artifacts, search)
- [ ] **M12** – Production deployment (auth UX, TLS, systemd, CI pipeline, frontend tests)

## Post-milestone backlog

- [ ] Performance pass (orchestrator loop latency + WS throughput)
- [ ] Project selector UI (multi-project support)
- [ ] Dark/light theme toggle
- [ ] Responsive mobile layout improvements
