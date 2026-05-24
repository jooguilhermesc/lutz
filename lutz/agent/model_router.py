"""Model Router for the Lutz agentic layer.

Implements three components:
- TierClassifier: classifies each tool call into L0-L3 complexity tiers
- ModelSelector: selects the best model for a given tier from env config
- PromptAdapter: adapts system prompts for specific model capabilities
- ModelRouter: combines the three components into a single routing call

Configuration via environment variables (see docs/agentic-chat-architecture.md §5).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PROFILES_PATH = Path(__file__).parent / "model_profiles.yaml"

# Default model configurations per tier (fallback when env not set)
_TIER_DEFAULTS: dict[int, dict[str, str]] = {
    0: {"provider": "openai", "model": "gpt-4o-mini", "base_url": ""},
    1: {"provider": "openai", "model": "gpt-4o-mini", "base_url": ""},
    2: {
        "provider": "openai",
        "model": "deepseek/deepseek-chat-v3",
        "base_url": "https://openrouter.ai/api/v1",
    },
    3: {
        "provider": "openai",
        "model": "deepseek/deepseek-r1",
        "base_url": "https://openrouter.ai/api/v1",
    },
}

# Approximate chars-per-token ratio used for context window estimation.
# Conservative: assumes 4 chars/token (typical for English + code).
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# TierClassifier
# ---------------------------------------------------------------------------


class TierClassifier:
    """Classify a tool call into a complexity tier (L0-L3).

    Algorithm matches the spec in docs/agentic-chat-architecture.md §3.
    """

    def classify(self, tool_name: str, tool_input: dict) -> int:
        """Return the tier (0, 1, 2, or 3) for the given tool call."""
        # L0: deterministic ops, no LLM
        if tool_name in ("inspect_corpus", "get_section_breakdown", "get_article_chunks"):
            return 0

        # L1: simple searches and queries
        if tool_name in ("search_corpus", "query_analytics"):
            return 1

        # L2 vs L3: analyze_corpus — depends on size and criterion
        if tool_name == "analyze_corpus":
            article_count = int(tool_input.get("article_count", 0))
            has_relevance_criterion = bool(tool_input.get("has_relevance_criterion", False))
            if article_count > 30 or has_relevance_criterion:
                return 3
            return 2

        # L2 vs L3: extract_citations — depends on article count
        if tool_name == "extract_citations":
            article_count = int(tool_input.get("article_count", 0))
            return 3 if article_count > 15 else 2

        # Roadmap always needs deep synthesis → L3
        if tool_name == "generate_roadmap":
            return 3

        # Unknown tools default to L1 (safe middle ground)
        return 1


# ---------------------------------------------------------------------------
# ModelSelector
# ---------------------------------------------------------------------------


class ModelSelector:
    """Select the best model for a given tier.

    Reads AGENT_MODEL_L{tier}_PROVIDER, AGENT_MODEL_L{tier}_MODEL,
    AGENT_MODEL_L{tier}_BASE_URL from the provided env dict (or os.environ
    when env is None).

    Returns a dict with keys: provider, model, base_url, profile.
    """

    def __init__(self, profiles_path: Path = _DEFAULT_PROFILES_PATH) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}
        if profiles_path.exists():
            with profiles_path.open("r", encoding="utf-8") as fh:
                self._profiles = yaml.safe_load(fh) or {}

    # ------------------------------------------------------------------

    def get_profile(self, model_id: str) -> dict[str, Any]:
        """Return the profile for *model_id*, or {} if not found.

        Attempts exact match first, then a case-insensitive fuzzy match
        against the simple model name (last segment after '/').
        """
        if model_id in self._profiles:
            return self._profiles[model_id]
        # Fuzzy: try the last path component (e.g. "deepseek/deepseek-v3" → "deepseek-v3")
        simple = model_id.split("/")[-1].lower()
        for key, profile in self._profiles.items():
            if key.lower() == simple:
                return profile
        return {}

    def select(self, tier: int, env: dict[str, str] | None = None) -> dict[str, Any]:
        """Return model configuration for the given tier."""
        env = env if env is not None else dict(os.environ)
        prefix = f"AGENT_MODEL_L{tier}"

        defaults = _TIER_DEFAULTS.get(tier, _TIER_DEFAULTS[1])
        provider = env.get(f"{prefix}_PROVIDER", defaults["provider"])
        model = env.get(f"{prefix}_MODEL", defaults["model"])
        base_url = env.get(f"{prefix}_BASE_URL", defaults.get("base_url", ""))

        profile = self.get_profile(model)

        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "profile": profile,
        }


# ---------------------------------------------------------------------------
# PromptAdapter
# ---------------------------------------------------------------------------


class PromptAdapter:
    """Adapt a system prompt for the capabilities and limits of a model.

    Responsibilities:
    1. Truncate prompts that exceed 80% of the model's context window.
    2. Add explicit JSON output instructions when the model lacks json_mode.
    3. Add tool-simulation instructions when the model lacks native tool calling.
    """

    _JSON_INSTRUCTION = (
        "\n\nIMPORTANT: You do not support native JSON mode. "
        "Always respond with valid JSON wrapped in ```json ... ``` code blocks. "
        "Do not include any text outside the JSON block."
    )

    _TOOL_SIMULATION_INSTRUCTION = (
        "\n\nIMPORTANT: You do not support native function/tool calling. "
        "When you want to call a tool, respond with a JSON object in this format:\n"
        '{"tool_call": {"name": "<tool_name>", "arguments": {...}}}'
    )

    def adapt(self, system_prompt: str, model_profile: dict) -> str:
        """Return an adapted version of *system_prompt* for *model_profile*."""
        context_window: int = model_profile.get("context_window", 131072)
        supports_json_mode: bool = model_profile.get("supports_json_mode", True)
        supports_tool_calling: bool = model_profile.get("supports_tool_calling", True)

        adapted = system_prompt

        # --- Truncation ---
        # Budget: 80% of context window in tokens, converted to chars
        max_chars = int(context_window * 0.8 * _CHARS_PER_TOKEN)
        if len(adapted) > max_chars:
            # Keep a tail sentinel so the model knows the prompt was cut
            sentinel = "\n\n[Prompt truncated to fit context window]"
            adapted = adapted[: max_chars - len(sentinel)] + sentinel

        # --- JSON mode instruction ---
        if not supports_json_mode:
            adapted += self._JSON_INSTRUCTION

        # --- Tool calling simulation ---
        if not supports_tool_calling:
            adapted += self._TOOL_SIMULATION_INSTRUCTION

        return adapted

    def get_temperature(self, model_profile: dict, task_type: str) -> float:
        """Return the recommended temperature for *task_type*.

        Falls back to 0.2 when the profile does not specify a value for *task_type*.
        """
        rec_temp = model_profile.get("recommended_temperature", {})
        return float(rec_temp.get(task_type, 0.2))


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


class ModelRouter:
    """Route a tool call to the appropriate model configuration.

    Combines TierClassifier, ModelSelector, and PromptAdapter into a single
    entry point used by the orchestrator.
    """

    def __init__(self, profiles_path: Path | None = None) -> None:
        self.classifier = TierClassifier()
        self.selector = ModelSelector(profiles_path or _DEFAULT_PROFILES_PATH)
        self.adapter = PromptAdapter()

    def route(
        self,
        tool_name: str,
        tool_input: dict,
        system_prompt: str = "",
        env: dict[str, str] | None = None,
        task_type: str = "synthesis",
    ) -> dict[str, Any]:
        """Classify, select model, and adapt prompt for *tool_name*.

        Returns
        -------
        dict with keys:
            tier, model, provider, base_url, adapted_prompt, temperature, profile
        """
        tier = self.classifier.classify(tool_name, tool_input)
        model_info = self.selector.select(tier, env=env)
        profile = model_info.get("profile", {})
        adapted_prompt = self.adapter.adapt(system_prompt, profile) if profile else system_prompt
        temperature = self.adapter.get_temperature(profile, task_type) if profile else 0.2

        return {
            "tier": tier,
            "model": model_info["model"],
            "provider": model_info["provider"],
            "base_url": model_info["base_url"],
            "adapted_prompt": adapted_prompt,
            "temperature": temperature,
            "profile": profile,
        }
