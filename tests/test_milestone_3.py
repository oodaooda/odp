from __future__ import annotations

import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


def _wait_until(fn, timeout_s: float = 8.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    return None


@pytest.fixture()
def app(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Minimal spec files
        (td / "INDEX.md").write_text("index", encoding="utf-8")
        (td / "MILESTONE_1.md").write_text("m1", encoding="utf-8")
        (td / "MILESTONE_2.md").write_text("m2", encoding="utf-8")
        (td / "MILESTONE_3.md").write_text("m3", encoding="utf-8")
        (td / "MILESTONE_4.md").write_text("m4", encoding="utf-8")
        (td / "UI_SPEC.md").write_text("ui", encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(td / "INDEX.md"))
        monkeypatch.setenv("ODP_SPEC_M1", str(td / "MILESTONE_1.md"))
        monkeypatch.setenv("ODP_SPEC_M2", str(td / "MILESTONE_2.md"))
        monkeypatch.setenv("ODP_SPEC_M3", str(td / "MILESTONE_3.md"))
        monkeypatch.setenv("ODP_SPEC_M4", str(td / "MILESTONE_4.md"))
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

        yield create_app(), td


def test_m3_pending_agent_memory_and_promotion(app):
    app_, _td = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m3"})
        assert r.status_code == 200
        task_id = UUID(r.json()["task_id"])

        def _done():
            t = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
            return t["state"] in ("COMMIT", "ROLLBACK") and t

        t = _wait_until(_done)
        assert t is not None
        assert t["state"] == "COMMIT"

        # Pending agent memory should exist.
        rr = client.get(f"/projects/{project_id}/agent-memory", params={"status": "pending", "task_id": str(task_id)})
        assert rr.status_code == 200
        rows = rr.json()["agent_memory"]
        assert len(rows) >= 1
        agent_memory_id = rows[0]["agent_memory_id"]

        # Promote one entry.
        pr = client.post(
            f"/projects/{project_id}/agent-memory/{agent_memory_id}/promote",
            json={"decision": "approved", "note": "ok"},
        )
        assert pr.status_code == 200

        # It should now show up as approved.
        rr2 = client.get(
            f"/projects/{project_id}/agent-memory",
            params={"status": "approved", "task_id": str(task_id)},
        )
        assert rr2.status_code == 200
        approved = rr2.json()["agent_memory"]
        assert any(r["agent_memory_id"] == agent_memory_id for r in approved)

        # Chat round-trip
        c1 = client.post(f"/projects/{project_id}/chat", json={"text": "hello", "task_id": str(task_id)})
        assert c1.status_code == 200
        c2 = client.get(f"/projects/{project_id}/chat", params={"task_id": str(task_id), "limit": 10})
        assert c2.status_code == 200
        msgs = c2.json()["messages"]
        assert any(m["text"] == "hello" for m in msgs)
