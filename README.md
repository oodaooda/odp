# Orchestrated Dev Platform (ODP)

ODP is a spec-driven, multi-agent development system designed to safely coordinate autonomous software engineering tasks. It uses a centralized orchestrator to manage specialized worker agents (engineering, QA/QC, security, etc.) within a multi-process architecture backed by Redis and real-time WebSocket observability. All changes are gated through structured verification and validation phases before commits are allowed.

## Docs (source of truth)
- PRD: `01_PRD.md`
- SRD: `02_SRD.md`
- PDR: `03_PDR.md`
- ICD: `04_ICD.md`
- DDR: `05_DDR.md`
- V&V Plan: `06_VV_PLAN.md`
- Security: `07_SECURITY.md`
- Decisions: `08_DECISIONS.md`
- Runbook: `09_RUNBOOK.md`
- SLOs: `10_SLOS.md`
- Config & Secrets: `11_CONFIG_SECRETS.md`
- Handoff: `12_HANDOFF.md`
- UI Spec: `docs/UI_SPEC.md`
- How To Run: `docs/HOW_TO_RUN.md`

## Repo layout (initial)
- `apps/`: UI + control surface
- `services/`: orchestrator and worker services
- `infra/`: Redis, WebSocket, deployment scaffolding
- `docs/`: process notes and indexes
- `tests/`: verification and validation suites
- `scripts/`: local dev and CI helpers
- `runtime/`: runtime artifacts (kept out of git if needed)

## Workflow (short)
1. Start from specs. Any work must link back to the doc stack above.
2. Define an explicit gate per phase (see `06_VV_PLAN.md`).
3. Run agent work only after the orchestrator decomposes tasks.
4. Merge only if all gates pass with objective evidence.

See `docs/PROCESS.md` for the detailed workflow.
