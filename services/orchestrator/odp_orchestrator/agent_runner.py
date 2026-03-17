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


async def _ensure_workspace_repo(
    *, repo_root: Path, workspace_root: Path, branch: str | None,
    github_repo: str | None = None, github_token: str | None = None,
) -> tuple[Path, str | None]:
    """Create an isolated workspace repo.

    - If github_repo is set: clone from GitHub (preferred for external projects).
    - Otherwise: git worktree checkout from local repo_root.
    - Test mode: no checkout (workspace_root used directly).
    """
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        return workspace_root, None

    ws_repo = workspace_root / "repo"
    print(f"[WORKSPACE] github_repo={github_repo} ws_repo={ws_repo} exists={ws_repo.exists()}", flush=True)
    if (ws_repo / ".git").exists():
        return ws_repo, branch

    # If a GitHub repo is configured, clone it instead of using a local worktree.
    if github_repo:
        if github_token:
            clone_url = f"https://x-access-token:****@github.com/{github_repo}.git"
        else:
            clone_url = f"https://github.com/{github_repo}.git"
        print(f"[WORKSPACE] cloning {clone_url} -> {ws_repo}", flush=True)
        # Use actual token in the real URL.
        real_url = f"https://x-access-token:{github_token}@github.com/{github_repo}.git" if github_token else clone_url
        rc, out = await _run_local_cmd(
            "git", "clone", "--depth", "1", real_url, str(ws_repo),
            cwd=workspace_root, timeout_s=120,
        )
        print(f"[WORKSPACE] clone rc={rc} out={out[:200]}", flush=True)
        if rc != 0:
            import logging
            logging.getLogger(__name__).warning("git clone failed: %s", out)
            # Fall through to worktree method.
        else:
            # Strip token from .git/config remote URL to avoid secret scanner hits.
            if github_token:
                await _run_local_cmd(
                    "git", "remote", "set-url", "origin",
                    f"https://github.com/{github_repo}.git",
                    cwd=ws_repo, timeout_s=10,
                )
            # Create a working branch if needed.
            if branch:
                await _run_local_cmd(
                    "git", "checkout", "-b", branch,
                    cwd=ws_repo, timeout_s=30,
                )
            return ws_repo, branch

    # Fallback: local git worktree from repo_root.
    cmd = ["git", "worktree", "add"]
    if branch:
        cmd += ["-b", branch]
    else:
        cmd += ["--detach"]
    cmd += [str(ws_repo), "HEAD"]

    rc, _out = await _run_local_cmd(*cmd, cwd=repo_root, timeout_s=60)
    if rc != 0:
        return repo_root, None

    return ws_repo, branch


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
    task_context: dict[str, Any] | None = None,
    feedback: str | None = None,
    github_repo: str | None = None,
    github_token: str | None = None,
) -> AgentResult:
    # Per-task workspace. QA and security reuse the engineer's workspace
    # (where the generated code lives) instead of a fresh clone.
    ws_root = cfg.workspaces_root / str(project_id) / str(task_id) / str(role)
    if role in (AgentRole.qa, AgentRole.security) and github_repo:
        eng_repo = (cfg.workspaces_root / str(project_id) / str(task_id) / "engineer" / "repo").resolve()
        if eng_repo.exists() and (eng_repo / ".git").exists():
            workspace = eng_repo
            work_branch = None
        else:
            # Engineer workspace not ready; fall back to own workspace.
            workspace, work_branch = await _ensure_workspace_repo(
                repo_root=cfg.repo_root, workspace_root=ws_root, branch=None,
                github_repo=github_repo, github_token=github_token,
            )
    else:
        ws_root = cfg.workspaces_root / str(project_id) / str(task_id) / str(role)
        branch = None
        if os.getenv("ODP_AGENT_TEST_MODE", "0") != "1" and role == AgentRole.engineer:
            branch = f"odp/task-{str(task_id)[:8]}"
        workspace, work_branch = await _ensure_workspace_repo(
            repo_root=cfg.repo_root, workspace_root=ws_root, branch=branch,
            github_repo=github_repo, github_token=github_token,
        )

    art_dir = cfg.artifacts_root / str(project_id) / str(task_id) / "agents" / str(role)
    art_dir.mkdir(parents=True, exist_ok=True)

    # Build agent env: inherit parent but strip secrets that agents should not see.
    _SECRET_PREFIXES = ("ODP_API_TOKEN", "ODP_RBAC_", "ODP_GITHUB_TOKEN", "ODP_GITHUB_WEBHOOK_SECRET", "ODP_DATABASE_URL", "ODP_ORCH_LLM_")
    env = {k: v for k, v in os.environ.items() if not any(k.startswith(p) for p in _SECRET_PREFIXES)}
    env.setdefault("PYTHONUNBUFFERED", "1")

    # Dual-provider support: map ODP_AGENT_LLM_* → ODP_LLM_* for agent subprocess.
    # This lets agents use a different LLM provider (e.g., OpenAI) than the orchestrator (e.g., Anthropic).
    for suffix in ("PROVIDER", "API_KEY", "MODEL", "MAX_TOKENS"):
        agent_val = os.getenv(f"ODP_AGENT_LLM_{suffix}")
        if agent_val:
            env[f"ODP_LLM_{suffix}"] = agent_val
    if expected_spec_hash:
        env["ODP_EXPECTED_SPEC_HASH"] = expected_spec_hash

    # Pass task context to agents via env (JSON-encoded).
    if task_context:
        import json as _json
        env["ODP_TASK_CONTEXT"] = _json.dumps(task_context)
    if feedback:
        env["ODP_AGENT_FEEDBACK"] = feedback

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

    # In unit-test mode, run agents in-process to keep pytest clean/stable (no asyncio subprocess
    # transports lingering during event-loop teardown).
    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        import contextlib
        import io

        # Inject task context into env for in-process agents too.
        if task_context:
            import json as _json
            os.environ["ODP_TASK_CONTEXT"] = _json.dumps(task_context)
        if feedback:
            os.environ["ODP_AGENT_FEEDBACK"] = feedback

        from services.agents.odp_agent.main import main as agent_main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = agent_main(["--role", str(role), "--workspace", str(workspace), "--artifacts", str(art_dir)])
        stdout = buf.getvalue()
        timed_out = False

        # Clean up injected env vars.
        os.environ.pop("ODP_TASK_CONTEXT", None)
        os.environ.pop("ODP_AGENT_FEEDBACK", None)
    else:
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

    async def _cleanup_git() -> None:
        if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
            return
        if os.getenv("ODP_GIT_CLEANUP", "1") != "1":
            return
        # Only cleanup if we created an isolated worktree under this role workspace.
        expected_repo = ws_root / "repo"
        if workspace != expected_repo:
            return
        await _run_local_cmd("git", "worktree", "remove", "--force", str(expected_repo), cwd=cfg.repo_root, timeout_s=60)
        if work_branch:
            await _run_local_cmd("git", "branch", "-D", str(work_branch), cwd=cfg.repo_root, timeout_s=60)

    # Always capture combined stdout as evidence.
    stdout_uri = _write_text(art_dir / "agent_stdout.txt", stdout)

    if timed_out:
        await _cleanup_git()
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

    await _cleanup_git()
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
