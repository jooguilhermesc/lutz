"""LLM client — unified interface for multiple providers.

Supported providers (configured via .env):
    docker_model_runner — Docker Model Runner (OpenAI-compatible, local)
    openai              — OpenAI API or any OpenAI-compatible endpoint
    anthropic           — Anthropic Claude API
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 4096


class LLMClient:
    """Send prompts to an LLM and return the text response."""

    def __init__(self, provider: str, model_id: str, **kwargs: Any) -> None:
        self.provider = provider
        self.model_id = model_id
        self._kwargs = kwargs

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "LLMClient":
        """Instantiate the right client based on environment variables.

        Reads:
            LLM_PROVIDER        — docker_model_runner | openai | anthropic
            LLM_MODEL           — model identifier
            OPENAI_API_KEY      — required when provider=openai
            OPENAI_BASE_URL     — optional custom base URL for openai-compatible APIs
            ANTHROPIC_API_KEY   — required when provider=anthropic
            DOCKER_MODEL_HOST   — base URL for Docker Model Runner (default: auto-detect)
            LLM_MAX_TOKENS      — max tokens in the response (default: 4096)
            LLM_TEMPERATURE     — temperature (default: 0.2)
        """
        provider = env.get("LLM_PROVIDER", "docker_model_runner").lower()
        max_tokens = int(env.get("LLM_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))
        temperature = float(env.get("LLM_TEMPERATURE", "0.2"))

        match provider:
            case "docker_model_runner":
                model_id = env.get("LLM_MODEL", "ai/llama3.2")
                base_url = env.get(
                    "DOCKER_MODEL_HOST",
                    "http://model-runner.docker.internal/engines/v1",
                )
                api_key = env.get("DOCKER_MODEL_API_KEY", "docker-model-runner")
                return cls(
                    provider=provider,
                    model_id=model_id,
                    base_url=base_url,
                    api_key=api_key,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            case "openai":
                model_id = env.get("LLM_MODEL", "gpt-4o-mini")
                api_key = env.get("OPENAI_API_KEY", "")
                base_url = env.get("OPENAI_BASE_URL", None)
                if not api_key:
                    raise ValueError(
                        "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
                        "Set it in your .env file."
                    )
                return cls(
                    provider=provider,
                    model_id=model_id,
                    api_key=api_key,
                    base_url=base_url,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            case "anthropic":
                model_id = env.get("LLM_MODEL", "claude-haiku-4-5-20251001")
                api_key = env.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    raise ValueError(
                        "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                        "Set it in your .env file."
                    )
                return cls(
                    provider=provider,
                    model_id=model_id,
                    api_key=api_key,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            case _:
                raise ValueError(
                    f"Unknown LLM_PROVIDER '{provider}'. "
                    "Valid options: docker_model_runner, openai, anthropic."
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(self, system: str, user: str) -> tuple[str, dict]:
        """Send a system + user prompt and return (text, usage).

        usage dict keys: prompt_tokens, completion_tokens, total_tokens.
        Counts are 0 when the provider does not report them.
        """
        match self.provider:
            case "docker_model_runner" | "openai":
                return self._complete_openai(system, user)
            case "anthropic":
                return self._complete_anthropic(system, user)
            case _:
                raise RuntimeError(f"Unsupported provider: {self.provider}")

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _complete_openai(self, system: str, user: str) -> tuple[str, dict]:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {"api_key": self._kwargs.get("api_key", "dummy")}
        if base_url := self._kwargs.get("base_url"):
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=self._kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS),
            temperature=self._kwargs.get("temperature", 0.2),
        )
        text = response.choices[0].message.content or ""
        u = response.usage
        usage = {
            "prompt_tokens": u.prompt_tokens if u else 0,
            "completion_tokens": u.completion_tokens if u else 0,
            "total_tokens": u.total_tokens if u else 0,
        }
        return text, usage

    def _complete_anthropic(self, system: str, user: str) -> tuple[str, dict]:
        import anthropic

        client = anthropic.Anthropic(api_key=self._kwargs["api_key"])
        response = client.messages.create(
            model=self.model_id,
            max_tokens=self._kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS),
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=self._kwargs.get("temperature", 0.2),
        )
        text = response.content[0].text
        u = response.usage
        usage = {
            "prompt_tokens": u.input_tokens if u else 0,
            "completion_tokens": u.output_tokens if u else 0,
            "total_tokens": (u.input_tokens + u.output_tokens) if u else 0,
        }
        return text, usage
