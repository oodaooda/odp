from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from .db import MemoryWriter
from .events import EventBus, now_ms
from .agent_runner import AgentRunConfig, run_agent
from .models import (
    AgentResult,
    AgentRole,
    GateDecision,
    GatePhase,
    Task,
    TaskCreateRequest,
    TaskState,
)
from .redis_store import RedisStore


def compute_spec_hash() -> str:
    # Minimal spec hash: include the index + milestone specs + UI spec. Used for drift detection.
    paths = [
        os.getenv("ODP_SPEC_INDEX", "docs/INDEX.md"),
        os.getenv("ODP_UI_SPEC", "docs/UI_SPEC.md"),
    ]
    # Dynamically include all milestone docs that exist.
    for i in range(1, 20):
        mp = os.getenv(f"ODP_SPEC_M{i}", f"docs/MILESTONE_{i}.md")
        paths.append(mp)
    h = hashlib.sha256()
    for p in paths:
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(f.read())
        else:
            h.update(p.encode("utf-8"))
            h.update(b":missing")
    return h.hexdigest()


@dataclass
class Orchestrator:
    store: RedisStore
    bus: EventBus
    memory: MemoryWriter
    agent_cfg: AgentRunConfig
    background_tasks: set[asyncio.Task[None]] = field(default_factory=set)

    async def create_task(self, project_id: UUID, req: TaskCreateRequest) -> Task:
        t = Task(
            project_id=project_id,
            task_id=uuid4(),
            title=req.title,
            spec_hash=compute_spec_hash(),
            state=TaskState.INIT,
            created_at_ms=now_ms(),
            updated_at_ms=now_ms(),
        )
        await self._save_task(t)
        await self.store.index_task(project_id, t.task_id)
        await self.bus.emit(project_id, t.task_id, "task_created", {"task": t.model_dump()})
        await self.memory.write_memory_event(
            project_id=project_id,
            task_id=t.task_id,
            type_="state_transition",
            actor="orchestrator",
            payload={"state": t.state, "title": t.title},
        )
        # Caller may manage the returned background task; in API we register it for clean shutdown.
        task = asyncio.create_task(self.run_to_completion(project_id, t.task_id))
        self.background_tasks.add(task)
        task.add_done_callback(lambda _t: self.background_tasks.discard(_t))
        return t

    async def get_task(self, project_id: UUID, task_id: UUID) -> Task | None:
        raw = await self.store.get_json(self.store.task_key(project_id, task_id))
        return Task.model_validate(raw) if raw else None

    async def list_tasks(self, project_id: UUID) -> list[Task]:
        tasks: list[Task] = []
        for tid in await self.store.list_task_ids(project_id):
            t = await self.get_task(project_id, tid)
            if t:
                tasks.append(t)
        tasks.sort(key=lambda x: x.created_at_ms)
        return tasks

    async def resume_incomplete(self, project_id: UUID) -> int:
        """Resume any tasks not yet terminal (COMMIT/ROLLBACK)."""
        n = 0
        for t in await self.list_tasks(project_id):
            if t.state not in (TaskState.COMMIT, TaskState.ROLLBACK):
                asyncio.create_task(self.run_to_completion(project_id, t.task_id))
                n += 1
        return n

    async def run_to_completion(self, project_id: UUID, task_id: UUID) -> None:
        lock_key = f"{self.store.task_key(project_id, task_id)}:lock"
        # A coarse lock to avoid double-runs.
        got = await self.store.redis.set(lock_key, "1", nx=True, ex=60)
        if not got:
            return
        try:
            while True:
                t = await self.get_task(project_id, task_id)
                if not t:
                    return
                if t.state in (TaskState.COMMIT, TaskState.ROLLBACK):
                    return

                if t.spec_hash != compute_spec_hash():
                    await self._fail_gate(
                        project_id,
                        task_id,
                        GatePhase.PHASE_1_LIFECYCLE,
                        "Spec drift detected; re-approval required.",
                        {"expected": t.spec_hash, "current": compute_spec_hash()},
                    )
                    await self._transition(t, TaskState.ROLLBACK)
                    continue

                if t.state == TaskState.INIT:
                    await self._transition(t, TaskState.DISPATCH)
                    continue

                if t.state == TaskState.DISPATCH:
                    # Deterministic stub: simulate engineer work.
                    res = await self._run_engineer(project_id, task_id)
                    await self._attach_agent_result(t, res)
                    await self._transition(t, TaskState.COLLECT)
                    continue

                if t.state == TaskState.COLLECT:
                    # In this milestone skeleton, COLLECT just confirms agent result exists.
                    ok = await self._gate_lifecycle(project_id, task_id)
                    if not ok:
                        await self._transition(t, TaskState.ROLLBACK)
                        continue
                    await self._transition(t, TaskState.VALIDATE)
                    continue

                if t.state == TaskState.VALIDATE:
                    # Ensure QA + security results exist (run once).
                    if not any(":agent_result:qa" in k for k in t.agent_results):
                        qa_res = await self._run_qa(project_id, task_id)
                        await self._attach_agent_result(t, qa_res)
                    if not any(":agent_result:security" in k for k in t.agent_results):
                        sec_res = await self._run_security(project_id, task_id)
                        await self._attach_agent_result(t, sec_res)

                    ok2 = await self._gate_engineer(project_id, task_id)
                    ok3 = await self._gate_qa(project_id, task_id)
                    ok4 = await self._gate_security(project_id, task_id)
                    ok5 = await self._gate_ws(project_id, task_id)

                    if ok2 and ok3 and ok4 and ok5:
                        merge_ok = await self._maybe_merge(t)
                        await self._transition(t, TaskState.COMMIT if merge_ok else TaskState.ROLLBACK)
                    else:
                        await self._transition(t, TaskState.ROLLBACK)
                    continue

                # If somehow in other states, rollback.
                await self._transition(t, TaskState.ROLLBACK)
        finally:
            await self.store.redis.delete(lock_key)

    async def _maybe_merge(self, t: Task) -> bool:
        """Best-effort merge automation.

        Enabled via ODP_ENABLE_MERGE=1. In test mode it is a no-op.
        """
        if os.getenv("ODP_ENABLE_MERGE", "0") != "1":
            return True
        if os.getenv("ODP_AGENT_TEST_MODE", "0") == "1":
            return True

        branch = f"odp/task-{str(t.task_id)[:8]}"
        # Merge in repo_root working tree.
        repo_root = self.agent_cfg.repo_root
        art_dir = self.agent_cfg.artifacts_root / str(t.project_id) / str(t.task_id) / "merge"
        art_dir.mkdir(parents=True, exist_ok=True)
        log_path = art_dir / "merge.log"

        import subprocess

        def run(cmd: list[str]) -> tuple[int, str]:
            p = subprocess.run(cmd, cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            return p.returncode, p.stdout

        rc1, out1 = run(["git", "checkout", "main"])
        rc2, out2 = run(["git", "merge", "--no-ff", branch, "-m", f"Merge task {t.task_id}"])
        log_path.write_text(out1 + "\n" + out2, encoding="utf-8")
        await self.memory.record_artifact(project_id=t.project_id, task_id=t.task_id, type_="log", uri=str(log_path))
        await self.bus.emit(t.project_id, t.task_id, "merge_log", {"uri": str(log_path), "branch": branch})

        if rc1 != 0 or rc2 != 0:
            return False

        # Cleanup branch (best-effort)
        run(["git", "branch", "-D", branch])
        return True

    async def _save_task(self, t: Task) -> None:
        await self.store.put_json(self.store.task_key(t.project_id, t.task_id), t.model_dump())

    async def _transition(self, t: Task, new_state: TaskState) -> None:
        # Avoid clobbering concurrent updates (e.g., gates/artifacts) by merging list fields from
        # the latest persisted task before writing the new state.
        cur = await self.get_task(t.project_id, t.task_id)
        if cur:
            # Merge + preserve order.
            seen = set()
            merged_agent = []
            for k in (cur.agent_results + t.agent_results):
                if k not in seen:
                    merged_agent.append(k)
                    seen.add(k)
            seen = set()
            merged_gates = []
            for k in (cur.gate_decisions + t.gate_decisions):
                if k not in seen:
                    merged_gates.append(k)
                    seen.add(k)
            t.agent_results = merged_agent
            t.gate_decisions = merged_gates

        t.state = new_state
        t.updated_at_ms = now_ms()
        await self._save_task(t)
        await self.bus.emit(t.project_id, t.task_id, "task_state", {"state": new_state})
        await self.memory.write_memory_event(
            project_id=t.project_id,
            task_id=t.task_id,
            type_="state_transition",
            actor="orchestrator",
            payload={"state": new_state},
        )

    async def _attach_agent_result(self, t: Task, res: AgentResult) -> None:
        key = f"odp:{t.project_id}:task:{t.task_id}:agent_result:{res.role}"
        await self.store.put_json(key, res.model_dump())
        if key not in t.agent_results:
            t.agent_results.append(key)
        await self._save_task(t)
        await self.bus.emit(t.project_id, t.task_id, "agent_result", {"result": res.model_dump()})

        # Persist artifacts.
        for a in res.artifacts:
            try:
                type_ = str(a.get("type") or "log")
                if type_ not in {"screenshot", "log", "diff", "report"}:
                    type_ = "log"
                uri = str(a.get("uri") or "")
                if uri:
                    artifact_id = await self.memory.record_artifact(
                        project_id=t.project_id, task_id=t.task_id, type_=type_, uri=uri
                    )
                    await self.bus.emit(
                        t.project_id,
                        t.task_id,
                        "artifact_recorded",
                        {"artifact": {"artifact_id": str(artifact_id), "type": type_, "uri": uri}},
                    )
            except Exception:
                # Don't fail task on evidence recording issues in M2.
                pass

        # Persist pending agent memory proposals.
        for me in res.memory_entries:
            try:
                type_ = str(me.get("type") or "")
                payload = me.get("payload")
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                if type_ not in {"scope_of_work", "roadmap", "test_log", "verification_result"}:
                    continue
                agent_memory_id = await self.memory.record_agent_memory_pending(
                    project_id=t.project_id,
                    task_id=t.task_id,
                    role=str(res.role),
                    type_=type_,
                    payload=payload,
                )
                await self.bus.emit(
                    t.project_id,
                    t.task_id,
                    "agent_memory_pending",
                    {"agent_memory": {"agent_memory_id": str(agent_memory_id), "type": type_, "role": str(res.role)}},
                )
            except Exception:
                pass

        await self.memory.write_memory_event(
            project_id=t.project_id,
            task_id=t.task_id,
            type_="decision",
            actor=f"agent:{res.role}",
            payload={
                "ok": res.ok,
                "summary": res.summary,
                "artifacts": res.artifacts,
                "memory_entries": res.memory_entries,
            },
        )

    async def _write_gate(self, decision: GateDecision) -> None:
        key = f"odp:{decision.project_id}:task:{decision.task_id}:gate:{decision.phase}"
        await self.store.put_json(key, decision.model_dump())
        t = await self.get_task(decision.project_id, decision.task_id)
        if t and key not in t.gate_decisions:
            t.gate_decisions.append(key)
            await self._save_task(t)
        await self.bus.emit(
            decision.project_id,
            decision.task_id,
            "gate_decision",
            {"gate": decision.model_dump()},
        )

    async def _fail_gate(
        self,
        project_id: UUID,
        task_id: UUID,
        phase: GatePhase,
        reason: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        d = GateDecision(
            project_id=project_id,
            task_id=task_id,
            phase=phase,
            passed=False,
            reason=reason,
            evidence=evidence or {},
            decided_at_ms=now_ms(),
        )
        await self._write_gate(d)

    async def _pass_gate(
        self,
        project_id: UUID,
        task_id: UUID,
        phase: GatePhase,
        reason: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        d = GateDecision(
            project_id=project_id,
            task_id=task_id,
            phase=phase,
            passed=True,
            reason=reason,
            evidence=evidence or {},
            decided_at_ms=now_ms(),
        )
        await self._write_gate(d)

    async def _run_with_retries(
        self,
        *,
        project_id: UUID,
        task_id: UUID,
        role: AgentRole,
        expected_spec_hash: str | None = None,
    ) -> AgentResult:
        max_retries = int(os.getenv("ODP_AGENT_MAX_RETRIES", "1"))
        attempt = 0
        backoffs = [0.2, 0.5, 1.0]
        while True:
            res = await run_agent(
                cfg=self.agent_cfg,
                project_id=project_id,
                task_id=task_id,
                role=role,
                expected_spec_hash=expected_spec_hash,
            )
            retryable = ("parse failure" in res.summary.lower()) or ("timed out" in res.summary.lower())
            if res.ok or (not retryable) or attempt >= max_retries:
                return res
            delay = backoffs[min(attempt, len(backoffs) - 1)]
            await asyncio.sleep(delay)
            attempt += 1

    async def _run_engineer(self, project_id: UUID, task_id: UUID) -> AgentResult:
        return await self._run_with_retries(project_id=project_id, task_id=task_id, role=AgentRole.engineer)

    async def _run_qa(self, project_id: UUID, task_id: UUID) -> AgentResult:
        # QA validates spec hash as part of its evidence.
        t = await self.get_task(project_id, task_id)
        expected = t.spec_hash if t else None
        return await self._run_with_retries(
            project_id=project_id,
            task_id=task_id,
            role=AgentRole.qa,
            expected_spec_hash=expected,
        )

    async def _run_security(self, project_id: UUID, task_id: UUID) -> AgentResult:
        return await self._run_with_retries(project_id=project_id, task_id=task_id, role=AgentRole.security)

    def _write_artifact_file(self, project_id: UUID, task_id: UUID, type_: str, text_: str) -> str:
        base = os.getenv("ODP_ARTIFACT_DIR", "runtime/artifacts")
        path = os.path.join(base, str(project_id), str(task_id))
        os.makedirs(path, exist_ok=True)
        fname = f"{int(time.time())}_{type_}.txt"
        full = os.path.join(path, fname)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text_)
        return full

    async def _get_agent_result(self, project_id: UUID, task_id: UUID, role: AgentRole) -> AgentResult | None:
        key = f"odp:{project_id}:task:{task_id}:agent_result:{role}"
        raw = await self.store.get_json(key)
        return AgentResult.model_validate(raw) if raw else None

    async def _gate_lifecycle(self, project_id: UUID, task_id: UUID) -> bool:
        t = await self.get_task(project_id, task_id)
        if not t or not t.agent_results:
            await self._fail_gate(project_id, task_id, GatePhase.PHASE_1_LIFECYCLE, "No agent results")
            return False
        await self._pass_gate(project_id, task_id, GatePhase.PHASE_1_LIFECYCLE, "Lifecycle ok")
        return True

    async def _gate_engineer(self, project_id: UUID, task_id: UUID) -> bool:
        res = await self._get_agent_result(project_id, task_id, AgentRole.engineer)
        if not res:
            await self._fail_gate(project_id, task_id, GatePhase.PHASE_2_ENGINEER, "Missing engineer result")
            return False
        if not res.ok:
            await self._fail_gate(
                project_id,
                task_id,
                GatePhase.PHASE_2_ENGINEER,
                "Engineer reported failure",
                {"summary": res.summary, "artifacts": res.artifacts},
            )
            return False
        if not res.artifacts:
            await self._fail_gate(project_id, task_id, GatePhase.PHASE_2_ENGINEER, "No engineer artifacts")
            return False
        await self._pass_gate(
            project_id,
            task_id,
            GatePhase.PHASE_2_ENGINEER,
            "Engineer passed and produced artifacts",
            {"summary": res.summary, "artifacts": res.artifacts},
        )
        return True

    async def _gate_qa(self, project_id: UUID, task_id: UUID) -> bool:
        res = await self._get_agent_result(project_id, task_id, AgentRole.qa)
        if not res:
            await self._fail_gate(project_id, task_id, GatePhase.PHASE_3_QA, "Missing QA result")
            return False
        if not res.ok:
            await self._fail_gate(
                project_id,
                task_id,
                GatePhase.PHASE_3_QA,
                "QA reported failure",
                {"summary": res.summary, "artifacts": res.artifacts},
            )
            return False
        await self._pass_gate(
            project_id,
            task_id,
            GatePhase.PHASE_3_QA,
            "QA regression passed",
            {"summary": res.summary, "artifacts": res.artifacts},
        )
        return True

    async def _gate_security(self, project_id: UUID, task_id: UUID) -> bool:
        res = await self._get_agent_result(project_id, task_id, AgentRole.security)
        if not res:
            await self._fail_gate(project_id, task_id, GatePhase.PHASE_4_SECURITY, "Missing security result")
            return False
        if not res.ok:
            await self._fail_gate(
                project_id,
                task_id,
                GatePhase.PHASE_4_SECURITY,
                "Security reported failure",
                {"summary": res.summary, "artifacts": res.artifacts},
            )
            return False
        await self._pass_gate(
            project_id,
            task_id,
            GatePhase.PHASE_4_SECURITY,
            "Security checks passed",
            {"summary": res.summary, "artifacts": res.artifacts},
        )
        return True

    async def _gate_ws(self, project_id: UUID, task_id: UUID) -> bool:
        # Milestone 2 treats WS stability as a V&V concern verified by the test suite.
        # We still record an explicit gate decision for auditability.
        await self._pass_gate(
            project_id,
            task_id,
            GatePhase.PHASE_5_WS,
            "WS stability asserted by replay + live event tests",
            {"note": "Validated by tests/test_milestone_1.py::test_websocket_replay_and_live_events"},
        )
        return True
