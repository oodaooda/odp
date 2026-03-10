# Security Hardening Guide — ODP

This document combines findings from two independent security audits and serves as a
reference for hardening ODP as it moves toward production deployment.

**Current score: ~6/10** (after critical fixes applied below)

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

---

## Remaining Issues — Ordered by Priority

### Tier 1: Fix Before Any Non-Local Exposure

#### T1.1 — RBAC enforcement on write endpoints
- **Risk:** Medium-High. Auth middleware sets role but most POST endpoints don't check it.
  `seed_demo` (creates test data) is accessible to anyone with "writer" role.
- **Where:** `api.py` — all `@app.post` handlers
- **Fix:** Add explicit role checks:
  ```python
  if _role_rank(request.state.role) < _role_rank("admin"):
      raise HTTPException(403, "admin required")
  ```
- **Priority endpoints:** `seed_demo`, `compact_chat`, `upload_artifact`, `create_project`

#### T1.2 — Require GitHub webhook secret
- **Risk:** Medium. Without `ODP_GITHUB_WEBHOOK_SECRET`, anyone can POST to
  `/webhooks/github` and create arbitrary tasks.
- **Where:** `api.py` — `github_webhook()`
- **Fix:** Reject requests if secret is not configured:
  ```python
  if not secret:
      raise HTTPException(503, "webhook not configured")
  ```

#### T1.3 — Default bind to 127.0.0.1
- **Risk:** Medium. Currently binds to 0.0.0.0 by default, exposing API to LAN.
- **Where:** `__main__.py`
- **Fix:** Default to `127.0.0.1`, use `ODP_BIND_HOST=0.0.0.0` to override for LAN access.
- **Note:** Acceptable for local dev on trusted network. Change for any shared/cloud deployment.

#### T1.4 — Rate limiting in FastAPI
- **Risk:** Medium. Caddy has rate limits, but direct access bypasses them.
  Brute force on auth tokens is possible.
- **Fix:** Add `slowapi` or custom middleware:
  - Auth endpoints: 10 req/min per IP
  - Write endpoints: 60 req/min per IP
  - Read endpoints: 300 req/min per IP
- **Dependency:** `pip install slowapi`

### Tier 2: Fix Before Production Deployment

#### T2.1 — Token expiration and rotation
- **Risk:** Medium. Tokens never expire. If leaked, they grant permanent access.
- **Current:** Raw string comparison against env vars.
- **Fix options:**
  - HMAC-signed tokens with embedded expiry: `base64(payload).hmac_signature`
  - JWT with short TTL (1 hour) + refresh endpoint
  - At minimum: add token rotation script and document the process

#### T2.2 — Move tokens from localStorage to HttpOnly cookies
- **Risk:** Medium. localStorage is accessible to any JS on the page (XSS = token theft).
- **Fix:** Set `HttpOnly`, `Secure`, `SameSite=Strict` cookie from login endpoint.
  Frontend stops managing tokens; browser handles it automatically.
- **Trade-off:** Slightly more complex CORS setup, but eliminates entire class of XSS attacks.

#### T2.3 — Content Security Policy (CSP)
- **Risk:** Medium. No CSP means injected scripts run unrestricted.
- **Fix:** Add CSP header in FastAPI (not just Caddy):
  ```python
  response.headers["Content-Security-Policy"] = (
      "default-src 'self'; "
      "script-src 'self'; "
      "style-src 'self' 'unsafe-inline'; "
      "connect-src 'self' wss:; "
      "img-src 'self' data:; "
      "frame-ancestors 'none'"
  )
  ```

#### T2.4 — Encrypt secrets at rest in Redis
- **Risk:** Medium. Project metadata (including GitHub repo URLs) stored as plaintext JSON.
- **Fix:** Use `cryptography.fernet` to encrypt sensitive fields before Redis storage.
  Key derived from `ODP_ENCRYPTION_KEY` env var.

#### T2.5 — Error message sanitization
- **Risk:** Low-Medium. HTTP error responses reveal internal structure
  (`"task not found"`, `"agent memory not found"`, path info in artifact errors).
- **Fix:** Generic external messages, log details server-side only:
  ```python
  raise HTTPException(404)  # No detail for external callers
  logger.warning("task %s not found in project %s", task_id, project_id)
  ```

