from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from .events import now_ms
from .models import AgentResult, AgentRole


@dataclass(frozen=True)
class AgentRunConfig:
    repo_root: Path
    workspaces_root: Path
    artifacts_root: Path
    timeout_s: int = 1200


async def _run_local_cmd(*cmd: str, cwd: Path, timeout_s: int) -> tuple[int, str]:
    """Run a local command and return (rc, combined_output)."""
    p = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=os.environ.copy(),
    )
    try:
        out_b, _ = await asyncio.wait_for(p.communicate(), timeout=timeout_s)
    except TimeoutError:
        p.kill()
        return 124, "timeout"
    out = out_b.decode("utf-8", errors="replace") if isinstance(out_b, (bytes, bytearray)) else ""
    return int(p.returncode or 0), out


async def _ensure_workspace_repo(*, repo_root: Path, workspace_root: Path) -> Path:
    """Create an isolated workspace repo.

    In real mode we use a git worktree so agents can run git diff and tests without touching
    the orchestrator's working tree.

    In ODP_AGENT_TEST_MODE we skip the checkout to keep unit tests fast/deterministic.
    """
    workspace_root.mkdir(parents=True, exist_ok=True)

    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        return workspace_root

    ws_repo = workspace_root / "repo"
    # If already initialized, reuse.
    if (ws_repo / ".git").exists():
        return ws_repo

    ws_repo.parent.mkdir(parents=True, exist_ok=True)
    rc, out = await _run_local_cmd(
        "git",
        "worktree",
        "add",
        "--detach",
        str(ws_repo),
        "HEAD",
        cwd=repo_root,
        timeout_s=60,
    )
    if rc != 0:
        # Fall back to repo_root (still runs, but loses isolation). This should be rare and is
        # preferable to hard-failing the orchestrator in dev.
        return repo_root
    return ws_repo


def _write_text(path: Path, text_: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_, encoding="utf-8")
    return str(path)


async def run_agent(
    *,
    cfg: AgentRunConfig,
    project_id: UUID,
    task_id: UUID,
    role: AgentRole,
    expected_spec_hash: str | None = None,
) -> AgentResult:
    # Per-task, per-role isolated workspace.
    ws_root = cfg.workspaces_root / str(project_id) / str(task_id) / str(role)
    workspace = await _ensure_workspace_repo(repo_root=cfg.repo_root, workspace_root=ws_root)

    art_dir = cfg.artifacts_root / str(project_id) / str(task_id) / "agents" / str(role)
    art_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if expected_spec_hash:
        env["ODP_EXPECTED_SPEC_HASH"] = expected_spec_hash

    cmd = [
        "python",
        "-m",
        "services.agents.odp_agent",
        "--role",
        str(role),
        "--workspace",
        str(workspace),
        "--artifacts",
        str(art_dir),
    ]

    p = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cfg.repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )

    timed_out = False
    try:
        stdout_b, _ = await asyncio.wait_for(p.communicate(), timeout=cfg.timeout_s)
    except TimeoutError:
        timed_out = True
        p.kill()
        stdout_b = b""

    stdout = stdout_b.decode("utf-8", errors="replace") if isinstance(stdout_b, (bytes, bytearray)) else ""

    # Always capture combined stdout as evidence.
    stdout_uri = _write_text(art_dir / "agent_stdout.txt", stdout)

    if timed_out:
        return AgentResult(
            project_id=project_id,
            task_id=task_id,
            role=role,
            ok=False,
            summary=f"{role} timed out",
            artifacts=[{"type": "log", "uri": stdout_uri}],
            logs=["timeout"],
            memory_entries=[],
            created_at_ms=now_ms(),
        )

    # Last line should be JSON.
    payload: dict[str, Any]
    try:
        last = stdout.strip().splitlines()[-1]
        payload = json.loads(last)
    except Exception:
        payload = {
            "ok": False,
            "summary": "agent output parse failure",
            "artifacts": [],
            "logs": [stdout[-4000:]],
        }

    artifacts = list(payload.get("artifacts") or [])
    artifacts.append({"type": "log", "uri": stdout_uri})

    return AgentResult(
        project_id=project_id,
        task_id=task_id,
        role=role,
        ok=bool(payload.get("ok")),
        summary=str(payload.get("summary")),
        artifacts=artifacts,
        logs=list(payload.get("logs") or []),
        memory_entries=list(payload.get("memory_entries") or []),
        created_at_ms=now_ms(),
    )
