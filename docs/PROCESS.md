# ODP Development Process (OpenClaw-driven)

## 1. Inputs (source of truth)
- Specs: PRD/SRD/PDR/ICD/DDR/V&V Plan
- Each task must cite the spec(s) it is implementing.
 - Each task must include a scope-of-work doc and roadmap with milestones.

## 2. Roles
- Orchestrator: decomposes work, enforces gates, final authority.
- Engineer agent: produces code + tests + diffs.
- QA agent: runs regression checks and spec compliance.
- Security agent: runs secret/dependency scans.
- Orchestrator is the only writer to long-term memory.
 - Agents may draft memory entries pending orchestrator promotion.

## 3. Phases and gates
- Phase 1: Orchestrator lifecycle tests
- Phase 2: Engineer (branch isolation, diff generation, local tests)
- Phase 3: QA regression + spec compliance
- Phase 4: Security checks
- Phase 5: UI/WebSocket stability checks

No commit or merge is allowed unless all gates pass and evidence is recorded.

## 4. Evidence requirements (per gate)
- Test output or log artifacts
- Repro steps or commands
- Source diffs
- Final gate decision recorded in state
- Memory events stored in Postgres (append-only)
- Scope-of-work, roadmap, and verification logs attached per task
- Commits and pushes only after tests pass; never push on failing tests
 - `.gitignore` must be maintained to prevent non-essential artifacts from being committed

## 5. Suggested first milestone
- Minimal orchestrator service with task lifecycle
- Redis state schema implemented (Task, Agent Result, Gate Decision)
- WebSocket event stream for status updates
- One end-to-end gated task flow in tests
- Orchestrator memory write path (Postgres + pgvector)

## 6. Templates (agent required)
- Scope of Work template: `docs/templates/SCOPE_OF_WORK.md`
- Roadmap template: `docs/templates/ROADMAP.md`
- Verification log template: `docs/templates/VERIFICATION_LOG.md`

## 7. OpenClaw TUI + Logs (Quick Reference)
- TUI status line shows connection/run state (connecting, running, streaming, idle, error). citeturn1search0
- If TUI shows no output: run `/status`, check `openclaw logs --follow`, and confirm agent/model status. citeturn1search0turn1search6turn0search0
- TUI delivery is off by default; enable with `/deliver on` or `openclaw tui --deliver`. citeturn1search0
- Log file location defaults to `/tmp/openclaw/openclaw-YYYY-MM-DD.log`; CLI tail is `openclaw logs --follow`. citeturn0search0turn0search4
