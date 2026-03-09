# LLM Integration Specification

## 1. Purpose
Define how ODP agents connect to large language models (Claude, OpenAI) to generate code, reason about tasks, and iterate on failures.

---

## 2. Architecture

```
┌──────────────┐     ┌──────────┐     ┌─────────────┐
│  Orchestrator │────▶│  Agent   │────▶│  LLM Client │
│  (dispatch)   │     │ (engineer)│     │  (llm.py)   │
└──────────────┘     └──────────┘     └──────┬──────┘
                                              │
                                     ┌────────▼────────┐
                                     │  Claude API  or  │
                                     │  OpenAI API      │
                                     └─────────────────┘
```

- The LLM client is a thin module: `services/orchestrator/odp_orchestrator/llm.py`
- Only the engineer agent calls the LLM. QA and security agents remain deterministic validators.
- The orchestrator never calls the LLM directly — it delegates through agents.

---

## 3. Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ODP_LLM_PROVIDER` | No | `none` | `anthropic`, `openai`, or `none` (disables LLM) |
| `ODP_LLM_MODEL` | No | `claude-sonnet-4-6` | Model ID to use |
| `ODP_LLM_API_KEY` | If provider set | — | API key for the LLM provider |
| `ODP_LLM_MAX_TOKENS` | No | `4096` | Max output tokens per call |
| `ODP_MAX_AGENT_RETRIES` | No | `3` | Max retry attempts on test failure |

When `ODP_LLM_PROVIDER=none` (default), agents fall back to current deterministic behavior. This preserves all existing tests.

---

## 4. Engineer Agent Flow (with LLM)

1. Receive task context: title, description, spec refs, relevant files
2. Build prompt: system instructions + task + file contents
3. Call LLM → receive code changes (unified diff or full file)
4. Apply changes to isolated worktree
5. Run `pytest -q`
6. If tests pass → return success + diff + test output
7. If tests fail → feed error back to LLM, retry (up to `ODP_MAX_AGENT_RETRIES`)
8. If all retries exhausted → return failure + all attempt logs

---

## 5. Context Building

The agent assembles LLM context from:
- Task title and description
- Spec file contents (from spec refs)
- Relevant source files from the workspace (heuristic: files matching task keywords)
- Past memory events (via pgvector search if embeddings enabled)
- Previous attempt feedback (on retry)

Token budget: context is truncated to fit within model limits. Spec content takes priority, then source files, then memory.

---

## 6. Cost & Rate Limiting

- Each LLM call logs: model, input tokens, output tokens, latency, cost estimate
- Logged as a memory event (type: `llm_call`)
- No global rate limiter in v1 — rely on provider rate limits
- Cost tracking visible in Audit Log

---

## 7. Security Constraints

- API keys stored in environment variables only (never in code, logs, or memory)
- Agent prompts must not include secrets from the workspace
- LLM output is always validated by QA and security agents before commit
- Generated code is treated as untrusted until gates pass

---

## 8. Testing

- All existing tests run with `ODP_LLM_PROVIDER=none` (no LLM calls)
- Integration test: `ODP_LLM_PROVIDER=anthropic` + real API key → generate code → verify output
- Mock LLM client for unit tests (deterministic responses)
