# Milestone 7: Production Hardening (Auth/RBAC, Audit UI, Deployment, Observability, CI/CD)

## Goal
Prepare ODP for real deployments by adding pragmatic security + ops foundations:
- Auth + RBAC (optional/config-gated)
- Audit-focused UI views
- Deployment hardening guidance
- Observability endpoints + structured logging
- CI/CD pipeline for tests

## Scope

### 1) Auth + RBAC (optional)
- If `ODP_API_TOKEN` (or RBAC token lists) are configured, require `Authorization: Bearer ...`.
- RBAC roles:
  - `reader`: can GET/list
  - `writer`: can create tasks/chat/upload artifacts
  - `admin`: can promote memory, trigger compaction, enable merges
- If no auth env vars are set, behavior remains unchanged (dev-friendly).

### 2) Audit UI
- Add UI pages for audit/review:
  - recent memory events (decision/summary/artifact/state transitions)
  - promotion decisions

### 3) Deployment hardening
- Document:
  - env var configuration
  - reverse proxy/TLS recommendation
  - token rotation
  - database backups

### 4) Observability
- Add endpoints:
  - `GET /healthz`
  - `GET /metrics` (lightweight text counters)
- Add request logging middleware (structured-ish JSON lines).

### 5) CI/CD
- Add GitHub Actions workflow running `pytest -q`.

## Deliverables
- [x] Optional auth + RBAC enforcement
- [x] Audit UI pages
- [x] Deployment hardening doc
- [x] /healthz + /metrics + request logging
- [x] CI workflow
- [x] Tests for auth gating (when enabled)

## Evidence
- `pytest -q` green
- No warnings
- CI workflow file present
