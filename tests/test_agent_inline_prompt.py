"""Tests for the inline_prompt fix in analyze_corpus and _build_job_args.

TDD RED phase: these tests are written BEFORE the fix.

Bug: _handle_analyze_corpus in lutz/agent/tools.py sets body["prompt"] = prompt_text,
but _build_job_args in lutz/server/app.py treats body["prompt"] as a filename,
not as inline text. The fix uses body["inline_prompt"] so _build_job_args
routes through the temp-file path correctly.
"""
from __future__ import annotations

import pathlib
import tempfile
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_manager() -> MagicMock:
    """Return a mock JobManager whose .create() returns a job with a UUID id."""
    jm = MagicMock()
    fake_job = MagicMock()
    fake_job.id = "test-job-uuid"
    jm.create.return_value = fake_job
    return jm


# ---------------------------------------------------------------------------
# Test 1 — analyze_corpus puts prompt text in inline_prompt, not prompt
# ---------------------------------------------------------------------------


def test_analyze_corpus_uses_inline_prompt():
    """body["inline_prompt"] must carry the prompt text; body["prompt"] must be absent."""
    from lutz.agent.tools import _handle_analyze_corpus

    jm = _make_job_manager()
    _handle_analyze_corpus(
        {"prompt": "Avaliar relevância dos artigos", "mode": "rag", "top_k": 5},
        job_manager=jm,
    )

    jm.create.assert_called_once()
    _, _, body = jm.create.call_args.args  # create(type_, title, body)
    assert "inline_prompt" in body, (
        "body deve ter 'inline_prompt', não 'prompt', para _build_job_args funcionar corretamente"
    )
    assert body["inline_prompt"] == "Avaliar relevância dos artigos"
    # 'prompt' key must not exist so _build_job_args doesn't treat it as a filename
    assert "prompt" not in body, (
        "body não deve ter 'prompt' (seria tratado como nome de arquivo por _build_job_args)"
    )


# ---------------------------------------------------------------------------
# Test 2 — analyze_corpus result still has status/job_id/job_type
# ---------------------------------------------------------------------------


def test_analyze_corpus_result_shape():
    """Return value must still have status=queued, job_id and job_type."""
    from lutz.agent.tools import _handle_analyze_corpus

    jm = _make_job_manager()
    result = _handle_analyze_corpus(
        {"prompt": "Minha análise", "mode": "per_article"},
        job_manager=jm,
    )

    assert result["status"] == "queued"
    assert result["job_id"] == "test-job-uuid"
    assert result["job_type"] == "analysis"


# ---------------------------------------------------------------------------
# Test 3 — _build_job_args with inline_prompt writes a temp file and uses it
# ---------------------------------------------------------------------------


def test_build_job_args_inline_prompt():
    """_build_job_args with inline_prompt creates a temp .md file with that content."""
    from lutz.server.app import _build_job_args

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = pathlib.Path(tmp_dir)
        (root / "prompts").mkdir()

        body = {"inline_prompt": "Analisar relevância dos estudos", "mode": "rag"}
        args, title = _build_job_args("analysis", body, root)

        # args must contain --p <path>
        assert "--p" in args, "args deve conter '--p'"
        p_idx = args.index("--p") + 1
        prompt_file = pathlib.Path(args[p_idx])

        assert prompt_file.exists(), "Arquivo temporário de prompt deve existir"
        content = prompt_file.read_text(encoding="utf-8")
        assert content == "Analisar relevância dos estudos"

        # cleanup (simulating _run_job cleanup)
        prompt_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 4 — _build_job_args with named prompt file still works (no regression)
# ---------------------------------------------------------------------------


def test_build_job_args_file_prompt_still_works():
    """Prompt by filename (lutz analysis --prompt meu_prompt.md) must not break."""
    from lutz.server.app import _build_job_args

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = pathlib.Path(tmp_dir)
        prompts_dir = root / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "meu_prompt.md").write_text("Critério de inclusão", encoding="utf-8")

        body = {"prompt": "meu_prompt", "mode": "per_article"}
        args, title = _build_job_args("analysis", body, root)

        assert "--p" in args
        p_idx = args.index("--p") + 1
        prompt_path = pathlib.Path(args[p_idx])
        assert prompt_path.name == "meu_prompt.md"
        assert "meu_prompt" in title


# ---------------------------------------------------------------------------
# Test 5 — inline_prompt file can be cleaned up after job
# ---------------------------------------------------------------------------


def test_inline_prompt_file_cleaned_up():
    """The temp file created for inline_prompt can be deleted without error."""
    from lutz.server.app import _build_job_args

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = pathlib.Path(tmp_dir)
        (root / "prompts").mkdir()

        body = {"inline_prompt": "Texto do prompt para limpeza", "mode": "rag"}
        args, _ = _build_job_args("analysis", body, root)

        p_idx = args.index("--p") + 1
        tmp_prompt = pathlib.Path(args[p_idx])
        assert tmp_prompt.exists()

        # Simulate cleanup in _run_job finally block
        tmp_prompt.unlink(missing_ok=True)
        assert not tmp_prompt.exists(), "Arquivo temporário deve ser deletável sem erros"


# ---------------------------------------------------------------------------
# Test 6 — no job_manager falls back gracefully (unchanged behavior)
# ---------------------------------------------------------------------------


def test_analyze_corpus_no_job_manager_fallback():
    """Without job_manager, analyze_corpus returns stub with note."""
    from lutz.agent.tools import _handle_analyze_corpus

    result = _handle_analyze_corpus(
        {"prompt": "Texto qualquer"},
        job_manager=None,
    )

    assert result["status"] == "queued"
    assert "job_id" in result
    assert result.get("note") == "no job_manager"
