"""Milestone 13: Production Hardening — verify auth flow, CI pipeline,
infra configs, backup scripts, and operational files."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"


def test_m13_login_page_exists():
    """React app must have a Login page component."""
    login = WEB_SRC / "pages" / "Login.tsx"
    assert login.is_file(), "Missing Login.tsx page"
    content = login.read_text()
    assert "onLogin" in content, "Login must accept onLogin callback"
    assert "Bearer" in content, "Login must send Bearer token"
    assert "localStorage" in content, "Login must store token in localStorage"


def test_m13_app_handles_auth():
    """App.tsx must check auth state and show Login when needed."""
    app = WEB_SRC / "App.tsx"
    content = app.read_text()
    assert "Login" in content, "App must import Login page"
    assert "authState" in content, "App must track auth state"
    assert "401" in content, "App must detect 401 responses"


def test_m13_api_client_sends_auth_header():
    """API client must include Authorization header from localStorage."""
    client = WEB_SRC / "api" / "client.ts"
    content = client.read_text()
    assert "authHeaders" in content, "Client must have authHeaders function"
    assert "Bearer" in content, "Client must send Bearer token"
    assert "localStorage" in content, "Client must read token from localStorage"


def test_m13_ci_pipeline():
    """GitHub Actions CI must have backend and frontend jobs."""
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.is_file(), "Missing CI workflow"
    content = ci.read_text()
    assert "backend" in content, "CI must have backend job"
    assert "frontend" in content, "CI must have frontend job"
    assert "ruff" in content, "CI must run linting"
    assert "pytest" in content, "CI must run pytest"
    assert "tsc" in content, "CI must run TypeScript check"
    assert "npm run build" in content, "CI must build frontend"


def test_m13_caddyfile():
    """Reverse proxy config must exist."""
    caddy = REPO_ROOT / "infra" / "Caddyfile"
    assert caddy.is_file(), "Missing Caddyfile"
    content = caddy.read_text()
    assert "reverse_proxy" in content, "Caddyfile must proxy to backend"
    assert "/ws/" in content, "Caddyfile must proxy WebSocket"
    assert "Strict-Transport-Security" in content, "Caddyfile must set HSTS"


def test_m13_systemd_units():
    """systemd service files must exist for orchestrator and redis."""
    systemd = REPO_ROOT / "infra" / "systemd"
    assert (systemd / "odp-orchestrator.service").is_file()
    orch = (systemd / "odp-orchestrator.service").read_text()
    assert "Restart=on-failure" in orch, "Must auto-restart on failure"
    assert "ProtectSystem" in orch, "Must have security hardening"

    assert (systemd / "odp-redis.service").is_file()


def test_m13_backup_restore_scripts():
    """Backup and restore scripts must exist and be executable."""
    backup = REPO_ROOT / "scripts" / "backup.sh"
    restore = REPO_ROOT / "scripts" / "restore.sh"
    assert backup.is_file(), "Missing backup.sh"
    assert restore.is_file(), "Missing restore.sh"
    import os
    assert os.access(str(backup), os.X_OK), "backup.sh must be executable"
    assert os.access(str(restore), os.X_OK), "restore.sh must be executable"
    assert "pg_dump" in backup.read_text(), "backup must dump postgres"
    assert "pg_restore" in restore.read_text(), "restore must restore postgres"
    assert "artifacts" in backup.read_text(), "backup must archive artifacts"
