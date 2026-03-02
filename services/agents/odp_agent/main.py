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
    )


def _compute_spec_hash(workspace: Path) -> str:
    # Must match orchestrator.compute_spec_hash().
    paths = [
        os.getenv("ODP_SPEC_INDEX", "docs/INDEX.md"),
        os.getenv("ODP_SPEC_M1", "docs/MILESTONE_1.md"),
        os.getenv("ODP_SPEC_M2", "docs/MILESTONE_2.md"),
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
    )


_SECRET_MARKERS = ["wt_", "sk-", "-----BEGIN PRIVATE KEY-----", "AWS_SECRET_ACCESS_KEY"]


def _security(workspace: Path, artifacts_dir: Path) -> AgentOutput:
    if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
        sec_uri = _write(artifacts_dir / "security_scan.txt", "ok (test mode)\n")
        return AgentOutput(
            ok=True,
            summary="security test-mode: ok",
            artifacts=[{"type": "report", "uri": sec_uri}],
            logs=["security:test-mode"],
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

    out = "\n".join(hits) if hits else "no obvious secret markers found"
    sec_uri = _write(artifacts_dir / "security_scan.txt", out + "\n")
    ok = len(hits) == 0
    return AgentOutput(
        ok=ok,
        summary="security: " + ("ok" if ok else f"found {len(hits)} hits"),
        artifacts=[{"type": "report", "uri": sec_uri}],
        logs=[f"hits={len(hits)}"],
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
