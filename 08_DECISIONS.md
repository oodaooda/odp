# Decisions & Policies

## 1. Data Retention & Privacy
- Default retention: 12 months.
- Archive after 90 days of inactivity (read-only).
- Purge only by explicit admin action (audit headers retained).
- UI must provide archive/purge buttons with confirmation.

## 2. Project Lifecycle
- States: active → archived → frozen → deleted.
- Archived: read-only and searchable.
- Frozen: no new tasks; admin review only.
- Deleted: content removed; audit headers retained.
- UI must provide state-change buttons with confirmation.

## 3. Access Control (RBAC)
- Roles: owner, admin, operator, viewer.
- owner/admin: gate overrides, memory promotion, delete/purge.
- operator: chat + create tasks, no merges.
- viewer: read-only.

## 4. Rate Limiting / Abuse Controls
- Per-project concurrent task cap (start at 5).
- Per-agent tool-call cap per task.
- Orchestrator rejects work if gate backlog exceeds threshold.

## 5. Failure Recovery
- Checkpoint state transitions to Redis + Postgres.
- Resume on restart; re-dispatch only idempotent work.
- Auto-retry with exponential backoff (max 3).

## 6. Spec Drift Detection
- Record spec hash at task start.
- If specs change mid-task, mark task stale and require re-approval.

## 7. Artifact Storage
- Local-only for now: `runtime/artifacts/<project>/<task>/`.
- Store URI + hash in DB for integrity.

## 8. Dashboard Controls
- Archive, freeze, delete, purge, gate override, and memory promotion actions
  must require explicit confirmation.

## 9. Chat Compaction
- Chat has a finite context window.
- Orchestrator must apply compaction when context exceeds limit.
- Compaction produces a summary memory event linked to original messages.
 - Summary must include: Decisions, Open Questions, Tasks, Evidence, Risks.
 - Compaction is auditable and never deletes original messages.
