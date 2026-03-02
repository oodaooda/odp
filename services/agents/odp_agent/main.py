from __future__ import annotations

import argparse
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

    # Real mode: run local pytest and capture output.
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


def _compute_spec_hash(workspace: Path) -> str:
    # Must match orchestrator.compute_spec_hash().
    paths = [
        os.getenv("ODP_SPEC_INDEX", "docs/INDEX.md"),
        os.getenv("ODP_SPEC_M1", "docs/MILESTONE_1.md"),
        os.getenv("ODP_SPEC_M2", "docs/MILESTONE_2.md"),
        os.getenv("ODP_SPEC_M3", "docs/MILESTONE_3.md"),
        os.getenv("ODP_SPEC_M4", "docs/MILESTONE_4.md"),
        os.getenv("ODP_SPEC_M5", "docs/MILESTONE_5.md"),
        os.getenv("ODP_SPEC_M6", "docs/MILESTONE_6.md"),
        os.getenv("ODP_SPEC_M7", "docs/MILESTONE_7.md"),
        os.getenv("ODP_UI_SPEC", "docs/UI_SPEC.md"),
    ]
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


_SECRET_MARKERS = ["wt_", "sk-", "-----BEGIN PRIVATE KEY-----", "AWS_SECRET_ACCESS_KEY"]


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
