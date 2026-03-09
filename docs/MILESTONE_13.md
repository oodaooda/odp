# Milestone 13: Production Hardening & Deployment

## Goal
Make ODP deployable and secure for real use — not just local dev. This covers auth UX, TLS, process management, CI/CD, testing, and operational reliability.

## Scope

### 1) Auth flow in React app
- [ ] Login page or token input screen (shown when backend returns 401)
- [ ] Token stored in localStorage, sent as `Authorization: Bearer` header on all API calls
- [ ] Role indicator in sidebar (reader/writer/admin)
- [ ] Graceful handling of expired/invalid tokens

### 2) Frontend test suite
- [ ] Vitest + React Testing Library setup in `apps/web/`
- [ ] Unit tests for: API client, Toast, ErrorBoundary, StateTimeline
- [ ] Integration tests for: Dashboard renders tasks, Chat sends messages
- [ ] CI runs frontend tests alongside backend tests

### 3) CI/CD pipeline
- [ ] GitHub Actions workflow: lint (ruff) → backend tests (pytest) → frontend build + test
- [ ] Fail PR if any check fails
- [ ] Build artifact: `apps/web/dist/` included in release

### 4) Reverse proxy + TLS
- [ ] Caddy or nginx config for TLS termination
- [ ] WebSocket proxying (`/ws/*`)
- [ ] Rate limiting and request size limits
- [ ] Example `Caddyfile` or `nginx.conf` in `infra/`

### 5) Process management
- [ ] systemd unit files for: orchestrator API, Redis, Postgres
- [ ] Auto-restart on failure
- [ ] Log rotation config
- [ ] Example files in `infra/systemd/`

### 6) Backup & restore
- [ ] `scripts/backup.sh` — pg_dump + artifact tarball
- [ ] `scripts/restore.sh` — pg_restore + artifact extraction
- [ ] Documented in runbook

### 7) Bug fixes
- [ ] Fix flaky M4 chat compaction test (SQLite race condition)
- [ ] Performance pass: ensure orchestrator loop < 200ms (SRD requirement)
- [ ] Verify WebSocket latency < 1s (SRD requirement)

## Non-goals
- Kubernetes / container orchestration
- Multi-region deployment
- SSO / OAuth (token-based auth is sufficient for v1)

## Deliverables
- [ ] Auth flow working in React app
- [ ] Frontend test suite with >80% coverage on critical paths
- [ ] CI pipeline green on GitHub Actions
- [ ] TLS reverse proxy config in `infra/`
- [ ] systemd units in `infra/systemd/`
- [ ] Backup/restore scripts in `scripts/`
- [ ] Flaky M4 test fixed
- [ ] All SRD performance requirements verified

## Evidence required
- CI pipeline screenshot (all checks green)
- Auth flow screenshot (login → dashboard)
- `pytest -q` + `npm test` both green
- TLS verified with `curl -v https://...`
