# Milestone 8: UI Parity With Prototypes (Dark Mode) + Live Data Bindings

## Goal
Bring the web UI to **visual and behavioral parity** with the dark-mode prototypes in `docs/UI_SPEC.md`, including:
- Dashboard layout
- Task detail view
- Gate evidence view
- Orchestrator chat view

## Scope
### 1) Dashboard UI parity
- Left nav, top bar, KPI cards
- Task table layout + status styling
- Orchestrator chat panel
- Agents list and gate status panels

### 2) Task detail UI parity
- Task schema panel
- Spec refs panel
- Agent results panel
- State transitions panel
- Audit log panel

### 3) Gate evidence UI parity
- Gate decision table
- Evidence viewer
- Agent tools panel
- State transition timeline

### 4) Chat UI parity
- Dedicated chat page
- Message bubbles + input controls
- Optional task_id scoping

### 5) Live data bindings
- Data pulled from existing APIs:
  - `/projects/{project_id}/tasks`
  - `/projects/{project_id}/tasks/{task_id}`
  - `/projects/{project_id}/memory-events`
  - `/projects/{project_id}/chat`
  - `/projects/{project_id}/tasks/{task_id}/artifacts`
  - `/projects/{project_id}/agent-memory`

## Non-goals
- No frontend framework migration
- No real-time sync (polling is fine)
- No authentication UX changes

## Deliverables
- [x] Dashboard UI matches `odp_ui_dashboard_dark.png`
- [x] Task detail UI matches `odp_ui_task_detail_dark.png`
- [x] Gate evidence UI matches `odp_ui_gate_evidence_dark.png`
- [x] Chat UI matches `odp_ui_chatbox_dark.png`
- [x] All pages use live API data where available

## Evidence required
- Screenshot(s) of each page
- `pytest -q` green (if any tests added)
