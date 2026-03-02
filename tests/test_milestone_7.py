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
            ("MILESTONE_2.md", "m2"),
            ("MILESTONE_3.md", "m3"),
            ("MILESTONE_4.md", "m4"),
            ("MILESTONE_5.md", "m5"),
            ("MILESTONE_6.md", "m6"),
            ("MILESTONE_7.md", "m7"),
            ("UI_SPEC.md", "ui"),
        ]:
            (td / name).write_text(txt, encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(td / "INDEX.md"))
        monkeypatch.setenv("ODP_SPEC_M1", str(td / "MILESTONE_1.md"))
        monkeypatch.setenv("ODP_SPEC_M2", str(td / "MILESTONE_2.md"))
        monkeypatch.setenv("ODP_SPEC_M3", str(td / "MILESTONE_3.md"))
        monkeypatch.setenv("ODP_SPEC_M4", str(td / "MILESTONE_4.md"))
        monkeypatch.setenv("ODP_SPEC_M5", str(td / "MILESTONE_5.md"))
        monkeypatch.setenv("ODP_SPEC_M6", str(td / "MILESTONE_6.md"))
        monkeypatch.setenv("ODP_SPEC_M7", str(td / "MILESTONE_7.md"))
        monkeypatch.setenv("ODP_UI_SPEC", str(td / "UI_SPEC.md"))

        monkeypatch.setenv("ODP_FAKE_REDIS", "1")
        monkeypatch.setenv("ODP_REDIS_URL", "redis://unused")
        monkeypatch.setenv("ODP_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("ODP_AUTO_MIGRATE", "1")

        monkeypatch.setenv("ODP_AGENT_TEST_MODE", "1")
        monkeypatch.setenv("ODP_ARTIFACT_DIR", str(td / "artifacts"))
        monkeypatch.setenv("ODP_WORKSPACE_DIR", str(td / "workspaces"))
        monkeypatch.setenv("ODP_REPO_ROOT", str(Path(__file__).resolve().parents[1]))

        # Enable auth
        monkeypatch.setenv("ODP_API_TOKEN", "secret")

        from services.orchestrator.odp_orchestrator.api import create_app

        yield create_app()


def test_m7_auth_gating(app):
    project_id = uuid4()
    headers = {"authorization": "Bearer secret"}

    with TestClient(app) as client:
        # healthz/metrics should be open
        assert client.get("/healthz").status_code == 200
        assert client.get("/metrics").status_code == 200

        # Without auth, other endpoints should be blocked
        assert client.get("/").status_code == 401
        assert client.post(f"/projects/{project_id}/tasks", json={"title": "x"}).status_code == 401

        # With auth, should work
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "x"}, headers=headers)
        assert r.status_code == 200
