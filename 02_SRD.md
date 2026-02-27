# System Requirements Document (SRD)

### 1. Process Model
- Multi-process architecture
- Agents must be isolated
- Orchestrator is authoritative

---

### 2. Reliability
- Agent failure must not crash system
- Tasks must be resumable
- Redis-backed state required

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

---

### 7. Constraints
- Python only
- Redis required
- WebSockets required
