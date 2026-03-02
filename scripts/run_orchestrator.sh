#!/usr/bin/env bash
set -euo pipefail

export ODP_REDIS_URL=${ODP_REDIS_URL:-redis://localhost:6379/0}
export ODP_DATABASE_URL=${ODP_DATABASE_URL:-postgresql+asyncpg://odp:odp@localhost:5432/odp}
export ODP_AUTO_MIGRATE=${ODP_AUTO_MIGRATE:-1}

python3 -m services.orchestrator.odp_orchestrator "$@"
