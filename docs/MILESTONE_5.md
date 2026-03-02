# Milestone 5: Real Embeddings (Config-Gated) + Git Workflow Hardening + UI Build-out

## Goal
Move ODP from a milestone-complete prototype into a more end-to-end usable dev platform by adding:
1) A **real embedding pipeline** (optional, config-gated; only uses pgvector when present)
2) A **hardened git workflow** (branch-per-task, strict worktree lifecycle, merge gating)
3) A **UI build-out** beyond the minimal Milestone-1 dashboard mock

## Scope

### 1) Embeddings pipeline (optional/config-gated)
- Add an embeddings module that can be enabled via environment/config.
- Default behavior remains **disabled** (no external calls; no secrets required).
- When enabled and pgvector is present:
  - Compute embeddings for promoted/summarized memory events.
  - Upsert into `vector_index`.
- Providers:
  - `disabled` (default)
  - `openai` (requires API key; model configurable)

### 2) Git workflow hardening
- Engineer agent work happens on a **branch per task** (no writes to main working tree).
- Worktrees are created per task and cleaned up deterministically.
- Merge gating:
  - Merge is only attempted if all gates pass.
  - For Milestone 5, merge can remain a **no-op / dry-run** unless explicitly enabled.

### 3) UI build-out
- Expand the web UI to include:
  - project/task list
  - task detail view (events + state)
  - evidence/artifacts view
  - pending agent memory view + promotion actions

## Deliverables
- [x] Embeddings module + config plumbing
- [x] Vector index upserts only when enabled + pgvector available
- [x] Git branch-per-task + strict worktree create/remove
- [x] UI pages for tasks/evidence/pending memory
- [x] Tests:
  - embeddings disabled is a true no-op
  - embeddings enabled without key fails gracefully (no crash)
  - worktree cleanup does not leak directories in runtime
  - UI endpoints serve successfully

## Evidence required
- `pytest -q` green
- No warnings in test output
- Screenshots or HTML snapshots of new UI pages (optional)
