# Milestone 4: Compaction + Vector Index (pgvector) + Branch Isolation Hardening

## Goal
Complete the SRD/ICD memory model by adding:
- Auditable chat compaction (summaries + linkage to compacted messages)
- Derived vector index (pgvector) for promoted memory events
- Stronger git sandboxing: branch/worktree per task with no writes to main

## Scope
### 1) Chat compaction (auditable)
- Add API endpoint:
  - `POST /projects/{project_id}/chat/compact` (optionally scoped to task_id)
- Behavior:
  - Select oldest N chat messages beyond a threshold.
  - Write a `memory_events` row of type `summary` with:
    - `compaction_of`: message/event ids compacted
    - summary text
  - Preserve original rows; compaction is additive and auditable.

### 2) Vector index (derived)
- Add table `vector_index` with (event_id, embedding vector, created_at).
- Provide orchestrator job:
  - On promotion/summary, compute embedding and upsert into vector_index.
- In dev/test environments without pgvector, system continues without vector support.

### 3) Git branch/worktree hardening
- For each task create a detached worktree/branch:
  - Engineer agent operates only inside that worktree.
- Orchestrator never writes to main working tree.
- Evidence includes:
  - worktree path
  - commit hash (optional)

## Non-goals
- No multi-node agent pool.
- No full UI dashboard rebuild.

## Deliverables
- [x] Compaction + summary audit trail
- [x] Vector index derived from promoted events (best-effort; pgvector optional)
- [x] Hardened workspace git behavior
- [x] Tests for compaction + vector fallback

## Evidence required
- Compaction summary + linkage stored
- Vector index rows created when pgvector available (or graceful skip)
- `pytest -q` green
