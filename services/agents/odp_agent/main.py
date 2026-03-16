from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentOutput:
    ok: bool
    summary: str
    artifacts: list[dict[str, Any]]
    logs: list[str]
    memory_entries: list[dict[str, Any]]


def _run(cmd: list[str], cwd: Path, timeout_s: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def _write(path: Path, text_: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_, encoding="utf-8")
    return str(path)


def _get_task_context() -> dict[str, str]:
    """Read task context from ODP_TASK_CONTEXT env var."""
    raw = os.getenv("ODP_TASK_CONTEXT", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_feedback() -> str:
    """Read retry feedback from ODP_AGENT_FEEDBACK env var."""
    return os.getenv("ODP_AGENT_FEEDBACK", "")


def _read_workspace_files(workspace: Path, max_files: int = 20, max_chars: int = 50_000) -> str:
    """Read key source files from workspace for LLM context."""
    extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".toml", ".yaml", ".yml", ".md"}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "runtime"}
    files: list[tuple[str, str]] = []
    total = 0

    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        if any(sd in p.parts for sd in skip_dirs):
            continue
        if p.suffix.lower() not in extensions:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(p.relative_to(workspace))
        if total + len(content) > max_chars:
            remaining = max_chars - total
            if remaining > 200:
                files.append((rel, content[:remaining] + "\n... (truncated)"))
            break
        files.append((rel, content))
        total += len(content)
        if len(files) >= max_files:
            break

    parts = []
    for rel, content in files:
        parts.append(f"=== {rel} ===\n{content}\n")
    return "\n".join(parts)


def _build_engineer_prompt(workspace: Path) -> tuple[str, list[dict[str, str]]]:
    """Build the LLM prompt for code generation."""
    ctx = _get_task_context()
    title = ctx.get("title", "Unknown task")
    description = ctx.get("description", "")
    feedback = _get_feedback()

    system = (
        "You are an expert software engineer working on the ODP (Orchestrated Dev Platform) project. "
        "Your job is to implement the requested changes. Output ONLY a unified diff that can be applied "
        "with `git apply`. Do not include explanations outside the diff. The diff must be valid and complete.\n\n"
        "Rules:\n"
        "- Output a unified diff starting with --- and +++ lines\n"
        "- Use correct file paths relative to the workspace root\n"
        "- Include enough context lines (3+) for clean application\n"
        "- For new files, use /dev/null as the --- path\n"
        "- Do not introduce security vulnerabilities or hardcoded secrets\n"
        "- Ensure code follows existing project conventions\n"
    )

    workspace_files = _read_workspace_files(workspace)
    user_msg = f"## Task\n**{title}**\n\n{description}\n\n"
    if workspace_files:
        user_msg += f"## Current Workspace Files\n{workspace_files}\n\n"
    if feedback:
        user_msg += f"## Previous Attempt Feedback\nThe previous attempt failed. Fix the issues:\n{feedback}\n\n"
    user_msg += "## Output\nProvide ONLY a unified diff to implement this task."

    return system, [{"role": "user", "content": user_msg}]


def _apply_diff(workspace: Path, diff_text: str, artifacts_dir: Path) -> tuple[bool, str]:
    """Apply a unified diff to the workspace. Returns (success, log)."""
    # Extract diff from LLM response (it might have markdown fences).
    lines = diff_text.strip().splitlines()
    diff_lines: list[str] = []
    in_diff = False
    for line in lines:
        if line.startswith("```"):
            in_diff = not in_diff
            continue
        if line.startswith("diff --git") or line.startswith("---") or in_diff:
            diff_lines.append(line)
            in_diff = True
        elif in_diff:
            diff_lines.append(line)

    # If no diff markers found, treat entire response as diff.
    if not diff_lines:
        diff_lines = lines

    # Clean up stray blank lines between file diffs that break git apply.
    cleaned: list[str] = []
    for i, line in enumerate(diff_lines):
        # Skip blank lines that appear right before a new file diff header.
        if line.strip() == "" and i + 1 < len(diff_lines) and diff_lines[i + 1].startswith("---"):
            continue
        cleaned.append(line)

    clean_diff = "\n".join(cleaned) + "\n"
    diff_path = artifacts_dir / "llm_generated.patch"
    _write(diff_path, clean_diff)

    # Try git apply first; if it fails, fall back to writing files directly.
    result = _run(
        ["git", "apply", "--check", str(diff_path)],
        cwd=workspace, timeout_s=30,
    )
    if result.returncode != 0:
        # Fallback: parse the diff and write files directly.
        fb_ok, fb_log = _apply_diff_fallback(workspace, cleaned)
        if fb_ok:
            return True, "diff applied via fallback (direct file write)"
        return False, f"git apply --check failed: {result.stdout}\nFallback also failed: {fb_log}"

    result = _run(
        ["git", "apply", str(diff_path)],
        cwd=workspace, timeout_s=30,
    )
    if result.returncode != 0:
        return False, f"git apply failed:\n{result.stdout}"

    return True, "diff applied successfully"


