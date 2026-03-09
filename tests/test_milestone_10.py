"""Milestone 10: Frontend polish — verify all M10 pages, hooks, and
components exist and the build is clean."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"


def test_m10_new_pages_exist():
    """M10 added Agents, Specs, and Settings pages."""
    pages_dir = WEB_SRC / "pages"
    for page in ["Agents.tsx", "Specs.tsx", "Settings.tsx"]:
        assert (pages_dir / page).is_file(), f"Missing M10 page: {page}"


def test_m10_toast_component():
    """Toast notification system must exist."""
    assert (WEB_SRC / "components" / "Toast.tsx").is_file()
    content = (WEB_SRC / "components" / "Toast.tsx").read_text()
    assert "useToast" in content, "Toast must export useToast hook"
    assert "ToastProvider" in content, "Toast must export ToastProvider"


def test_m10_error_boundary():
    """ErrorBoundary component must exist."""
    assert (WEB_SRC / "components" / "ErrorBoundary.tsx").is_file()
    content = (WEB_SRC / "components" / "ErrorBoundary.tsx").read_text()
    assert "getDerivedStateFromError" in content, "Must implement getDerivedStateFromError"


def test_m10_live_refresh_hooks():
    """WebSocket and polling hooks must exist."""
    hooks_dir = WEB_SRC / "hooks"
    assert (hooks_dir / "useLiveRefresh.ts").is_file()
    content = (hooks_dir / "useLiveRefresh.ts").read_text()
    assert "useLiveRefresh" in content
    assert "usePollingRefresh" in content


def test_m10_app_wires_all_routes():
    """App.tsx must include routes for all 8 pages."""
    app_content = (WEB_SRC / "App.tsx").read_text()
    for route in [
        "Dashboard",
        "TaskDetail",
        "GateEvidence",
        "Chat",
        "Agents",
        "Specs",
        "AuditLog",
        "Settings",
    ]:
        assert route in app_content, f"App.tsx missing route for {route}"
    assert "ErrorBoundary" in app_content, "App.tsx must include ErrorBoundary"
    assert "ToastProvider" in app_content, "App.tsx must include ToastProvider"


def test_m10_css_has_animations():
    """index.css must include toast animation and loading spinner."""
    css = (WEB_SRC / "index.css").read_text()
    assert "toast-in" in css, "Missing toast animation keyframes"
    assert ".spinner" in css, "Missing spinner class"
    assert ".loading-center" in css, "Missing loading-center class"
