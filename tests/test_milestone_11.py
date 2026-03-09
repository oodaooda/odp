"""Milestone 11: LLM Agent Integration — verify the LLM client module,
engineer agent LLM flow, task context passing, and graceful fallback."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_m11_llm_module_exists():
    """The LLM client module must exist with call_llm function."""
    llm_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "llm.py"
    assert llm_path.is_file(), "Missing llm.py module"
    content = llm_path.read_text()
    assert "async def call_llm" in content, "llm.py must export call_llm"
    assert "LLMResponse" in content, "llm.py must define LLMResponse"
    assert "anthropic" in content, "llm.py must support Anthropic provider"
    assert "openai" in content, "llm.py must support OpenAI provider"


def test_m11_llm_disabled_by_default():
    """When ODP_LLM_PROVIDER=none, call_llm returns None."""
    import asyncio
    # Ensure provider is disabled.
    old = os.environ.get("ODP_LLM_PROVIDER")
    os.environ["ODP_LLM_PROVIDER"] = "none"
    try:
        from services.orchestrator.odp_orchestrator.llm import call_llm
        result = asyncio.get_event_loop().run_until_complete(
            call_llm(system="test", messages=[{"role": "user", "content": "hello"}])
        )
        assert result is None, "call_llm should return None when provider is 'none'"
    finally:
        if old is not None:
            os.environ["ODP_LLM_PROVIDER"] = old
        else:
            os.environ.pop("ODP_LLM_PROVIDER", None)


def test_m11_task_model_has_description():
    """Task model must include a description field."""
    from services.orchestrator.odp_orchestrator.models import Task, TaskCreateRequest
    # TaskCreateRequest should accept description.
    req = TaskCreateRequest(title="test", description="do something")
    assert req.description == "do something"

    # Task should have description with default.
    t = Task(
        project_id="00000000-0000-0000-0000-000000000000",
        task_id="00000000-0000-0000-0000-000000000001",
        title="test",
        spec_hash="abc",
        created_at_ms=0,
        updated_at_ms=0,
    )
    assert t.description == ""


def test_m11_engineer_agent_has_llm_branch():
    """Engineer agent must have LLM code generation path."""
    agent_path = REPO_ROOT / "services" / "agents" / "odp_agent" / "main.py"
    content = agent_path.read_text()
    assert "_engineer_with_llm" in content, "Engineer must have LLM code gen function"
    assert "ODP_LLM_PROVIDER" in content, "Engineer must check LLM provider config"
    assert "_build_engineer_prompt" in content, "Engineer must build LLM prompts"
    assert "_apply_diff" in content, "Engineer must apply generated diffs"
    assert "ODP_TASK_CONTEXT" in content, "Engineer must read task context from env"


def test_m11_agent_runner_passes_context():
    """Agent runner must pass task_context and feedback to agents."""
    runner_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "agent_runner.py"
    content = runner_path.read_text()
    assert "task_context" in content, "agent_runner must accept task_context"
    assert "feedback" in content, "agent_runner must accept feedback"
    assert "ODP_TASK_CONTEXT" in content, "agent_runner must set ODP_TASK_CONTEXT env"
    assert "ODP_AGENT_FEEDBACK" in content, "agent_runner must set ODP_AGENT_FEEDBACK env"


def test_m11_orchestrator_retry_with_feedback():
    """Orchestrator retry loop must capture feedback from failures."""
    orch_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "orchestrator.py"
    content = orch_path.read_text()
    assert "feedback" in content, "Orchestrator must support feedback in retries"
    assert "task_context" in content, "Orchestrator must pass task_context to agents"


def test_m11_test_mode_unaffected():
    """Test mode still works identically — no LLM calls."""
    old_test = os.environ.get("ODP_AGENT_TEST_MODE")
    old_llm = os.environ.get("ODP_LLM_PROVIDER")
    os.environ["ODP_AGENT_TEST_MODE"] = "1"
    os.environ.pop("ODP_LLM_PROVIDER", None)
    try:
        import tempfile
        from services.agents.odp_agent.main import _engineer, AgentOutput
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "workspace"
            ws.mkdir()
            art = Path(td) / "artifacts"
            art.mkdir()
            result = _engineer(ws, art)
            assert isinstance(result, AgentOutput)
            assert result.ok is True
            assert "test-mode" in result.summary
    finally:
        if old_test is not None:
            os.environ["ODP_AGENT_TEST_MODE"] = old_test
        else:
            os.environ.pop("ODP_AGENT_TEST_MODE", None)
        if old_llm is not None:
            os.environ["ODP_LLM_PROVIDER"] = old_llm


def test_m11_cost_tracking():
    """LLM module must include cost estimation."""
    from services.orchestrator.odp_orchestrator.llm import _estimate_cost
    cost = _estimate_cost("claude-sonnet-4-6", 1000, 500)
    assert cost > 0, "Cost estimate should be positive"
    assert isinstance(cost, float)


def test_m11_workspace_file_reader():
    """Engineer agent must be able to read workspace files for context."""
    import tempfile
    from services.agents.odp_agent.main import _read_workspace_files
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "hello.py").write_text("print('hello')\n")
        (ws / "README.md").write_text("# Test\n")
        result = _read_workspace_files(ws)
        assert "hello.py" in result
        assert "print('hello')" in result


def test_m11_frontend_supports_description():
    """Frontend types and client must support task description."""
    types_path = REPO_ROOT / "apps" / "web" / "src" / "api" / "types.ts"
    client_path = REPO_ROOT / "apps" / "web" / "src" / "api" / "client.ts"
    types_content = types_path.read_text()
    client_content = client_path.read_text()
    assert "description" in types_content, "Task type must include description"
    assert "description" in client_content, "createTask must accept description"
