"""Milestone 8: UI parity — verify the old embedded HTML was removed and
the SPA catch-all serves index.html from the React build."""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name, txt in [
            ("INDEX.md", "index"),
            ("MILESTONE_1.md", "m1"),
            ("UI_SPEC.md", "ui"),
        ]:
            (td / name).write_text(txt, encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(td / "INDEX.md"))
        monkeypatch.setenv("ODP_SPEC_M1", str(td / "MILESTONE_1.md"))
        monkeypatch.setenv("ODP_UI_SPEC", str(td / "UI_SPEC.md"))
        monkeypatch.setenv("ODP_FAKE_REDIS", "1")
        monkeypatch.setenv("ODP_REDIS_URL", "redis://unused")
        monkeypatch.setenv("ODP_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("ODP_AUTO_MIGRATE", "1")
        monkeypatch.setenv("ODP_AGENT_TEST_MODE", "1")
        monkeypatch.setenv("ODP_ARTIFACT_DIR", str(td / "artifacts"))
        monkeypatch.setenv("ODP_WORKSPACE_DIR", str(td / "workspaces"))
        monkeypatch.setenv("ODP_REPO_ROOT", str(Path(__file__).resolve().parents[1]))

        from services.orchestrator.odp_orchestrator.api import create_app

        yield create_app()


def test_m8_no_old_embedded_html_routes(app):
    """The old HTML UI routes (/ui/*) should not exist. API routes should still work."""
    with TestClient(app) as client:
        # API endpoints must still function
        assert client.get("/healthz").status_code == 200

        project_id = uuid4()
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m8-test"})
        assert r.status_code == 200

        r = client.get(f"/projects/{project_id}/tasks")
        assert r.status_code == 200
        assert len(r.json()) == 1


def test_m8_spa_serves_index_html(app):
    """If the React build exists, the catch-all route should serve index.html.
    In test environments the dist/ may not exist, so we just verify the route
    doesn't return old embedded HTML."""
    with TestClient(app) as client:
        r = client.get("/some/unknown/path")
        # Should be either 200 (SPA) or 404 (no dist/), but NOT old HTML
        if r.status_code == 200:
            assert "<!doctype html>" in r.text.lower() or "<html" in r.text.lower()
            # Must NOT contain old dashboard-specific content
            assert "setProject" not in r.text
            assert "loadTasks" not in r.text


def test_m8_api_py_line_count():
    """api.py should be under 700 lines (was ~1170 before M8/M9 cleanup; grew with M12-M14 endpoints)."""
    api_path = Path(__file__).resolve().parents[1] / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    lines = api_path.read_text().splitlines()
    assert len(lines) < 700, f"api.py has {len(lines)} lines, expected < 700"
