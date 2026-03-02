# Milestone 2: Real Agent Subprocesses + Local Infra + Evidence Artifacts

## Goal
Upgrade Milestone 1’s in-process stubs into a minimal **multi-process**, evidence-producing workflow that matches SRD constraints:
- Orchestrator remains authoritative.
- Agents run in isolated subprocesses/workspaces.
- Gates require **objective evidence** (test output / scan logs / diff).

## Scope
- Agent execution (subprocess-based) for 3 roles:
  - engineer
  - qa
  - security
- Per-task, per-role isolated workspace directory under `runtime/workspaces/<project>/<task>/<role>/`.
- Deterministic, local-only workflow:
  - Engineer produces a diff (can be no-op) and runs unit tests.
  - QA re-runs regression tests and validates spec hash.
  - Security performs secret-pattern + dependency sanity scan (lightweight, local).
- Local infra via docker-compose for **Redis + Postgres** (dev), with Postgres schema init.
- Artifact capture:
  - Store gate evidence artifacts under `runtime/artifacts/<project>/<task>/`.
  - Record artifact metadata in DB (`artifacts` table) and emit WS events.

## Non-goals
- No Kubernetes.
- No distributed agent pool.
- No real VCS merge automation.
- No embeddings/vector retrieval.
- No full UI build (dashboard remains minimal).

## Deliverables
- [x] Agent runner
  - Orchestrator spawns `python -m ...` agent entrypoints as subprocesses.
  - Captures stdout/stderr to artifact files.
  - Enforces timeouts.
  - Produces `AgentResult` with artifacts + logs.

- [x] Workspaces
  - Create per-role workspace directories per task.
  - Ensure agents cannot write to orchestrator memory store directly.

- [x] Gates (must pass)
  - Phase 1: lifecycle tests (existing)
  - Phase 2: engineer evidence
    - `pytest -q` output captured
    - diff artifact produced
  - Phase 3: QA evidence
    - `pytest -q` output captured
  - Phase 4: security evidence
    - secret scan report captured
  - Phase 5: WS stability
    - existing replay + live event tests

- [x] Local infra
  - `infra/docker-compose.yml` includes Redis + Postgres.
  - Postgres is configured for local dev (pgvector optional; tolerate absence).

- [x] Tests
  - Agent subprocess execution and result collection
  - Workspace isolation paths exist
  - Gate evidence artifacts exist and are recorded
  - Crash recovery still works

## Evidence required
- Test output logs (engineer + QA)
- Security scan output
- Diff artifact
- WS event transcript (at least replay + terminal state)

## Open questions
- Agent protocol: JSON over stdout vs file drop.
- Timeout defaults per role.
