from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID, uuid4

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Minimal spec files
        for name, txt in [
            ("INDEX.md", "index"),
            ("MILESTONE_1.md", "m1"),
            ("MILESTONE_2.md", "m2"),
            ("MILESTONE_3.md", "m3"),
            ("MILESTONE_4.md", "m4"),
            ("MILESTONE_5.md", "m5"),
            ("UI_SPEC.md", "ui"),
        ]:
            (td / name).write_text(txt, encoding="utf-8")

        monkeypatch.setenv("ODP_SPEC_INDEX", str(td / "INDEX.md"))
        monkeypatch.setenv("ODP_SPEC_M1", str(td / "MILESTONE_1.md"))
        monkeypatch.setenv("ODP_SPEC_M2", str(td / "MILESTONE_2.md"))
        monkeypatch.setenv("ODP_SPEC_M3", str(td / "MILESTONE_3.md"))
        monkeypatch.setenv("ODP_SPEC_M4", str(td / "MILESTONE_4.md"))
        monkeypatch.setenv("ODP_SPEC_M5", str(td / "MILESTONE_5.md"))
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


def test_m4_chat_compaction_writes_summary_memory_event(app):
    project_id = uuid4()

    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m4"})
        assert r.status_code == 200
        task_id = UUID(r.json()["task_id"])

        # Wait for background task to settle before writing chat messages.
        import time
        time.sleep(0.5)

        # Write some chat messages.
        for i in range(6):
            c = client.post(
                f"/projects/{project_id}/chat",
                json={"text": f"msg-{i}", "task_id": str(task_id)},
            )
            assert c.status_code == 200

        # Allow SQLite writes to flush.
        time.sleep(0.3)

        cc = client.post(
            f"/projects/{project_id}/chat/compact",
            json={"task_id": str(task_id), "keep_last": 2, "compact_n": 10},
        )
        assert cc.status_code == 200
        assert cc.json()["compacted"] >= 1

        # Compaction is additive; allow a short eventual-consistency window while background task
        # transitions complete.
        t0 = time.time()
        while True:
            ev = client.get(
                f"/projects/{project_id}/memory-events",
                params={"task_id": str(task_id), "limit": 1000},
            )
            assert ev.status_code == 200
            events = ev.json()["events"]
            if any(e["type"] == "summary" for e in events):
                break
            if time.time() - t0 > 5.0:
                assert False, f"summary not found in memory-events: {events}"
            time.sleep(0.1)
