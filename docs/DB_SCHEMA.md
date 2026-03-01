# Database Schema (Postgres + pgvector)

## 1. Memory Events (source of truth)
```sql
create table memory_events (
  event_id uuid primary key,
  task_id uuid not null,
  type text not null check (type in ('message','decision','artifact','summary','state_transition')),
  actor text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index memory_events_task_id_idx on memory_events(task_id);
create index memory_events_type_idx on memory_events(type);
```

## 2. Agent Memory (pending promotion)
```sql
create table agent_memory (
  agent_memory_id uuid primary key,
  agent_role text not null check (agent_role in ('engineer','qa','security')),
  task_id uuid not null,
  type text not null check (type in ('scope_of_work','roadmap','milestone','test_log','verification_result')),
  payload jsonb not null,
  status text not null check (status in ('pending','approved','rejected')),
  created_at timestamptz not null default now()
);

create index agent_memory_task_id_idx on agent_memory(task_id);
create index agent_memory_status_idx on agent_memory(status);
```

## 3. Promotion Decisions
```sql
create table promotion_decisions (
  promotion_id uuid primary key,
  agent_memory_id uuid not null references agent_memory(agent_memory_id),
  decision text not null check (decision in ('approved','rejected')),
  reviewer text not null,
  created_at timestamptz not null default now()
);

create index promotion_decisions_agent_memory_id_idx on promotion_decisions(agent_memory_id);
```

## 4. Artifacts
```sql
create table artifacts (
  artifact_id uuid primary key,
  task_id uuid not null,
  type text not null check (type in ('screenshot','log','diff','report')),
  uri text not null,
  created_at timestamptz not null default now()
);

create index artifacts_task_id_idx on artifacts(task_id);
```

## 5. Vector Index (pgvector)
```sql
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;

create table memory_vectors (
  event_id uuid primary key references memory_events(event_id),
  embedding vector(1536) not null,
  source text not null,
  created_at timestamptz not null default now()
);

-- Example IVFFLAT index (tune lists based on scale)
create index memory_vectors_embedding_idx on memory_vectors using ivfflat (embedding vector_l2_ops) with (lists = 100);
```
