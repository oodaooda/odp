# Milestone 11: Agent Orchestration End-to-End (Planned)

## Goal
Wire the UI to the full agent execution flow so users can submit a task, watch agents spawn, observe gate pass/fail decisions, and see commit/rollback outcomes — all through the browser.

## Scope

### 1) Task execution flow in UI
- [ ] "Run Task" button triggers orchestrator dispatch
- [ ] Live agent spawn indicators (engineer/qa/security cards update in real-time)
- [ ] Gate decisions stream into TaskDetail and GateEvidence as they happen
- [ ] Commit/rollback outcome displayed with toast + state timeline update

### 2) Agent memory promotion UI
- [ ] Pending memory entries listed with approve/reject buttons
- [ ] Promotion decisions recorded and displayed in audit log
- [ ] Toast notification on approve/reject

### 3) Artifact management
- [ ] Artifact upload via drag-and-drop or file picker
- [ ] Artifact download links in TaskDetail and GateEvidence
- [ ] Inline preview for text artifacts (logs, diffs, reports)

### 4) Memory search
- [ ] Search bar on Dashboard or dedicated search page
- [ ] Calls `/projects/{project_id}/memory/search` endpoint
- [ ] Results displayed with artifact enrichment

### 5) Project-level WebSocket
- [ ] Backend: new WS endpoint for project-wide events (not task-specific)
- [ ] Frontend: `useProjectSocket` drives Dashboard, Agents, AuditLog updates
- [ ] Eliminate remaining polling on pages that can use WS

## Non-goals
- Auth/login UI (M12)
- Deployment automation (M12)
- Performance optimization

## Deliverables
- [ ] End-to-end task execution visible in UI
- [ ] Agent memory promotion workflow functional
- [ ] Artifact upload/download working
- [ ] Memory search integrated
- [ ] All tests pass

## Evidence required
- Screenshots of task execution flow
- `pytest -q` green
- Demo video or walkthrough
