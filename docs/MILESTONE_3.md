# Milestone 3: Agent Memory (Pending) + Promotion + Chat History + Retry

## Goal
Extend the Milestone 2 multi-process workflow with **auditable, orchestrator-controlled memory** and improved reliability:
- Agents can *propose* structured memory entries (scope/roadmap/verification logs) as part of their subprocess result.
- Orchestrator is still the **only writer** to source-of-truth memory events.
- Orchestrator records proposed entries into a **pending** table and supports **promotion** (approve/reject).
- Chat history is queryable per project/task.
- Basic retry/backoff is implemented for agent subprocess runs.

## Scope
### 1) Pending agent memory
- Add Postgres/SQLite tables:
  - `agent_memory_pending` (agent-proposed entries)
  - `promotion_decisions` (approve/reject audit)
- Each pending entry includes:
  - project_id, task_id, role
  - type: `scope_of_work|roadmap|test_log|verification_result`
  - payload (json)
  - status: `pending|approved|rejected`

### 2) Agent protocol extension
- Agent subprocess JSON output includes:
  - `memory_entries`: list of proposed entries (type + payload)
- Orchestrator persists these as `pending` automatically when attaching an AgentResult.

### 3) Promotion workflow
- API endpoints:
  - `GET /projects/{project_id}/agent-memory?status=pending&task_id=...`
  - `POST /projects/{project_id}/agent-memory/{agent_memory_id}/promote` with `{decision: approved|rejected, note?: string}`
- Promotion behavior:
  - On **approved**: write a `memory_events` row (`type='decision'` or `type='summary'`) that references the promoted entry.
  - On **rejected**: record only the decision row.

### 4) Chat history
- Add `GET /projects/{project_id}/chat?task_id=...&limit=...` returning persisted messages.

### 5) Reliability: retries
- Implement agent retry in orchestrator:
  - Configurable `ODP_AGENT_MAX_RETRIES` (default 1)
  - Exponential backoff (e.g., 0.2s, 0.5s, 1s)
  - Retry only on subprocess/timeout/parse failures (not on explicit agent ok=false)

## Non-goals
- No full compaction/summarization policy enforcement (defer to Milestone 4).
- No UI build-out beyond existing minimal dashboard.
- No real "merge to main" automation.

## Deliverables
1. DB schema changes + migration via `ODP_AUTO_MIGRATE`
2. Agent output includes memory_entries (at least in test mode)
3. Orchestrator records pending entries + emits WS events:
   - `agent_memory_pending`
   - `agent_memory_promoted`
4. API endpoints for listing and promotion
5. Tests:
   - Pending memory entries exist after a task completes
   - Promotion endpoint updates status + writes auditable decision
   - Retry logic is exercised (forced parse failure once, then succeeds)

## Evidence required
- DB rows for pending entries + promotion decision
- WS transcript includes pending/promoted events
- Test output (`pytest -q`) green
