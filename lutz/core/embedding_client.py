"""Embedding client — unified interface for multiple providers.

Supported providers (configured via .env):
    docker_model_runner   — Docker Model Runner (OpenAI-compatible, local)
    openai                — OpenAI API or any OpenAI-compatible endpoint
    openrouter            — OpenRouter (openrouter.ai) multi-provider gateway
    sentence_transformers — local model via sentence-transformers (no API key)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SentenceTransformer singleton cache — avoids reloading the model from disk
# on every embed() call (loading takes 2-5 seconds per model).
# ---------------------------------------------------------------------------
_ST_MODEL_CACHE: dict[str, Any] = {}
_ST_MODEL_LOCK = threading.Lock()


def _get_st_model(model_id: str) -> Any:
    """Return a cached SentenceTransformer instance, loading once per process."""
    if model_id not in _ST_MODEL_CACHE:
        with _ST_MODEL_LOCK:
            if model_id not in _ST_MODEL_CACHE:  # double-check inside lock
                from sentence_transformers import SentenceTransformer
                logger.debug("Loading SentenceTransformer model '%s' (first use)", model_id)
                _ST_MODEL_CACHE[model_id] = SentenceTransformer(model_id)
    return _ST_MODEL_CACHE[model_id]


class EmbeddingClient:
    """Generate text embeddings from a configured provider."""

    def __init__(self, provider: str, model_id: str, **kwargs: Any) -> None:
        self.provider = provider
        self.model_id = model_id
        self._kwargs = kwargs
        # Lazy-initialised on the first embed() call.  A lock ensures the
        # client is created exactly once even under concurrent access.
        self._client: Any = None
        self._client_lock = threading.Lock()

    def _get_openai_client(self) -> Any:
        """Return the OpenAI SDK client, initialising it on first call (thread-safe)."""
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is not None:  # double-check inside lock
                return self._client
            from openai import OpenAI

            client_kwargs: dict[str, Any] = {"api_key": self._kwargs.get("api_key", "dummy")}
            if base_url := self._kwargs.get("base_url"):
                client_kwargs["base_url"] = base_url
            self._client = OpenAI(**client_kwargs)
        return self._client

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "EmbeddingClient":
        """Instantiate the right client based on environment variables.

        Reads:
            EMBEDDING_PROVIDER  — docker_model_runner | openai | openrouter | sentence_transformers
            EMBEDDING_MODEL     — model identifier
            OPENAI_API_KEY      — required when provider=openai
            OPENAI_BASE_URL     — optional custom base URL for openai-compatible APIs
            OPENROUTER_API_KEY  — required when provider=openrouter
            DOCKER_MODEL_HOST   — base URL for Docker Model Runner (default: auto-detect)
        """
        provider = env.get("EMBEDDING_PROVIDER", "sentence_transformers").lower()
        model_id = env.get("EMBEDDING_MODEL", _default_embedding_model(provider))

        match provider:
            case "docker_model_runner":
                base_url = env.get(
                    "DOCKER_MODEL_HOST",
                    "http://model-runner.docker.internal/engines/v1",
                )
                api_key = env.get("DOCKER_MODEL_API_KEY", "docker-model-runner")
                return cls(provider=provider, model_id=model_id, base_url=base_url, api_key=api_key)

            case "openai":
                api_key = env.get("OPENAI_API_KEY", "")
                base_url = env.get("OPENAI_BASE_URL", None)
                if not api_key:
                    raise ValueError(
                        "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai. "
                        "Set it in your .env file."
                    )
                return cls(provider=provider, model_id=model_id, api_key=api_key, base_url=base_url)

            case "openrouter":
                api_key = env.get("OPENROUTER_API_KEY", "")
                if not api_key:
                    raise ValueError(
                        "OPENROUTER_API_KEY is required when EMBEDDING_PROVIDER=openrouter. "
                        "Set it in your .env file."
                    )
                return cls(
                    provider=provider,
                    model_id=model_id,
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                )

            case "sentence_transformers":
                return cls(provider=provider, model_id=model_id)

            case _:
                raise ValueError(
                    f"Unknown EMBEDDING_PROVIDER '{provider}'. "
                    "Valid options: docker_model_runner, openai, openrouter, sentence_transformers."
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Return (embeddings, total_tokens).

        total_tokens is the number of tokens consumed by the embedding API.
        For sentence_transformers (local), it is estimated (~4 chars per token).
        """
        match self.provider:
            case "docker_model_runner" | "openai" | "openrouter":
                return self._embed_openai(texts)
            case "sentence_transformers":
                return self._embed_sentence_transformers(texts)
            case _:
                raise RuntimeError(f"Unsupported provider: {self.provider}")

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _embed_openai(self, texts: list[str]) -> tuple[list[list[float]], int]:
        batch_size = 256
        all_embeddings: list[list[float]] = []
        total_tokens = 0
        client = self._get_openai_client()
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = client.embeddings.create(
                model=self.model_id, input=batch, encoding_format="float"
            )
            all_embeddings.extend([item.embedding for item in response.data])
            if response.usage:
                total_tokens += response.usage.total_tokens

        return all_embeddings, total_tokens

    def _embed_sentence_transformers(self, texts: list[str]) -> tuple[list[list[float]], int]:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Run: pip install lutz-research[local]\n"
                "Or set EMBEDDING_PROVIDER=openai / docker_model_runner to avoid this dependency."
            ) from exc

        model = _get_st_model(self.model_id)
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        # sentence_transformers is local — estimate tokens (~4 chars per token)
        estimated_tokens = sum(len(t) // 4 for t in texts)
        return embeddings.tolist(), estimated_tokens


def _default_embedding_model(provider: str) -> str:
    match provider:
        case "openai" | "openrouter":
            return "text-embedding-3-small"
        case "docker_model_runner":
            return "nomic-embed-text"
        case _:
            return "all-MiniLM-L6-v2"
