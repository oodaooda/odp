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
        (td / "UI_SPEC.md").write_text("ui", encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(td / "INDEX.md"))
        monkeypatch.setenv("ODP_SPEC_M1", str(td / "MILESTONE_1.md"))
        monkeypatch.setenv("ODP_SPEC_M2", str(td / "MILESTONE_2.md"))
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


def test_m2_agent_artifacts_and_gates(app):
    app_, td = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m2"})
        assert r.status_code == 200
        task_id = UUID(r.json()["task_id"])

        def _done():
            t = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
            return t["state"] in ("COMMIT", "ROLLBACK") and t

        t = _wait_until(_done)
        assert t is not None
        assert t["state"] == "COMMIT"

        # Agent results recorded.
        assert any("agent_result:engineer" in k for k in t["agent_results"])
        assert any("agent_result:qa" in k for k in t["agent_results"])
        assert any("agent_result:security" in k for k in t["agent_results"])

        # Gate decisions recorded (assert phases present by key).
        gates = "\n".join(t["gate_decisions"])
        assert "phase_2_engineer" in gates
        assert "phase_3_qa" in gates
        assert "phase_4_security" in gates
        assert "phase_5_ws" in gates

        # Workspace isolation paths exist.
        ws = td / "workspaces" / str(project_id) / str(task_id)
        assert (ws / "engineer").exists()
        assert (ws / "qa").exists()
        assert (ws / "security").exists()

        # Artifact files exist.
        base = td / "artifacts" / str(project_id) / str(task_id) / "agents"
        assert (base / "engineer" / "engineer_diff.patch").exists()
        assert (base / "engineer" / "engineer_pytest.txt").exists()
        assert (base / "qa" / "qa_pytest.txt").exists()
        assert (base / "qa" / "qa_spec_hash.txt").exists()
        assert (base / "security" / "security_scan.txt").exists()
        assert (base / "security" / "dependency_sanity.txt").exists()
