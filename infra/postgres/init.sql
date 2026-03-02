-- ODP local dev schema init
-- Keep this lightweight and idempotent.

-- pgvector is optional; tolerate absence by not hard-failing init.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
  WHEN undefined_file THEN
    -- pgvector not installed
    RAISE NOTICE 'pgvector not installed; continuing without vector';
END$$;

CREATE TABLE IF NOT EXISTS memory_events (
  project_id uuid NOT NULL,
  event_id uuid PRIMARY KEY,
  task_id uuid NOT NULL,
  type text NOT NULL CHECK (type IN ('message','decision','artifact','summary','state_transition')),
  actor text NOT NULL,
  payload jsonb NOT NULL,
  compaction_of uuid[],
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_events_task_id_idx ON memory_events(task_id);
CREATE INDEX IF NOT EXISTS memory_events_type_idx ON memory_events(type);
CREATE INDEX IF NOT EXISTS memory_events_project_id_idx ON memory_events(project_id);

CREATE TABLE IF NOT EXISTS artifacts (
  project_id uuid NOT NULL,
  artifact_id uuid PRIMARY KEY,
  task_id uuid NOT NULL,
  type text NOT NULL CHECK (type IN ('screenshot','log','diff','report')),
  uri text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS artifacts_task_id_idx ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS artifacts_project_id_idx ON artifacts(project_id);

CREATE TABLE IF NOT EXISTS chat_messages (
  project_id uuid NOT NULL,
  message_id uuid PRIMARY KEY,
  task_id uuid,
  actor text NOT NULL CHECK (actor IN ('user','orchestrator')),
  text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_project_id_idx ON chat_messages(project_id);
CREATE INDEX IF NOT EXISTS chat_messages_task_id_idx ON chat_messages(task_id);
