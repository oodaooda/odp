# Operations Runbook

## 1. Startup
- Ensure Redis and Postgres are running.
- Start orchestrator service.
- Start WebSocket gateway and UI.

## 2. Shutdown
- Quiesce new tasks.
- Allow running tasks to finish or rollback.
- Stop services in order: UI → Orchestrator → Redis/Postgres.

## 3. Backup & Restore
- Daily Postgres backups (pg_dump).
- Weekly artifact archive (filesystem snapshot).
- Restore by replaying Postgres + artifacts.

## 4. Incident Response
- Capture logs and task IDs.
- Freeze affected project if needed.
- Run gate re-evaluation after recovery.
