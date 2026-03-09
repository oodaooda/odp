# Milestone 12: End-to-End Orchestration UI

## Goal
Wire the React UI to the full task execution flow so a user can: submit a task description → watch agents generate code → see gates pass/fail → observe commit or rollback — all from the browser.

This milestone closes the gap between the backend (which already orchestrates) and the frontend (which currently only displays data).

## Scope

### 1) Task execution from UI
- [ ] "Run Task" button on Dashboard and TaskDetail triggers `POST /projects/{id}/resume` or a new dispatch endpoint
- [ ] Task creation accepts a description field (not just title)
- [ ] Live agent spawn indicators — engineer/qa/security cards show "running" → "passed"/"failed" in real-time via WebSocket
- [ ] Commit/rollback outcome displayed with toast + timeline update
- [ ] "Cancel Task" button for in-progress tasks

### 2) Agent memory promotion UI
- [ ] Dedicated "Pending Memory" section on TaskDetail page
- [ ] Lists agent-proposed memory entries with approve/reject buttons
- [ ] Calls `POST /projects/{id}/agent-memory/{id}/promote`
- [ ] Promotion decisions shown in audit log with toast feedback

### 3) Artifact management
- [ ] Artifact upload via file picker on TaskDetail page
- [ ] Calls `POST /projects/{id}/tasks/{id}/artifacts` (multipart upload)
- [ ] Download links for all artifacts in TaskDetail and GateEvidence
- [ ] Inline preview for text artifacts (logs, diffs, reports) in a modal or expandable viewer

### 4) Memory search
- [ ] Search bar on Dashboard or a dedicated search page
- [ ] Calls `GET /projects/{id}/memory/search?q=...`
- [ ] Results displayed with event details + linked artifacts
- [ ] Click-through to relevant task detail

### 5) Project-level WebSocket
- [ ] Backend: new WS endpoint `/ws/projects/{project_id}` for project-wide events
- [ ] Broadcasts all task state changes, gate decisions, agent results for the project
- [ ] Frontend: `useProjectSocket` replaces polling on Dashboard, Agents, AuditLog
- [ ] Connection indicator in sidebar (green dot when WS connected)

## Non-goals
- Auth/login UI (M13)
- Multi-project selector (M14)

## Deliverables
- [ ] Full task lifecycle visible and controllable from browser
- [ ] Agent memory promotion workflow functional in UI
- [ ] Artifact upload/download/preview working
- [ ] Memory search integrated
- [ ] Project-level WebSocket eliminates remaining polling
- [ ] `npm run build` clean
- [ ] `pytest -q` green

## Evidence required
- Walkthrough: create task → agents run → gates evaluate → commit (all in browser)
- Screenshot of memory promotion UI
- Screenshot of artifact preview
