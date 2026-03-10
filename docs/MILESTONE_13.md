# Milestone 13: Production Hardening & Deployment

## Goal
Make ODP deployable and secure for real use — not just local dev. This covers auth UX, TLS, process management, CI/CD, testing, and operational reliability.

## Scope

### 1) Auth flow in React app
- [x] Login page or token input screen (shown when backend returns 401)
- [x] Token stored in localStorage, sent as `Authorization: Bearer` header on all API calls
- [x] Role indicator in sidebar (reader/writer/admin)
- [x] Graceful handling of expired/invalid tokens

### 2) Frontend test suite
- [ ] Vitest + React Testing Library setup in `apps/web/`
- [ ] Unit tests for: API client, Toast, ErrorBoundary, StateTimeline
- [ ] Integration tests for: Dashboard renders tasks, Chat sends messages
- [ ] CI runs frontend tests alongside backend tests

### 3) CI/CD pipeline
- [x] GitHub Actions workflow: lint (ruff) → backend tests (pytest) → frontend build + test
- [x] Fail PR if any check fails
- [x] Build artifact: `apps/web/dist/` included in release

### 4) Reverse proxy + TLS
- [x] Caddy config for TLS termination
- [x] WebSocket proxying (`/ws/*`)
- [x] Rate limiting and request size limits
- [x] Example `Caddyfile` in `infra/`

### 5) Process management
- [x] systemd unit files for: orchestrator API, Redis
- [x] Auto-restart on failure
- [ ] Log rotation config
- [x] Example files in `infra/systemd/`

### 6) Backup & restore
- [x] `scripts/backup.sh` — pg_dump + artifact tarball
- [x] `scripts/restore.sh` — pg_restore + artifact extraction
- [ ] Documented in runbook

### 7) Bug fixes
- [x] Fix flaky M4 chat compaction test (SQLite race condition)
- [ ] Performance pass: ensure orchestrator loop < 200ms (SRD requirement)
- [ ] Verify WebSocket latency < 1s (SRD requirement)

## Non-goals
- Kubernetes / container orchestration
- Multi-region deployment
- SSO / OAuth (token-based auth is sufficient for v1)

## Deliverables
- [x] Auth flow working in React app
- [ ] Frontend test suite with >80% coverage on critical paths
- [x] CI pipeline green on GitHub Actions
- [x] TLS reverse proxy config in `infra/`
- [x] systemd units in `infra/systemd/`
- [x] Backup/restore scripts in `scripts/`
- [x] Flaky M4 test fixed
- [ ] All SRD performance requirements verified

## Evidence required
- CI pipeline screenshot (all checks green)
- Auth flow screenshot (login → dashboard)
- `pytest -q` + `npm test` both green
- TLS verified with `curl -v https://...`