def _apply_diff_fallback(workspace: Path, diff_lines: list[str]) -> tuple[bool, str]:
    """Fallback: parse unified diff for new files and write them directly."""
    current_file: str | None = None
    current_lines: list[str] = []
    files_written = 0

    def _flush() -> None:
        nonlocal files_written
        if current_file and current_lines:
            path = workspace / current_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(current_lines) + "\n")
            files_written += 1

    for line in diff_lines:
        if line.startswith("+++ b/"):
            _flush()
            current_file = line[6:]
            current_lines = []
        elif line.startswith("+++ /dev/null"):
            # File deletion — skip.
            _flush()
            current_file = None
            current_lines = []
        elif line.startswith("---") or line.startswith("@@") or line.startswith("diff --git"):
            continue
        elif line.startswith("+"):
            current_lines.append(line[1:])
        elif line.startswith("-"):
            continue  # Can only handle new file additions in fallback.
        elif not line.startswith("\\"):
            # Context line (no prefix) — include as-is.
            current_lines.append(line)
    _flush()

    if files_written > 0:
        return True, f"wrote {files_written} file(s)"
    return False, "no files extracted from diff"


def _engineer(workspace: Path, artifacts_dir: Path) -> AgentOutput:
    # Test-mode: deterministic + fast.
    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        diff_uri = _write(artifacts_dir / "engineer_diff.patch", "# no-op diff (test mode)\n")
        test_uri = _write(artifacts_dir / "engineer_pytest.txt", "4 passed (test mode)\n")
        return AgentOutput(
            ok=True,
            summary="engineer test-mode: produced diff + pytest artifacts",
            artifacts=[{"type": "diff", "uri": diff_uri}, {"type": "log", "uri": test_uri}],
            logs=["engineer:test-mode"],
            memory_entries=[
                {"type": "scope_of_work", "payload": {"summary": "(test mode) produce diff + run unit tests"}},
                {"type": "test_log", "payload": {"command": "pytest -q", "result": "pass (test mode)"}},
            ],
        )

    # Check if LLM is available.
    llm_provider = os.getenv("ODP_LLM_PROVIDER", "none").lower()
    if llm_provider != "none" and os.getenv("ODP_LLM_API_KEY", ""):
        return _engineer_with_llm(workspace, artifacts_dir)

    # Fallback: deterministic mode (no LLM) — run local pytest and capture output.
    diff = _run(["git", "diff"], cwd=workspace, timeout_s=60)
    diff_uri = _write(artifacts_dir / "engineer_diff.patch", diff.stdout)

    tests = _run(["python", "-m", "pytest", "-q"], cwd=workspace, timeout_s=1200)
    test_uri = _write(artifacts_dir / "engineer_pytest.txt", tests.stdout)

    ok = tests.returncode == 0
    return AgentOutput(
        ok=ok,
        summary="engineer: pytest " + ("passed" if ok else "failed"),
        artifacts=[{"type": "diff", "uri": diff_uri}, {"type": "log", "uri": test_uri}],
        logs=[f"pytest_rc={tests.returncode}"],
        memory_entries=[
            {"type": "test_log", "payload": {"command": "pytest -q", "returncode": tests.returncode}},
            {"type": "verification_result", "payload": {"ok": ok, "summary": "engineer unit tests"}},
        ],
    )


