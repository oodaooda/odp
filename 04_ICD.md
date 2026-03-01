# Interface Control Document (ICD)

## 1. Redis Schemas

### Task
```json
{
  "project_id": "uuid",
  "task_id": "uuid",
  "status": "pending|running|failed|passed",
  "phase": "phase_name",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "spec_refs": ["01_PRD.md", "02_SRD.md", "03_PDR.md", "04_ICD.md", "05_DDR.md", "06_VV_PLAN.md"]
}
```

### Agent Result
```json
{
  "project_id": "uuid",
  "task_id": "uuid",
  "agent_role": "engineer|qa|security",
  "status": "passed|failed",
  "artifacts": ["path/or/url"],
  "summary": "short, evidence-first summary",
  "created_at": "timestamp"
}
```

### Gate Decision
```json
{
  "project_id": "uuid",
  "task_id": "uuid",
  "gate": "phase_name",
  "decision": "pass|fail",
  "evidence": ["result_id_1", "result_id_2"],
  "created_at": "timestamp"
}
```

## 2. Memory (Postgres)

### Orchestrator Memory Event
```json
{
  "project_id": "uuid",
  "event_id": "uuid",
  "task_id": "uuid",
  "type": "message|decision|artifact|summary|state_transition",
  "actor": "orchestrator",
  "payload": {},
  "created_at": "timestamp"
}
```

### Vector Index Entry (pgvector)
```json
{
  "event_id": "uuid",
  "embedding": "vector",
  "source": "memory_event",
  "created_at": "timestamp"
}
```

### Artifact
```json
{
  "project_id": "uuid",
  "artifact_id": "uuid",
  "task_id": "uuid",
  "type": "screenshot|log|diff|report",
  "uri": "path/or/url",
  "created_at": "timestamp"
}
```

### Agent Memory (Pending Promotion)
```json
{
  "project_id": "uuid",
  "agent_memory_id": "uuid",
  "agent_role": "engineer|qa|security",
  "task_id": "uuid",
  "type": "scope_of_work|roadmap|milestone|test_log|verification_result",
  "payload": {},
  "status": "pending|approved|rejected",
  "created_at": "timestamp"
}
```

### Promotion Decision
```json
{
  "project_id": "uuid",
  "promotion_id": "uuid",
  "agent_memory_id": "uuid",
  "decision": "approved|rejected",
  "reviewer": "orchestrator",
  "created_at": "timestamp"
}
```

### Chat Message
```json
{
  "project_id": "uuid",
  "message_id": "uuid",
  "task_id": "uuid",
  "actor": "user|orchestrator",
  "text": "string",
  "created_at": "timestamp"
}
```
