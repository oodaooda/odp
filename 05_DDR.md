# Detailed Design Review (DDR)

## 1. Orchestrator State Machine
- INIT
- DISPATCH
- COLLECT
- VALIDATE
- COMMIT
- ROLLBACK

---

## 2. Retry Logic
- Max retries per agent: configurable
- Exponential backoff
- Retry only idempotent tasks

---

## 3. Git Operations
- Clone to temp workspace
- Branch per task
- No direct main writes
- Merge only after gates

---

## 4. Directory Layout
```text
runtime/
├── orchestrator/
├── agents/
│   ├── engineer/
│   ├── qa/
│   └── security/
├── redis/
└── logs/
```

## 5. Memory Model
- Postgres is the source of truth for memory events.
- Orchestrator is the only writer.
- Agents may read via orchestrator-mediated queries.
- Vector index (pgvector) is derived from memory events.
 - Agents may write to agent-scoped memory tables (pending), which require orchestrator promotion.

## 6. Agent Workspaces
- Each agent gets an isolated workspace per task.
- All artifacts, tests, and logs are stored under the agent workspace.
- Orchestrator controls promotion of artifacts into source-of-truth memory.

## 7. Agent Memory (Persistent)
- Agents maintain task-scoped memory entries in Postgres (pending).
- Orchestrator reviews and promotes entries into source-of-truth memory.
- Vector index is derived only from promoted memory events.
