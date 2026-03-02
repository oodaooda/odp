# Deployment Hardening (ODP)

This is pragmatic guidance for deploying ODP beyond local dev.

## Security
- Set one of:
  - `ODP_API_TOKEN` (simple single-token auth), or
  - `ODP_RBAC_READ_TOKENS`, `ODP_RBAC_WRITE_TOKENS`, `ODP_RBAC_ADMIN_TOKENS` (comma-separated)
- Put ODP behind TLS (reverse proxy) and restrict network access.
- Rotate tokens periodically.

## Reverse proxy
Use a reverse proxy (Caddy/Nginx/Traefik) for:
- TLS termination
- rate limiting
- request size limits

## Database
- Prefer Postgres in production.
- Configure backups:
  - periodic pg_dump
  - WAL archiving (optional)

## Observability
- `/healthz` for liveness
- `/metrics` for basic counters
- Enable request logging as needed (future: structured JSON logs + traces)

## CI
- GitHub Actions workflow runs `pytest -q` on pushes/PRs.
