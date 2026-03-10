# Security Hardening Guide — ODP

This document combines findings from two independent security audits and serves as a
reference for hardening ODP as it moves toward production deployment.

**Current score: ~8/10** (after Tier 1 + most Tier 2/3 fixes applied)

---

## Fixes Already Applied

These were fixed in the codebase and are no longer vulnerabilities:

### 1. Arbitrary file write via upload path traversal (was CRITICAL)
- **Was:** `file.filename` used directly in `os.path.join`, allowing `../../escape.txt`
- **Fix:** Filename sanitized with `Path(name).name`, resolved path checked against
  upload dir, fallback to UUID filename if suspicious. Streaming upload with 50 MB limit.
- **File:** `api.py` — `upload_artifact()`

### 2. WebSocket authentication bypass (was HIGH)
- **Was:** WS endpoints called `accept()` without any auth check
- **Fix:** `_ws_auth()` validates bearer token from query param or header before accepting.
  Unauthorized connections are closed with code 1008.
- **Files:** `api.py` — `ws_project()`, `ws_task()`; frontend hooks pass token via `?token=`

### 3. Secret leakage to agent subprocesses (was HIGH)
- **Was:** `os.environ.copy()` passed all env vars (including API tokens, DB creds) to agents
- **Fix:** Env vars matching `ODP_API_TOKEN`, `ODP_RBAC_*`, `ODP_GITHUB_TOKEN`,
  `ODP_GITHUB_WEBHOOK_SECRET`, `ODP_DATABASE_URL` are stripped before agent execution.
- **File:** `agent_runner.py` — `run_agent()`

### 4. .gitignore gaps (was LOW)
- **Fix:** Added `.env`, `.env.*`, `*.pem`, `*.key`, `backups/`, `*.sql.gz`, `*.tar.gz`

### 5. RBAC enforcement on admin endpoints (was HIGH)
- **Was:** `seed_demo`, `resume`, `compact_chat` accessible to writer role
- **Fix:** `_required_role()` now routes `/demo`, `/resume`, `/chat/compact`, `/promote`
  to admin role requirement.
- **File:** `api.py` — `_ADMIN_PATHS` + `_required_role()`

### 6. Require GitHub webhook secret (was MEDIUM)
- **Was:** Webhook accepted unsigned events when secret not configured
- **Fix:** Returns 503 if `ODP_GITHUB_WEBHOOK_SECRET` is not set.
- **File:** `api.py` — `github_webhook()`

### 7. Default bind to 127.0.0.1 (was MEDIUM)
- **Was:** Bound to 0.0.0.0 by default, exposing to LAN
- **Fix:** Default to `127.0.0.1`. Set `ODP_HOST=0.0.0.0` to override for LAN access.
- **File:** `__main__.py`

### 8. Rate limiting in FastAPI (was MEDIUM)
- **Was:** No app-level rate limiting; only Caddy edge limits
- **Fix:** Per-IP rate limiting middleware: 60 writes/min, 300 reads/min (configurable
  via `ODP_RATE_LIMIT_WRITE`, `ODP_RATE_LIMIT_READ`).
- **File:** `api.py` — `_check_rate_limit()` + auth middleware

### 9. Content Security Policy (was MEDIUM)
- **Was:** No CSP header; injected scripts could run unrestricted
- **Fix:** `security_headers_middleware` adds CSP, X-Content-Type-Options, X-Frame-Options,
  Referrer-Policy, Permissions-Policy on every response. Also added to Caddyfile.
- **Files:** `api.py`, `infra/Caddyfile`

### 10. Error message sanitization (was LOW-MEDIUM)
- **Was:** Error details like `"task not found"`, `"agent memory not found"` leaked structure
- **Fix:** All HTTPException details now use generic messages (`"not found"`, `"forbidden"`).
- **File:** `api.py`

### 11. Docker credential hardening (was LOW)
- **Was:** Postgres defaults hardcoded as `odp/odp` in docker-compose
- **Fix:** Uses `${POSTGRES_USER:-odp}` etc. for env override. Ports bound to `127.0.0.1`.
- **File:** `infra/docker-compose.yml`

### 12. Secret scanning expanded in agent (was LOW)
- **Was:** Only 4 secret markers (`sk-`, `wt_`, PEM, AWS key)
- **Fix:** Expanded to 16 patterns including GitHub tokens, multiple PEM types,
  `password=`, `api_key=`, `token=`, `secret=`.
- **File:** `services/agents/odp_agent/main.py` — `_SECRET_MARKERS`

### 13. Backup metadata redaction (was LOW)
- **Was:** `backup_meta.json` stored raw DB URL with credentials
- **Fix:** Credentials redacted to `***:***` before writing.
- **File:** `scripts/backup.sh`

