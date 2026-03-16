from __future__ import annotations

import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


def _wait_done(client: TestClient, project_id: UUID, task_id: UUID, timeout_s: float = 8.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        t = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
        if t["state"] in ("COMMIT", "ROLLBACK"):
            return t
        time.sleep(0.05)
    return None


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
        monkeypatch.setenv("ODP_UI_SPEC", str(td / "UI_SPEC.md"))

        monkeypatch.setenv("ODP_FAKE_REDIS", "1")
        monkeypatch.setenv("ODP_REDIS_URL", "redis://unused")
        monkeypatch.setenv("ODP_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        monkeypatch.setenv("ODP_AUTO_MIGRATE", "1")

        monkeypatch.setenv("ODP_AGENT_TEST_MODE", "1")
        monkeypatch.setenv("ODP_ARTIFACT_DIR", str(td / "artifacts"))
        monkeypatch.setenv("ODP_WORKSPACE_DIR", str(td / "workspaces"))
        monkeypatch.setenv("ODP_REPO_ROOT", str(Path(__file__).resolve().parents[1]))

        # Merge enabled but test-mode should no-op.
        monkeypatch.setenv("ODP_ENABLE_MERGE", "1")

        from services.orchestrator.odp_orchestrator.api import create_app

        yield create_app()


def test_m6_search_fallback_and_ui(app):
    project_id = uuid4()

    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m6"})
        assert r.status_code == 200
        task_id = UUID(r.json()["task_id"])

        t = _wait_done(client, project_id, task_id)
        assert t is not None
        assert t["state"] in ("COMMIT", "ROLLBACK")

        # Search should return results with evidence linking field.
        s = client.get(f"/projects/{project_id}/memory/search", params={"q": "state", "limit": 5})
        assert s.status_code == 200
        results = s.json()["results"]
        assert isinstance(results, list)
        if results:
            assert "artifacts" in results[0]

        # SPA serves at root; task API works.
        ui1 = client.get("/")
        assert ui1.status_code == 200
        ui2 = client.get(f"/projects/{project_id}/tasks/{task_id}")
        assert ui2.status_code == 200
