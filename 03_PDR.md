# Preliminary Design Review (PDR)

### 1. Architecture Overview

- Orchestrator (single authority)
- Worker agents (stateless)
- Redis (coordination + state)
- WebSocket server (UI visibility)
- Postgres (memory source-of-truth)
- pgvector (retrieval index)
- Project router (namespaces per project_id)
 - Dashboard served on LAN for local network access

---

### 2. Authority Model
- Orchestrator decides all outcomes
- Agents provide evidence, not decisions
- No peer-to-peer agent control

---

### 3. Data Flow
1. Task received
2. Orchestrator decomposes
3. Agents execute
4. Results returned
5. Gates evaluated
6. Commit or reject
 7. Chat messages persisted as memory events

---

### 4. Trust Boundaries
- Agents untrusted
- Redis semi-trusted
- Orchestrator trusted
 - Postgres trusted (append-only)
 - Vector store untrusted (read-only)

---

### 5. Design Risks
- Agent hallucination → mitigated by gates
- Interface drift → mitigated by ICD
- Silent failure → mitigated by V&V

---

### 6. PDR Approval Criteria
- All roles defined
- Message flow explicit
- No circular authority
