"""Thin LLM client supporting Anthropic (Claude) and OpenAI.

Supports dual-provider config:
  - ODP_LLM_*          — default (used by agents in subprocess)
  - ODP_ORCH_LLM_*     — orchestrator-specific (Claude for decisions)
  - ODP_AGENT_LLM_*    — agent-specific (OpenAI for code gen)

When provider is 'none' (default), all calls return None and agents
fall back to deterministic behavior.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Result from an LLM call."""
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_estimate: float  # rough USD estimate


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rough cost estimate based on public pricing."""
    rates: dict[str, tuple[float, float]] = {
        # (input $/1M tokens, output $/1M tokens)
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-opus-4-6": (15.0, 75.0),
        "claude-haiku-4-5-20251001": (0.80, 4.0),
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    }
    in_rate, out_rate = rates.get(model, (3.0, 15.0))
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


async def call_llm(
    *,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    env_prefix: str = "ODP_LLM",
) -> LLMResponse | None:
    """Call the configured LLM provider.

    Args:
        env_prefix: Env var prefix to read config from. Defaults to "ODP_LLM".
                    Use "ODP_ORCH_LLM" for orchestrator calls.
                    Agents in subprocess use "ODP_LLM" (mapped from ODP_AGENT_LLM_*).

    Returns None if provider is 'none' or not configured.
    """
    provider = os.getenv(f"{env_prefix}_PROVIDER", "none").lower()
    if provider == "none":
        return None

    default_model = "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o"
    model = os.getenv(f"{env_prefix}_MODEL", default_model)
    api_key = os.getenv(f"{env_prefix}_API_KEY", "")
    max_tok = max_tokens or int(os.getenv(f"{env_prefix}_MAX_TOKENS", "4096"))

    if not api_key:
        logger.warning("%s_API_KEY not set; skipping LLM call", env_prefix)
        return None

    t0 = time.monotonic()

    if provider == "anthropic":
        return await _call_anthropic(model=model, api_key=api_key, system=system,
                                     messages=messages, max_tokens=max_tok, t0=t0)
    elif provider == "openai":
        return await _call_openai(model=model, api_key=api_key, system=system,
                                  messages=messages, max_tokens=max_tok, t0=t0)
    else:
        logger.warning("Unknown ODP_LLM_PROVIDER=%s; skipping LLM call", provider)
        return None


async def _call_anthropic(
    *, model: str, api_key: str, system: str,
    messages: list[dict[str, str]], max_tokens: int, t0: float,
) -> LLMResponse:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    latency = int((time.monotonic() - t0) * 1000)
    text = resp.content[0].text if resp.content else ""
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    return LLMResponse(
        text=text, model=model,
        input_tokens=in_tok, output_tokens=out_tok,
        latency_ms=latency,
        cost_estimate=_estimate_cost(model, in_tok, out_tok),
    )


async def _call_openai(
    *, model: str, api_key: str, system: str,
    messages: list[dict[str, str]], max_tokens: int, t0: float,
) -> LLMResponse:
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = openai.AsyncOpenAI(api_key=api_key)
    oai_messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    oai_messages.extend(messages)
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=oai_messages,  # type: ignore[arg-type]
    )
    latency = int((time.monotonic() - t0) * 1000)
    choice = resp.choices[0] if resp.choices else None
    text = choice.message.content or "" if choice else ""
    usage = resp.usage
    in_tok = usage.prompt_tokens if usage else 0
    out_tok = usage.completion_tokens if usage else 0
    return LLMResponse(
        text=text, model=model,
        input_tokens=in_tok, output_tokens=out_tok,
        latency_ms=latency,
        cost_estimate=_estimate_cost(model, in_tok, out_tok),
    )
