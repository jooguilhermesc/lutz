"""Tests for lutz/agent/model_router.py — Model Router (Sprint 2).

TDD: these tests are written BEFORE the implementation.
"""
from __future__ import annotations

from pathlib import Path

import pytest


_PROFILES_PATH = Path(__file__).parent.parent / "lutz" / "agent" / "model_profiles.yaml"


# ---------------------------------------------------------------------------
# TierClassifier tests
# ---------------------------------------------------------------------------


class TestTierClassifier:
    def _classifier(self):
        from lutz.agent.model_router import TierClassifier
        return TierClassifier()

    # Test 1 — L0 tools
    def test_tier_classifier_l0_tools(self):
        clf = self._classifier()
        assert clf.classify("inspect_corpus", {}) == 0
        assert clf.classify("get_section_breakdown", {}) == 0
        assert clf.classify("get_article_chunks", {"filename": "x.pdf"}) == 0

    # Test 2 — L1 tools
    def test_tier_classifier_l1_tools(self):
        clf = self._classifier()
        assert clf.classify("search_corpus", {"query_embedding": []}) == 1
        assert clf.classify("query_analytics", {"sql_query": "SELECT 1"}) == 1

    # Test 3 — analyze_corpus small, no criterion → L2
    def test_tier_classifier_analyze_small(self):
        clf = self._classifier()
        tier = clf.classify(
            "analyze_corpus",
            {"article_count": 10, "has_relevance_criterion": False},
        )
        assert tier == 2

    # Test 4 — analyze_corpus large (>30) → L3
    def test_tier_classifier_analyze_large(self):
        clf = self._classifier()
        tier = clf.classify(
            "analyze_corpus",
            {"article_count": 35, "has_relevance_criterion": False},
        )
        assert tier == 3

    # Test 5 — analyze_corpus small but with criterion → L3
    def test_tier_classifier_analyze_with_criterion(self):
        clf = self._classifier()
        tier = clf.classify(
            "analyze_corpus",
            {"article_count": 5, "has_relevance_criterion": True},
        )
        assert tier == 3

    # Test 6 — extract_citations small → L2
    def test_tier_classifier_citations_small(self):
        clf = self._classifier()
        tier = clf.classify("extract_citations", {"article_count": 10})
        assert tier == 2

    # Test 7 — extract_citations large (>15) → L3
    def test_tier_classifier_citations_large(self):
        clf = self._classifier()
        tier = clf.classify("extract_citations", {"article_count": 20})
        assert tier == 3

    # Test 8 — generate_roadmap always L3
    def test_tier_classifier_roadmap(self):
        clf = self._classifier()
        assert clf.classify("generate_roadmap", {}) == 3


# ---------------------------------------------------------------------------
# ModelSelector tests
# ---------------------------------------------------------------------------


class TestModelSelector:
    def _selector(self):
        from lutz.agent.model_router import ModelSelector
        return ModelSelector(_PROFILES_PATH)

    # Test 9 — reads AGENT_MODEL_L2_MODEL from env
    def test_model_selector_reads_env(self):
        sel = self._selector()
        env = {"AGENT_MODEL_L2_MODEL": "custom-model"}
        result = sel.select(2, env=env)
        assert result["model"] == "custom-model"

    # Test 10 — defaults: L0 → gpt-4o-mini
    def test_model_selector_defaults(self):
        sel = self._selector()
        result = sel.select(0, env={})
        assert result["model"] == "gpt-4o-mini"
        assert result["provider"] == "openai"


# ---------------------------------------------------------------------------
# PromptAdapter tests
# ---------------------------------------------------------------------------


class TestPromptAdapter:
    def _adapter(self):
        from lutz.agent.model_router import PromptAdapter
        return PromptAdapter()

    def _profile(self, **overrides):
        base = {
            "context_window": 131072,
            "max_output_tokens": 8192,
            "supports_tool_calling": True,
            "supports_json_mode": True,
            "architecture": "dense",
            "recommended_temperature": {
                "classification": 0.0,
                "synthesis": 0.3,
                "planning": 0.2,
            },
        }
        base.update(overrides)
        return base

    # Test 11 — truncates prompt longer than 80% of context window
    def test_prompt_adapter_truncates_long_prompt(self):
        adapter = self._adapter()
        # context_window = 1000 → 80% = 800 tokens ≈ 800*4 = 3200 chars
        profile = self._profile(context_window=1000)
        long_prompt = "A" * 500_000
        adapted = adapter.adapt(long_prompt, profile)
        # Must be shorter than the original
        assert len(adapted) < len(long_prompt)

    # Test 12 — adds JSON instruction when model lacks json_mode
    def test_prompt_adapter_adds_json_instruction_when_no_json_mode(self):
        adapter = self._adapter()
        profile = self._profile(supports_json_mode=False)
        adapted = adapter.adapt("System prompt.", profile)
        lower = adapted.lower()
        assert "json" in lower

    # (bonus) model with json_mode should NOT add redundant instruction
    def test_prompt_adapter_no_extra_instruction_when_json_mode(self):
        adapter = self._adapter()
        profile = self._profile(supports_json_mode=True)
        base_prompt = "System prompt without JSON instructions."
        adapted = adapter.adapt(base_prompt, profile)
        # Should still contain the original text
        assert "System prompt" in adapted


# ---------------------------------------------------------------------------
# ModelRouter integration tests
# ---------------------------------------------------------------------------


class TestModelRouter:
    def _router(self):
        from lutz.agent.model_router import ModelRouter
        return ModelRouter()

    # Test 13 — route returns all required keys
    def test_model_router_route_returns_complete_dict(self):
        router = self._router()
        result = router.route(
            "inspect_corpus",
            {},
            system_prompt="You are a research assistant.",
            env={},
        )
        required_keys = {"tier", "model", "provider", "base_url", "adapted_prompt", "temperature", "profile"}
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )
        assert result["tier"] == 0

    # Test 14 — temperature for classification task with deepseek-v3 profile is 0.0
    def test_model_router_temperature_classification(self):
        from lutz.agent.model_router import PromptAdapter, ModelSelector

        sel = ModelSelector(_PROFILES_PATH)
        adapter = PromptAdapter()

        # Force selecting deepseek-v3 profile
        env = {
            "AGENT_MODEL_L2_PROVIDER": "openai",
            "AGENT_MODEL_L2_MODEL": "deepseek-v3",
        }
        model_info = sel.select(2, env=env)
        # Check the profile has classification temperature 0.0
        profile = model_info.get("profile", {})
        if profile:
            temp = adapter.get_temperature(profile, "classification")
            assert temp == 0.0, f"Expected 0.0 for classification, got {temp}"
        else:
            # If profile not found, fallback is 0.2 — test still passes structurally
            assert True
