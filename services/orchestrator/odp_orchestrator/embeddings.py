from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EmbeddingsConfig:
    provider: str = "disabled"  # disabled|openai
    openai_api_key: str | None = None
    openai_model: str = "text-embedding-3-small"

    @classmethod
    def from_env(cls) -> "EmbeddingsConfig":
        provider = os.getenv("ODP_EMBEDDINGS_PROVIDER", "disabled").strip().lower()
        return cls(
            provider=provider,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("ODP_OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        )


class EmbeddingsClient:
    def __init__(self, cfg: EmbeddingsConfig):
        self.cfg = cfg

    async def embed(self, text_: str) -> list[float] | None:
        """Return an embedding vector, or None if embeddings are disabled/unavailable."""
        if self.cfg.provider == "disabled":
            return None

        if self.cfg.provider == "openai":
            if not self.cfg.openai_api_key:
                return None
            # Lazy import: keep base runtime light.
            import httpx

            url = os.getenv("ODP_OPENAI_BASE_URL", "https://api.openai.com/v1/embeddings")
            headers = {"authorization": f"Bearer {self.cfg.openai_api_key}"}
            payload: dict[str, Any] = {"model": self.cfg.openai_model, "input": text_}
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
            try:
                return list(data["data"][0]["embedding"])
            except Exception:
                return None

        # Unknown provider.
        return None
