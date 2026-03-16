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

        # Enable embeddings provider but do NOT provide API key; should be a no-op.
        monkeypatch.setenv("ODP_EMBEDDINGS_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        monkeypatch.setenv("ODP_AGENT_TEST_MODE", "1")
        monkeypatch.setenv("ODP_ARTIFACT_DIR", str(td / "artifacts"))
        monkeypatch.setenv("ODP_WORKSPACE_DIR", str(td / "workspaces"))
        monkeypatch.setenv("ODP_REPO_ROOT", str(Path(__file__).resolve().parents[1]))

        from services.orchestrator.odp_orchestrator.api import create_app

        yield create_app(), td


def test_m5_ui_pages_and_embeddings_graceful(app):
    app_, _td = app
    project_id = uuid4()

    with TestClient(app_) as client:
        # Basic UI endpoints
        r0 = client.get("/")
        assert r0.status_code == 200

        # SPA serves at root (React handles client-side routing).
        r1 = client.get("/")
        assert r1.status_code == 200

        # Create a task
        r = client.post(f"/projects/{project_id}/tasks", json={"title": "m5"})
        assert r.status_code == 200
        task_id = UUID(r.json()["task_id"])

        # Task API endpoint works.
        r2 = client.get(f"/projects/{project_id}/tasks/{task_id}")
        assert r2.status_code == 200

        # Trigger a summary memory event (compaction) which would attempt embeddings.
        for i in range(3):
            client.post(f"/projects/{project_id}/chat", json={"text": f"msg-{i}", "task_id": str(task_id)})
        cc = client.post(
            f"/projects/{project_id}/chat/compact",
            json={"task_id": str(task_id), "keep_last": 1, "compact_n": 10},
        )
        assert cc.status_code == 200
