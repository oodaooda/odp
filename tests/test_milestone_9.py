"""Milestone 9: React SPA — verify the frontend build artifacts exist and
the project structure is correct."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "apps" / "web"


def test_m9_react_app_structure():
    """The React SPA should have the expected directory structure."""
    assert (WEB_DIR / "package.json").is_file()
    assert (WEB_DIR / "vite.config.ts").is_file()
    assert (WEB_DIR / "tsconfig.json").is_file()
    assert (WEB_DIR / "src" / "App.tsx").is_file()
    assert (WEB_DIR / "src" / "main.tsx").is_file()
    assert (WEB_DIR / "src" / "index.css").is_file()


def test_m9_all_pages_exist():
    """All required page components must exist."""
    pages_dir = WEB_DIR / "src" / "pages"
    required = [
        "Dashboard.tsx",
        "TaskDetail.tsx",
        "GateEvidence.tsx",
        "Chat.tsx",
        "AuditLog.tsx",
    ]
    for page in required:
        assert (pages_dir / page).is_file(), f"Missing page: {page}"


def test_m9_api_client_and_types():
    """The API client and type definitions must exist."""
    api_dir = WEB_DIR / "src" / "api"
    assert (api_dir / "client.ts").is_file()
    assert (api_dir / "types.ts").is_file()


def test_m9_core_components():
    """Core UI components must exist."""
    comp_dir = WEB_DIR / "src" / "components"
    assert (comp_dir / "Layout.tsx").is_file()
    assert (comp_dir / "StateTimeline.tsx").is_file()


def test_m9_vite_config_has_proxy():
    """Vite config should proxy API calls to the backend."""
    config = (WEB_DIR / "vite.config.ts").read_text()
    assert "/projects" in config, "Vite config missing /projects proxy"
    assert "/ws" in config, "Vite config missing /ws proxy"
    assert "0.0.0.0" in config, "Vite config should bind to 0.0.0.0 for LAN access"
