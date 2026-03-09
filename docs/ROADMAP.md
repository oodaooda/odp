# ODP Roadmap

This file is the high-level progress tracker. Keep it up to date as milestones land.

## Foundation (Complete)

- [x] **M1** – Orchestrator lifecycle + Redis schemas + WebSocket event stream + basic tests
- [x] **M2** – Agent execution (multi-process), isolated workspaces, evidence artifacts, local infra
- [x] **M3** – Agent memory + promotion workflow + chat history API + retries
- [x] **M4** – Chat compaction + vector index wiring (best-effort) + tests
- [x] **M5** – Embeddings (config-gated) + git workflow hardening + UI build-out
- [x] **M6** – Retrieval (pgvector) + merge automation + UI for evidence/promotion
- [x] **M7** – Production hardening (auth/RBAC, audit UI, observability, CI/CD)
- [x] **M8** – UI parity with dark-mode prototypes + live data bindings

## Frontend Rebuild (Complete)

- [x] **M9** – React SPA frontend (replaced embedded HTML with React + TypeScript + Vite)
- [x] **M10** – Frontend polish & real-time (all pages, WebSocket live refresh, toasts, error boundary)

## AI & Integration (Planned)

- [ ] **M11** – LLM agent integration (Claude/OpenAI code generation, retry with feedback, task context)
- [ ] **M12** – End-to-end orchestration UI (run tasks from browser, memory promotion, artifacts, search, project WS)
- [ ] **M13** – Production hardening & deployment (auth UX, TLS, systemd, CI pipeline, frontend tests, bug fixes)
- [ ] **M14** – Multi-project & GitHub integration (project selector, webhooks, PR creation, status checks)

## Post-v1 Backlog

- [ ] Multi-repo support (agent works across multiple repositories)
- [ ] Agent-to-agent feedback (engineer receives QA/security feedback directly)
- [ ] Custom agent roles (user-defined agents beyond engineer/qa/security)
- [ ] Dark/light theme toggle
- [ ] Mobile-responsive layout
