# Milestone 11: LLM Agent Integration

## Goal
Wire an LLM (Claude or OpenAI) into the engineer agent so it can **actually generate code** from task descriptions. This is the core capability that transforms ODP from a deterministic test runner into an autonomous software engineering platform.

Currently, the engineer agent just runs `git diff` and `pytest` on an unchanged workspace. After M11, it will:
1. Read the task description and spec references
2. Call an LLM to generate code changes
3. Apply the changes to its isolated worktree
4. Run tests to validate
5. Retry with error feedback if tests fail

## Scope

### 1) LLM client module
- [ ] New `services/orchestrator/odp_orchestrator/llm.py` — thin wrapper supporting Claude (Anthropic SDK) and OpenAI
- [ ] Config-gated: `ODP_LLM_PROVIDER=anthropic|openai`, `ODP_LLM_MODEL`, `ODP_LLM_API_KEY`
- [ ] Disabled by default (agents fall back to current deterministic behavior)
- [ ] Token/cost tracking per call

### 2) Engineer agent — code generation
- [ ] Agent receives task title, description, and spec refs as context
- [ ] Calls LLM with: task prompt + relevant file contents from workspace
- [ ] Applies generated diff/code to the worktree
- [ ] Runs `pytest -q` to validate
- [ ] On test failure: feeds error output back to LLM for retry (max 3 attempts)
- [ ] Returns final diff, test output, and generation logs as artifacts

### 3) Task context passing
- [ ] Orchestrator passes task metadata (title, spec_hash, spec file contents) to agent subprocess
- [ ] Agent reads spec files from repo to build LLM context
- [ ] Memory search (pgvector) provides relevant past decisions as context

### 4) QA/Security agents — enhanced validation
- [ ] QA agent: no LLM needed, but now validates that generated code matches spec intent (spec hash check already exists)
- [ ] Security agent: scan generated diffs for secrets/vulnerabilities (already functional, just needs to run on real diffs)

### 5) Orchestrator retry loop
- [ ] On engineer failure, orchestrator can re-dispatch with feedback from QA/security
- [ ] Configurable max retries: `ODP_MAX_AGENT_RETRIES` (default 3)
- [ ] Each retry logged as a memory event with the feedback context

## Non-goals
- Multi-file refactoring across entire repos (single-task scope only)
- Agent-to-agent direct communication (orchestrator mediates)
- Fine-tuning or training models

## Deliverables
- [ ] `llm.py` module with Claude + OpenAI support
- [ ] Engineer agent generates real code from task descriptions
- [ ] Test failure → LLM retry loop functional
- [ ] All existing tests still pass (`ODP_AGENT_TEST_MODE=1` unchanged)
- [ ] New integration test: create task → agent generates code → tests pass → commit
- [ ] Documentation: `docs/LLM_INTEGRATION.md`

## Evidence required
- Integration test passing with real LLM call
- Artifact: generated diff from a sample task
- `pytest -q` green (existing tests + new integration test)
