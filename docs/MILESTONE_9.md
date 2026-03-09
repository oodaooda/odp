# Milestone 9: React SPA Frontend

## Goal
Replace the embedded HTML/CSS/JS in `api.py` with a proper **React + TypeScript + Vite** single-page application served from `apps/web/`.

## Scope
### 1) Project scaffolding
- Vite + React + TypeScript in `apps/web/`
- react-router-dom for client-side routing
- Vite proxy config for API/WebSocket forwarding in dev

### 2) Core pages (matching dark-mode prototypes)
- Dashboard: KPI cards, task table, chat panel, agents panel
- Task Detail: task schema, agent results, state transitions, audit log, timeline
- Gate Evidence: gate decisions table, evidence viewer, agent tools, timeline
- Chat: message bubbles, input bar, auto-scroll
- Audit Log: full event log table

### 3) API integration
- REST client (`apps/web/src/api/client.ts`) wired to all backend endpoints
- WebSocket hook with auto-reconnect for live task events
- Type definitions for all data models

### 4) Backend changes
- Removed ~687 lines of embedded HTML from `api.py`
- Added SPA catch-all route serving `apps/web/dist/index.html`
- Static `/assets/*` mount for built JS/CSS

### 5) Network access
- Vite dev server binds `0.0.0.0:5173` for LAN access
- FastAPI binds `0.0.0.0:8080` for production serving
- Accessible at `10.0.0.25` from other devices on the network

## Non-goals
- No agent execution wiring (M11)
- No auth UX (M12)

## Deliverables
- [x] React SPA builds cleanly (`npm run build`)
- [x] All 5 pages render and connect to backend API
- [x] Dark theme matches prototype PNGs
- [x] `api.py` reduced from ~1170 to ~485 lines
- [x] `pytest -q` all tests pass (10/10)
- [x] LAN-accessible at 10.0.0.25:8080

## Evidence
- `npm run build` produces dist/ with no errors
- `pytest -q` green (10 passed)
- Commit: `2b9ed51`
