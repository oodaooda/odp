# Milestone 6: Retrieval (pgvector) + Merge Automation + UI for Evidence/Promotion

## Goal
Add end-to-end usability features to make ODP closer to a real orchestration developer loop:
1) **Real retrieval/query** over memory using pgvector when available, with evidence linking
2) **Merge automation** beyond dry-run, with cleanup + traceability + gating
3) **UI build-out** for artifacts and agent-memory promotion workflows

## Scope

### 1) Retrieval (pgvector + evidence linking)
- Add API endpoint:
  - `GET /projects/{project_id}/memory/search?q=...&limit=...`
- Behavior:
  - If pgvector is available and embeddings are enabled:
    - Embed query
    - Retrieve nearest `memory_events` via vector similarity
  - Otherwise:
    - Fallback to simple text search over `memory_events.payload`
- Evidence linking:
  - Each result includes:
    - memory event metadata
    - associated artifacts for the same task_id (if any)

### 2) Merge automation beyond dry-run
- Add optional merge step after all gates pass:
  - `ODP_ENABLE_MERGE=1` to enable
- Requirements:
  - Only attempt merge when all gates pass
  - Record merge evidence artifact (log)
  - Cleanup worktrees/branches even on failure
  - Traceability: record merge commit hash (when performed) into task/memory event

### 3) UI for artifacts + promotion
- Expand UI pages to include:
  - Artifacts listing for a task
  - Pending agent memory list + promote/reject actions

## Deliverables
- [x] Retrieval/search endpoint with pgvector-first, text-fallback behavior
- [x] Evidence linking (search results include related artifacts)
- [x] Optional merge automation with evidence logs + traceability
- [x] UI for artifacts + promotion actions
- [x] Tests:
  - search fallback works in sqlite
  - promotion UI endpoints render
  - merge automation disabled by default; enabled in test mode is a no-op

## Evidence required
- `pytest -q` green
- No warnings
- Demo: search endpoint returns results + evidence links (in sqlite fallback)
