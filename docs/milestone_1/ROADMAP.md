# Roadmap

## Milestones
1. Milestone 1: Orchestrator skeleton + gated flow (this)
2. Milestone 2: Real agent execution + isolated workspaces
3. Milestone 3: UI dashboard implementation (per UI prototypes)

## Dependencies
- Redis available for local dev/test.
- Postgres available for local dev (pgvector optional).

## Timeline (estimate)
- Milestone 1: 1-2 days (skeleton + tests)

## Risks & Mitigations
- Risk: Docker not available in some environments.
  - Mitigation: dockerless test harness (fakeredis + sqlite) for unit/e2e loop.
- Risk: pgvector not installed.
  - Mitigation: schema init tolerates missing vector extension for M1.
