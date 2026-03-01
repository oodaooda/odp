# System Requirements Document (SRD)

### 1. Process Model
- Multi-process architecture
- Agents must be isolated
- Orchestrator is authoritative
 - Multi-project isolation required (per project_id)

---

### 2. Reliability
- Agent failure must not crash system
- Tasks must be resumable
- Redis-backed state required
 - Memory writes must be orchestrator-only
 - Agents must persist task artifacts in agent-scoped workspaces
 - Memory writes must be orchestrator-only

---

### 3. Performance
- Orchestrator response < 200ms (local)
- WebSocket updates < 1s latency
- No blocking calls in orchestrator loop

---

### 4. Security
- No secrets in agent prompts
- No direct prod access
- Git operations sandboxed
 - Memory store is append-only and auditable
 - Vector retrieval is read-only for agents
 - Memory store is append-only and auditable
 - Vector retrieval is read-only for agents

---

### 5. Scalability
- Horizontal agent scaling supported
- Redis must support concurrent tasks
- No hard-coded agent limits

---

### 6. Observability
- All state transitions logged
- Every task traceable
- Audit logs immutable
- Each agent must log: scope-of-work, roadmap/milestones, tests run, and verification results
- Chat history must be persisted and queryable per project
- All destructive actions require explicit confirmation (UI and API)
 - Chat compaction required when context exceeds limits; summaries must be auditable

---

### 7. Constraints
- Python only
- Redis required
- WebSockets required
- Postgres required (source-of-truth memory)
- Vector search required (pgvector)
 - Agent workspaces are isolated per task and role
 - Postgres required (source-of-truth memory)
 - Vector search required (pgvector)
