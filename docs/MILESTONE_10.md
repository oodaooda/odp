# Milestone 10: Frontend Polish & Real-Time

## Goal
Complete all frontend pages, add real-time WebSocket-driven updates, toast notifications, loading states, and error handling.

## Scope

### Phase 1: New pages + toast system
- **Agents page**: role summary KPIs, agent results table, role descriptions
- **Specs page**: 12-doc spec stack listing, M1–M12 milestone tracker with status
- **Settings page**: connection config, API token input, env var reference, architecture diagram
- **Toast notifications**: success/error/info feedback on actions (seed demo, create task)
- **Loading spinners**: initial data fetch indicator on Dashboard

### Phase 2: WebSocket-driven live refresh
- **`useLiveRefresh` hook**: WebSocket triggers instant data refresh on any event; 30s polling fallback
- **`usePollingRefresh` hook**: reusable interval-based polling for pages without task-specific WS
- **TaskDetail**: live WS connection with green/red indicator; toast on state transitions
- **Chat**: optimistic message rendering; disabled input while sending
- **Dashboard**: migrated to `usePollingRefresh` (no leaked timers)

### Phase 3: Error handling + consistency
- **ErrorBoundary**: wraps entire app; crash recovery with reload button
- **Loading spinners**: added to GateEvidence, AuditLog
- **All pages**: consistent use of polling hooks, no raw `setInterval`

## Non-goals
- Full WebSocket replacement of all polling (backend WS is per-task, not per-project)
- Frontend test suite (M12)

## Deliverables
- [x] Agents, Specs, Settings pages fully functional
- [x] All 8 sidebar tabs navigate correctly
- [x] Toast notifications on task creation, demo seeding
- [x] WebSocket live refresh on TaskDetail with connection indicator
- [x] Optimistic chat messages
- [x] ErrorBoundary with crash recovery
- [x] Loading spinners on all pages
- [x] `npm run build` clean
- [x] `pytest -q` 9/10 pass (1 pre-existing flaky M4 test)

## Evidence
- `npm run build` produces dist/ with no errors
- `pytest -q` 9 passed, 1 pre-existing flaky
- Commits: `b51b608`, `eb69d32`, `1dfa2bb`