def _engineer_with_llm(workspace: Path, artifacts_dir: Path) -> AgentOutput:
    """Engineer agent with LLM code generation."""
    from services.orchestrator.odp_orchestrator.llm import call_llm

    system, messages = _build_engineer_prompt(workspace)
    logs: list[str] = ["engineer:llm-mode"]
    artifacts: list[dict[str, Any]] = []

    # Call LLM to generate code.
    try:
        loop = asyncio.new_event_loop()
        resp = loop.run_until_complete(call_llm(system=system, messages=messages))
        loop.close()
    except Exception as e:
        logs.append(f"llm_error={e}")
        return AgentOutput(
            ok=False, summary=f"engineer: LLM call failed: {e}",
            artifacts=artifacts, logs=logs,
            memory_entries=[{"type": "test_log", "payload": {"error": str(e)}}],
        )

    if resp is None:
        logs.append("llm_response=None")
        return AgentOutput(
            ok=False, summary="engineer: LLM returned no response",
            artifacts=artifacts, logs=logs,
            memory_entries=[],
        )

    logs.append(f"llm_model={resp.model}")
    logs.append(f"llm_tokens_in={resp.input_tokens}")
    logs.append(f"llm_tokens_out={resp.output_tokens}")
    logs.append(f"llm_latency_ms={resp.latency_ms}")
    logs.append(f"llm_cost_usd={resp.cost_estimate:.4f}")

    # Save raw LLM response.
    llm_uri = _write(artifacts_dir / "llm_response.txt", resp.text)
    artifacts.append({"type": "log", "uri": llm_uri})

    # Apply the generated diff.
    apply_ok, apply_log = _apply_diff(workspace, resp.text, artifacts_dir)
    logs.append(f"apply_ok={apply_ok}")
    if not apply_ok:
        logs.append(f"apply_log={apply_log}")
        return AgentOutput(
            ok=False, summary=f"engineer: diff apply failed: {apply_log[:200]}",
            artifacts=artifacts, logs=logs,
            memory_entries=[{"type": "test_log", "payload": {"apply_ok": False, "log": apply_log}}],
        )

    # Capture the diff after apply.
    diff = _run(["git", "diff"], cwd=workspace, timeout_s=60)
    diff_uri = _write(artifacts_dir / "engineer_diff.patch", diff.stdout)
    artifacts.append({"type": "diff", "uri": diff_uri})

    # Run tests to validate.
    tests = _run(["python", "-m", "pytest", "-q"], cwd=workspace, timeout_s=1200)
    test_uri = _write(artifacts_dir / "engineer_pytest.txt", tests.stdout)
    artifacts.append({"type": "log", "uri": test_uri})

    ok = tests.returncode == 0
    return AgentOutput(
        ok=ok,
        summary="engineer(llm): pytest " + ("passed" if ok else "failed"),
        artifacts=artifacts,
        logs=logs + [f"pytest_rc={tests.returncode}"],
        memory_entries=[
            {"type": "scope_of_work", "payload": {
                "summary": f"LLM-generated code ({resp.model})",
                "tokens": resp.input_tokens + resp.output_tokens,
                "cost_usd": resp.cost_estimate,
            }},
            {"type": "test_log", "payload": {"command": "pytest -q", "returncode": tests.returncode}},
            {"type": "verification_result", "payload": {"ok": ok, "summary": "engineer LLM unit tests"}},
        ],
    )


def _compute_spec_hash(workspace: Path) -> str:
    # Must match orchestrator.compute_spec_hash().
    paths = [
        os.getenv("ODP_SPEC_INDEX", "docs/INDEX.md"),
        os.getenv("ODP_UI_SPEC", "docs/UI_SPEC.md"),
    ]
    for i in range(1, 20):
        mp = os.getenv(f"ODP_SPEC_M{i}", f"docs/MILESTONE_{i}.md")
        paths.append(mp)
    import hashlib

    h = hashlib.sha256()
    for p in paths:
        fp = workspace / p if not os.path.isabs(p) else Path(p)
        if fp.exists():
            h.update(fp.read_bytes())
        else:
            h.update(str(p).encode("utf-8"))
            h.update(b":missing")
    return h.hexdigest()


def _qa(workspace: Path, artifacts_dir: Path) -> AgentOutput:
    expected = os.getenv("ODP_EXPECTED_SPEC_HASH")
    got = _compute_spec_hash(workspace) if expected else None
    spec_ok = (got == expected) if expected else True

    spec_report = "qa: no expected spec hash provided\n" if not expected else f"expected={expected}\nactual={got}\n"
    spec_uri = _write(artifacts_dir / "qa_spec_hash.txt", spec_report)

    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        qa_uri = _write(artifacts_dir / "qa_pytest.txt", "4 passed (test mode)\n")
        ok = True and spec_ok
        return AgentOutput(
            ok=ok,
            summary="qa test-mode: regression passed" + ("" if spec_ok else " (spec hash mismatch)"),
            artifacts=[{"type": "log", "uri": qa_uri}, {"type": "report", "uri": spec_uri}],
            logs=["qa:test-mode", f"spec_ok={spec_ok}"],
            memory_entries=[
                {"type": "verification_result", "payload": {"ok": ok, "spec_ok": spec_ok, "mode": "test"}},
            ],
        )

    tests = _run(["python", "-m", "pytest", "-q"], cwd=workspace, timeout_s=1200)
    qa_uri = _write(artifacts_dir / "qa_pytest.txt", tests.stdout)
    tests_ok = tests.returncode == 0
    ok = tests_ok and spec_ok
    summary = "qa: pytest " + ("passed" if tests_ok else "failed")
    if not spec_ok:
        summary += "; spec hash mismatch"
    return AgentOutput(
        ok=ok,
        summary=summary,
        artifacts=[{"type": "log", "uri": qa_uri}, {"type": "report", "uri": spec_uri}],
        logs=[f"pytest_rc={tests.returncode}", f"spec_ok={spec_ok}"],
        memory_entries=[
            {"type": "test_log", "payload": {"command": "pytest -q", "returncode": tests.returncode}},
            {"type": "verification_result", "payload": {"ok": ok, "spec_ok": spec_ok}},
        ],
    )