#### T2.6 — Upload DoS prevention
- **Risk:** Medium. Even with 50 MB limit, concurrent large uploads can exhaust memory/disk.
- **Fix:**
  - Per-project upload quota (e.g., 500 MB total)
  - Concurrent upload limit (e.g., 3 per project)
  - Temporary file cleanup cron

#### T2.7 — Docker credential hardening
- **Risk:** Low (local dev). Postgres defaults are `odp/odp` in docker-compose.
- **Fix:** Use `.env` file for docker-compose, document that defaults must be changed:
  ```yaml
  environment:
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
  ```

### Tier 3: Production Operations

#### T3.1 — Structured logging with redaction
- **Fix:** Replace `print()` calls with `structlog` or `logging`. Add redaction filter
  that strips tokens, API keys, and passwords from all log output.
- **Benefit:** Audit trail without secret leakage.

#### T3.2 — Log rotation
- **Fix:** Configure `logrotate` or use systemd journal with size limits.
  Add to `infra/logrotate.d/odp`.

#### T3.3 — Secret scanning in CI
- **Fix:** Add `trufflehog` or `gitleaks` to `.github/workflows/ci.yml`:
  ```yaml
  - name: Secret scan
    uses: trufflesecurity/trufflehog@main
    with:
      extra_args: --only-verified
  ```

#### T3.4 — Dependency auditing in CI
- **Fix:** Add to CI pipeline:
  ```yaml
  - run: pip install pip-audit && pip-audit
  - run: cd apps/web && npm audit --audit-level=high
  ```

#### T3.5 — Agent sandbox hardening
- **Risk:** Low-Medium. Agents run as subprocesses with same UID as orchestrator.
- **Fix options (increasing isolation):**
  1. `seccomp` profile restricting syscalls
  2. Linux namespaces (unshare) for filesystem/network isolation
  3. Container-per-agent (Docker/Podman)
  4. gVisor/Firecracker microVM (maximum isolation)
- **Recommended for v1:** Option 2 (namespaces) — good balance of isolation vs. complexity

#### T3.6 — Audit log immutability
- **Fix:** Add hash chain to memory_events table:
  ```sql
  ALTER TABLE memory_events ADD COLUMN prev_hash TEXT;
  -- Each event's hash = SHA256(prev_hash + event_data)
  ```
  Tampering breaks the chain and is detectable.

#### T3.7 — Network segmentation
- **Fix:** Redis and Postgres should not be reachable from outside the host.
  Docker compose: remove port mappings, use internal network only.
  Agent subprocesses: consider network namespace with no external access.

#### T3.8 — TLS for internal connections
- **Fix:** Enable TLS for Redis (`rediss://`) and Postgres (`sslmode=require`).
  Prevents sniffing on shared hosts.

#### T3.9 — Backup encryption
- **Fix:** Encrypt backup output:
  ```bash
  pg_dump ... | gzip | gpg --symmetric --cipher-algo AES256 -o backup.sql.gz.gpg
  ```

#### T3.10 — Secret scanning in agent output
- **Current:** Agent security checker only catches 4 patterns (`sk-`, `wt_`, PEM, AWS key).
- **Fix:** Expand to cover common patterns:
  ```python
  _SECRET_MARKERS = [
      "sk-", "wt_", "ghp_", "gho_", "github_pat_",
      "-----BEGIN", "AWS_SECRET", "AKIA",
      "password=", "api_key=", "token=", "secret=",
      "eyJ",  # JWT prefix (base64 of '{"')
  ]
  ```

---

## Security Checklist for Production Launch

Before exposing ODP beyond localhost, verify all items:

- [ ] All Tier 1 items resolved
- [ ] All Tier 2 items resolved (or risk accepted with documentation)
- [ ] Auth tokens are set (`ODP_RBAC_ADMIN_TOKENS`, etc.)
- [ ] GitHub webhook secret is configured
- [ ] Caddy (or equivalent) is fronting the API with TLS
- [ ] Redis/Postgres not exposed on public interface
- [ ] Docker default credentials changed
- [ ] `.env` file excluded from git
- [ ] `pip-audit` and `npm audit` show no high/critical issues
- [ ] Backup encryption enabled
- [ ] Log rotation configured
- [ ] Secret scanning in CI pipeline
- [ ] Rate limiting active at both proxy and app layer
- [ ] CSP header set
- [ ] Agent subprocess env vars are stripped of secrets

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
