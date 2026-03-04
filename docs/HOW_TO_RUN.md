# How To Run ODP (Local Dev)

## 1. Prerequisites
- Linux/macOS
- Git
- Conda (Miniforge) with env name `odp`
- Redis + Postgres (local dev)

## 2. Conda Environment
```bash
/home/deimos/miniforge3/bin/conda create -y -n odp python=3.11
/home/deimos/miniforge3/bin/conda run -n odp python -m pip install -r requirements-dev.txt
```

## 3. Start Infra (Redis + Postgres)
```bash
cd /home/deimos/Documents/openClaw/genesis/odp
docker compose -f infra/docker-compose.yml up -d
```
If your Docker install doesn't support `docker compose`, use the legacy binary:
```bash
docker-compose -f infra/docker-compose.yml up -d
```

## 4. Run Tests
```bash
cd /home/deimos/Documents/openClaw/genesis/odp
/home/deimos/miniforge3/bin/conda run -n odp pytest -q
```

## 5. Run Orchestrator API
```bash
cd /home/deimos/Documents/openClaw/genesis/odp
/home/deimos/miniforge3/bin/conda run -n odp \
  uvicorn services.orchestrator.odp_orchestrator.api:create_app --factory --reload --host 0.0.0.0 --port 8080
```

## 6. Open UI (Basic)
- Project UI: `http://127.0.0.1:8080/ui/projects/{project_id}`
- Task UI: `http://127.0.0.1:8080/ui/projects/{project_id}/tasks/{task_id}`
- Audit UI: `http://127.0.0.1:8080/ui/projects/{project_id}/audit`

Remote access (same LAN): use the host's IP, e.g. `http://10.0.0.25:8080/ui/projects/{project_id}`

## 6b. Create a Project ID
Generate a UUID and use it as the project id:
```bash
python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
```

## 7. Environment Variables (Optional)
- `ODP_EMBEDDINGS_PROVIDER=openai` (enable embeddings)
- `ODP_ENABLE_MERGE=1` (enable merge automation)
- `ODP_LOG_REQUESTS=1` (request logging)

## 8. Stop Infra
```bash
cd /home/deimos/Documents/openClaw/genesis/odp
docker compose -f infra/docker-compose.yml down
```
