from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4

import sys

# Ensure repo root is importable when running under isolated envs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


def _wait_until(fn, timeout_s: float = 5.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    return None


@pytest.fixture(scope="module")
def containers():
    # Dockerless test harness:
    # - Redis: fakeredis (in-process)
    # - DB: sqlite (async)
    yield {
        "redis_url": "redis://unused",
        "pg_url": "sqlite+aiosqlite:///:memory:",
    }


@pytest.fixture()
def app(containers, monkeypatch):
    # Isolate spec hash inputs per-test.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        idx = td / "INDEX.md"
        m1 = td / "MILESTONE_1.md"
        m2 = td / "MILESTONE_2.md"
        m3 = td / "MILESTONE_3.md"
        m4 = td / "MILESTONE_4.md"
        m5 = td / "MILESTONE_5.md"
        ui = td / "UI_SPEC.md"
        idx.write_text("index", encoding="utf-8")
        m1.write_text("m1", encoding="utf-8")
        m2.write_text("m2", encoding="utf-8")
        m3.write_text("m3", encoding="utf-8")
        m4.write_text("m4", encoding="utf-8")
        m5.write_text("m5", encoding="utf-8")
        ui.write_text("ui", encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(idx))
        monkeypatch.setenv("ODP_SPEC_M1", str(m1))
        monkeypatch.setenv("ODP_SPEC_M2", str(m2))
        monkeypatch.setenv("ODP_SPEC_M3", str(m3))
        monkeypatch.setenv("ODP_SPEC_M4", str(m4))
        monkeypatch.setenv("ODP_SPEC_M5", str(m5))
        monkeypatch.setenv("ODP_UI_SPEC", str(ui))
        monkeypatch.setenv("ODP_REDIS_URL", containers["redis_url"])
        monkeypatch.setenv("ODP_FAKE_REDIS", "1")
        monkeypatch.setenv("ODP_DATABASE_URL", containers["pg_url"])
        monkeypatch.setenv("ODP_AUTO_MIGRATE", "1")
        monkeypatch.setenv("ODP_AGENT_TEST_MODE", "1")
        monkeypatch.setenv("ODP_ARTIFACT_DIR", str(td / "artifacts"))
        monkeypatch.setenv("ODP_WORKSPACE_DIR", str(td / "workspaces"))
        monkeypatch.setenv("ODP_REPO_ROOT", str(Path(__file__).resolve().parents[1]))

        from services.orchestrator.odp_orchestrator.api import create_app

        yield create_app(), {"idx": idx, "m1": m1, "ui": ui}


def test_task_lifecycle_to_commit(app):
    app_, _files = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m1"})
        assert r.status_code == 200
        task = r.json()
        task_id = UUID(task["task_id"])

        def _done():
            t = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
            return t["state"] in ("COMMIT", "ROLLBACK") and t

        t = _wait_until(_done, timeout_s=8.0)
        assert t is not None
        assert t["state"] == "COMMIT"


def test_gate_enforcement_spec_drift_rolls_back(app):
    app_, files = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "drift"})
        task = r.json()
        task_id = UUID(task["task_id"])

        # Force drift before the orchestrator completes.
        files["m1"].write_text("m1 changed", encoding="utf-8")

        def _done():
            t = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
            return t["state"] in ("COMMIT", "ROLLBACK") and t

        t = _wait_until(_done, timeout_s=8.0)
        assert t is not None
        assert t["state"] == "ROLLBACK"


@pytest.mark.asyncio
async def test_crash_recovery_resume_endpoint(app):
    app_, _files = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "resume"})
        task = r.json()
        task_id = UUID(task["task_id"])

        # Simulate a crash by setting the task state back to DISPATCH.
        # Mutate task state directly (fakeredis). Access the app's redis client.
        redis = app_.state.redis
        key = f"odp:{project_id}:task:{task_id}"
        raw = await redis.get(key)
        assert raw is not None
        import json

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        t = json.loads(raw)
        t["state"] = "DISPATCH"
        await redis.set(key, json.dumps(t))

        # Now resume.
        rr = client.post(f"/projects/{project_id}/resume")
        assert rr.status_code == 200

        def _done():
            t2 = client.get(f"/projects/{project_id}/tasks/{task_id}").json()
            return t2["state"] in ("COMMIT", "ROLLBACK") and t2

        t2 = _wait_until(_done, timeout_s=8.0)
        assert t2 is not None
        assert t2["state"] == "COMMIT"


def test_websocket_replay_and_live_events(app):
    app_, _files = app
    project_id = uuid4()

    with TestClient(app_) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "ws"})
        task = r.json()
        task_id = task["task_id"]

        with client.websocket_connect(f"/ws/projects/{project_id}/tasks/{task_id}?since=0") as ws:
            # We should at least see the initial task_created and some state transitions.
            first = ws.receive_text()
            assert "task_created" in first
            # Read a few more.
            got_states = 0
            for _ in range(20):
                msg = ws.receive_text()
                if "task_state" in msg:
                    got_states += 1
                if "COMMIT" in msg or "ROLLBACK" in msg:
                    break
            assert got_states >= 1
