"""Tests for F1 (library search) and F4 (reasoning control) in _run_chat().

TDD: these tests are written BEFORE the production code changes.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env(provider: str = "openai") -> dict:
    base = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": "gpt-4o-mini",
        "EMBEDDING_PROVIDER": "openai",
        "EMBEDDING_MODEL": "text-embedding-3-small",
    }
    if provider == "openai":
        base["OPENAI_API_KEY"] = "test-key"
    elif provider == "anthropic":
        base["ANTHROPIC_API_KEY"] = "test-key"
    return base


def _run_chat_import():
    from lutz.server.app import _run_chat
    return _run_chat


def _dummy_messages():
    return [{"role": "user", "content": "What is RAG?"}]


def _dummy_embedding():
    return [0.1] * 128


# ---------------------------------------------------------------------------
# F4 — Reasoning level
# ---------------------------------------------------------------------------

class TestReasoningLevel:

    def _run_with_reasoning(self, root, level, provider="openai"):
        """Helper: run _run_chat with a given reasoning_level and capture LLM call."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("response text", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = provider

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        with patch("lutz.server.app.load_env", return_value=_make_env(provider)), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock):

            options = {
                "use_rag": True,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 3,
                "reasoning_level": level,
            }
            result = _run_chat(root, _dummy_messages(), options, "pt", [])

        return llm_mock, result

    def test_fast_reasoning_uses_low_temperature(self, tmp_path):
        """F4: reasoning_level='fast' must pass temperature=0.1 to complete_messages."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock):

            options = {
                "use_rag": True,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 3,
                "reasoning_level": "fast",
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        _args, _kwargs = llm_mock.complete_messages.call_args
        assert _kwargs.get("temperature") == 0.1, (
            f"Expected temperature=0.1 for 'fast' reasoning, got {_kwargs.get('temperature')}"
        )

    def test_balanced_reasoning_is_default(self, tmp_path):
        """F4: reasoning_level='balanced' (default) must use temperature=0.2."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock):

            # No reasoning_level in options — should default to "balanced"
            options = {
                "use_rag": True,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 3,
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        _args, _kwargs = llm_mock.complete_messages.call_args
        got = _kwargs.get("temperature")
        assert got == 0.2, f"Expected temperature=0.2 for 'balanced' (default), got {got}"

    def test_deep_reasoning_appends_cot_instruction(self, tmp_path):
        """F4: reasoning_level='deep' must append chain-of-thought instruction to system prompt."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock):

            options = {
                "use_rag": True,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 3,
                "reasoning_level": "deep",
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        _args, _kwargs = llm_mock.complete_messages.call_args
        system = _kwargs.get("system") or (_args[0] if _args else "")
        assert "passo a passo" in system or "step by step" in system.lower(), (
            "Expected CoT instruction in system prompt for 'deep' reasoning"
        )
        assert _kwargs.get("temperature") == 0.3, (
            f"Expected temperature=0.3 for 'deep' reasoning, got {_kwargs.get('temperature')}"
        )

    def test_deep_reasoning_temperature(self, tmp_path):
        """F4: reasoning_level='deep' must use temperature=0.3."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 3,
                "reasoning_level": "deep",
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        _args, _kwargs = llm_mock.complete_messages.call_args
        assert _kwargs.get("temperature") == 0.3


# ---------------------------------------------------------------------------
# F1 — Library search (VectorStore integration)
# ---------------------------------------------------------------------------

class TestLibrarySearch:

    def test_library_search_called_when_use_library_true(self, tmp_path):
        """F1: when use_library=True, VectorStore.search() must be called."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()
        vector_store_mock.search.return_value = [
            {"filename": "art.pdf", "page": 1, "text": "relevant chunk"}
        ]

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
                "use_library": True,
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        vector_store_mock.search.assert_called_once()

    def test_library_search_not_called_when_false(self, tmp_path):
        """F1: when use_library=False (default), VectorStore.search() must NOT be called."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
                "use_library": False,
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        vector_store_mock.search.assert_not_called()

    def test_library_search_not_called_when_absent(self, tmp_path):
        """F1: when use_library is absent from options, VectorStore.search() must NOT be called."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        vector_store_mock.search.assert_not_called()

    def test_library_empty_does_not_crash(self, tmp_path):
        """F1: when VectorStore returns empty list, _run_chat must complete normally."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()
        vector_store_mock.search.return_value = []

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
                "use_library": True,
            }
            result = _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        assert result["response"] == "answer"
        assert result["sources"] == []

    def test_library_chunks_injected_with_biblioteca_prefix(self, tmp_path):
        """F1: chunks from library must be injected with '[Biblioteca:' prefix in system prompt."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()
        vector_store_mock.search.return_value = [
            {"filename": "paper.pdf", "page": 3, "text": "LLM is great"}
        ]

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
                "use_library": True,
            }
            _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        _args, _kwargs = llm_mock.complete_messages.call_args
        system = _kwargs.get("system") or (_args[0] if _args else "")
        assert "[Biblioteca:" in system, (
            f"Expected '[Biblioteca:' prefix in system prompt, got:\n{system}"
        )

    def test_library_sources_included_in_response(self, tmp_path):
        """F1: sources from library search must be included in the returned sources list."""
        _run_chat = _run_chat_import()

        emb_mock = MagicMock()
        emb_mock.embed.return_value = ([_dummy_embedding()], {})

        llm_mock = MagicMock()
        llm_mock.complete_messages.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        })
        llm_mock.provider = "openai"

        context_store_mock = MagicMock()
        context_store_mock.is_empty.return_value = True

        vector_store_mock = MagicMock()
        vector_store_mock.search.return_value = [
            {"filename": "paper.pdf", "page": 3, "text": "LLM is great"}
        ]

        with patch("lutz.server.app.load_env", return_value=_make_env()), \
             patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock), \
             patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock), \
             patch("lutz.server.app.ContextStore", return_value=context_store_mock), \
             patch("lutz.server.app.VectorStore", return_value=vector_store_mock):

            options = {
                "use_rag": False,
                "use_model_knowledge": True,
                "use_context_files": False,
                "top_k": 5,
                "use_library": True,
            }
            result = _run_chat(tmp_path, _dummy_messages(), options, "pt", [])

        assert any(s["filename"] == "paper.pdf" for s in result["sources"]), (
            f"Expected paper.pdf in sources, got: {result['sources']}"
        )


# ---------------------------------------------------------------------------
# F4 — LLMClient.complete_messages temperature parameter
# ---------------------------------------------------------------------------

class TestLLMClientTemperature:

    def test_complete_messages_accepts_temperature_kwarg(self):
        """LLMClient.complete_messages must accept and forward temperature kwarg."""
        from lutz.core.llm_client import LLMClient

        client = LLMClient(
            provider="openai",
            model_id="gpt-4o-mini",
            api_key="dummy",
            max_tokens=100,
            temperature=0.5,
        )

        openai_client_mock = MagicMock()
        choice = MagicMock()
        choice.message.content = "hello"
        response = MagicMock()
        response.choices = [choice]
        response.usage.prompt_tokens = 5
        response.usage.completion_tokens = 5
        response.usage.total_tokens = 10
        openai_client_mock.chat.completions.create.return_value = response

        with patch.object(client, "_get_client", return_value=openai_client_mock):
            text, usage = client.complete_messages(
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.1,
            )

        call_kwargs = openai_client_mock.chat.completions.create.call_args[1]
        assert call_kwargs.get("temperature") == 0.1, (
            f"Expected temperature=0.1 forwarded to API, got {call_kwargs.get('temperature')}"
        )