### 14. Secret scanning + dependency auditing in CI (was Tier 3)
- **Fix:** Added `gitleaks` secret scanning job, `pip-audit` step in backend,
  `npm audit` step in frontend to `.github/workflows/ci.yml`.
- **File:** `.github/workflows/ci.yml`

### 15. Log rotation config (was Tier 3)
- **Fix:** Added `infra/logrotate.d/odp` with daily rotation, 14-day retention, compression.
- **File:** `infra/logrotate.d/odp`

---

## Remaining Issues — Future Production Hardening

### Token & Session Management
- **Token expiration:** Tokens never expire. Consider HMAC-signed tokens with TTL or JWT.
- **HttpOnly cookies:** Move tokens from localStorage to HttpOnly Secure cookies to
  eliminate XSS token theft.
- **Token rotation:** Document rotation process; add admin endpoint to invalidate tokens.

### Encryption at Rest
- **Redis encryption:** Project metadata stored as plaintext JSON. Use `cryptography.fernet`
  to encrypt sensitive fields. Key via `ODP_ENCRYPTION_KEY` env var.
- **Backup encryption:** Encrypt `pg_dump` output with GPG:
  ```bash
  pg_dump ... | gzip | gpg --symmetric --cipher-algo AES256 -o backup.sql.gz.gpg
  ```

### Agent Sandbox Hardening
- Agents run as subprocesses with same UID as orchestrator.
- Options (increasing isolation):
  1. `seccomp` profile restricting syscalls
  2. Linux namespaces (unshare) for filesystem/network isolation
  3. Container-per-agent (Docker/Podman)
  4. gVisor/Firecracker microVM (maximum isolation)
- Recommended for v1: Option 2 (namespaces)

### Audit Log Immutability
- Add hash chain to `memory_events` table:
  ```sql
  ALTER TABLE memory_events ADD COLUMN prev_hash TEXT;
  -- Each event hash = SHA256(prev_hash + event_data)
  ```

### Network Segmentation
- Redis/Postgres should use Docker internal network only (no host port mappings) in prod.
- Agent subprocesses: consider network namespace with no external access.

### TLS for Internal Connections
- Enable TLS for Redis (`rediss://`) and Postgres (`sslmode=require`).

### Structured Logging
- Replace `print()` with `structlog` or `logging`. Add redaction filter for tokens/keys.

### Upload Quotas
- Per-project upload quota (e.g., 500 MB total)
- Concurrent upload limit
- Temporary file cleanup cron

---

## Security Checklist for Production Launch

Before exposing ODP beyond localhost, verify all items:

- [x] RBAC enforced on admin endpoints
- [x] WebSocket auth enforced
- [x] Upload path traversal fixed
- [x] Agent env vars stripped of secrets
- [x] Rate limiting active at app layer
- [x] CSP + security headers set
- [x] GitHub webhook requires secret
- [x] Error messages sanitized
- [x] Secret scanning in CI
- [x] Dependency auditing in CI
- [x] Log rotation configured
- [x] `.env` excluded from git
- [x] Docker ports bound to localhost
- [ ] Auth tokens are set (`ODP_RBAC_ADMIN_TOKENS`, etc.)
- [ ] Caddy (or equivalent) is fronting the API with TLS
- [ ] Token expiration implemented
- [ ] Backup encryption enabled
- [ ] Redis encryption at rest

---

## What's Already Solid

- SQL queries use parameterized statements (SQLAlchemy `text()` with `:param`)
- HMAC comparison uses timing-safe `hmac.compare_digest()`
- Agent commands use list-based `subprocess` (no `shell=True`)
- Pydantic validates all request/response shapes
- Caddyfile enforces HSTS, request size limits, security headers
- File download has path traversal check (`resolved.relative_to(base)`)
- Auth failure logging for audit trail
- npm audit clean (no known advisories)

---

## Threat Model Summary

```
                    INTERNET / LAN
                         |
                    ┌────┴────┐
                    │  Caddy  │  TLS, rate limit, headers
                    └────┬────┘
                         |
                    ┌────┴────┐
                    │ FastAPI │  Auth middleware, RBAC, input validation
                    └────┬────┘
                         |
           ┌─────────────┼─────────────┐
           |             |             |
      ┌────┴───┐   ┌────┴───┐   ┌────┴──────┐
      │ Redis  │   │Postgres│   │  Agents   │
      │(state) │   │(memory)│   │(subprocess)│
      └────────┘   └────────┘   └─────┬─────┘
                                      |
                                ┌─────┴─────┐
                                │  LLM API  │
                                │ (Claude/  │
                                │  OpenAI)  │
                                └───────────┘

Attack surfaces:      Caddy → FastAPI → Redis/PG → Agents → LLM
Trust boundary:       Everything after Caddy is trusted internal
Key controls:         TLS at edge, auth at API, isolation at agent
```

---

*Last updated: 2026-03-10*
*Based on audits by: Claude Code + external security assessment*