_SECRET_MARKERS = [
    "sk-",                          # OpenAI / Stripe keys
    "sk-ant-",                      # Anthropic keys
    "wt_",                          # Weights & Biases
    "ghp_", "gho_", "github_pat_",  # GitHub tokens
    "AKIA",                         # AWS access key ID prefix
    "AWS_SECRET_ACCESS_KEY",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "password=",
    "secret=",
    "token=",
    "api_key=",
]


def _dependency_sanity(workspace: Path) -> tuple[bool, str]:
    """Very lightweight local-only dependency sanity scan.

    Fails on clearly untrusted sources (VCS/URL/path). Warns on unpinned specs.
    """

    pyproject = workspace / "pyproject.toml"
    if not pyproject.exists():
        return True, "dependency_sanity: pyproject.toml missing; skipped\n"

    try:
        import tomllib  # py3.11+

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"dependency_sanity: failed to parse pyproject.toml: {e}\n"

    deps = (data.get("project") or {}).get("dependencies") or []
    if not isinstance(deps, list):
        return False, "dependency_sanity: project.dependencies is not a list\n"

    bad: list[str] = []
    warn: list[str] = []
    for d in deps:
        if not isinstance(d, str):
            continue
        ds = d.strip()
        # Disallow VCS/URL/path installs in this minimal local workflow.
        if "git+" in ds or "://" in ds or " @ " in ds or ds.startswith("-e "):
            bad.append(ds)
            continue
        # Very rough check for version pin/constraint.
        if not any(op in ds for op in ["==", ">=", "<=", "~=", "!=", ">", "<"]):
            warn.append(ds)

    ok = len(bad) == 0
    lines: list[str] = ["dependency_sanity:\n"]
    if bad:
        lines.append("FAIL: untrusted dependency sources detected:\n")
        lines.extend([f"- {x}\n" for x in bad])
    if warn:
        lines.append("WARN: dependencies without explicit version constraints:\n")
        lines.extend([f"- {x}\n" for x in warn])
    if not bad and not warn:
        lines.append("ok: all dependencies have version constraints\n")
    return ok, "".join(lines)


def _security(workspace: Path, artifacts_dir: Path) -> AgentOutput:
    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        sec_uri = _write(artifacts_dir / "security_scan.txt", "ok (test mode)\n")
        dep_uri = _write(artifacts_dir / "dependency_sanity.txt", "ok (test mode)\n")
        return AgentOutput(
            ok=True,
            summary="security test-mode: ok",
            artifacts=[
                {"type": "report", "uri": sec_uri},
                {"type": "report", "uri": dep_uri},
            ],
            logs=["security:test-mode"],
            memory_entries=[
                {"type": "verification_result", "payload": {"ok": True, "summary": "security scan (test mode)"}},
            ],
        )

    hits: list[str] = []
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in _SECRET_MARKERS:
            if m in txt:
                hits.append(f"{p}: marker {m}")

    secret_out = "\n".join(hits) if hits else "no obvious secret markers found"
    sec_uri = _write(artifacts_dir / "security_scan.txt", secret_out + "\n")
    secrets_ok = len(hits) == 0

    deps_ok, dep_report = _dependency_sanity(workspace)
    dep_uri = _write(artifacts_dir / "dependency_sanity.txt", dep_report)

    ok = secrets_ok and deps_ok
    summary_bits = []
    summary_bits.append("secrets ok" if secrets_ok else f"secrets: {len(hits)} hits")
    summary_bits.append("deps ok" if deps_ok else "deps: FAIL")

    return AgentOutput(
        ok=ok,
        summary="security: " + "; ".join(summary_bits),
        artifacts=[
            {"type": "report", "uri": sec_uri},
            {"type": "report", "uri": dep_uri},
        ],
        logs=[f"secret_hits={len(hits)}", f"deps_ok={deps_ok}"],
        memory_entries=[
            {
                "type": "verification_result",
                "payload": {"ok": ok, "secrets_ok": secrets_ok, "deps_ok": deps_ok, "secret_hits": len(hits)},
            },
        ],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["engineer", "qa", "security"])
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--artifacts", required=True)
    args = ap.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    artifacts = Path(args.artifacts).resolve()

    if args.role == "engineer":
        out = _engineer(workspace, artifacts)
    elif args.role == "qa":
        out = _qa(workspace, artifacts)
    else:
        out = _security(workspace, artifacts)

    # JSON protocol over stdout.
    print(json.dumps(out.__dict__, separators=(",", ":")))
    return 0 if out.ok else 2
