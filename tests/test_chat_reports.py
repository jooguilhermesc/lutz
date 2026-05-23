"""Tests for F2 — Integração com Relatórios de Análise no chat.

Covers:
  1. test_list_reports_empty_when_no_dir — diretório não existe → {"reports": []}
  2. test_list_reports_returns_metadata — cria JSON de teste, verifica id, analysis_type, article_count
  3. test_run_chat_injects_selected_report — mock do LLM, passa selected_report_ids, verifica system prompt
  4. test_run_chat_ignores_missing_report — ID inexistente → não lança exceção
  5. test_run_chat_truncates_large_report — JSON com 200 artigos → contexto ≤ 8000 chars
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers para mock de LLM/Embedding (padrão do projeto)
# ---------------------------------------------------------------------------

def _make_env() -> dict:
    return {
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-4o-mini",
        "OPENAI_API_KEY": "test-key",
        "EMBEDDING_PROVIDER": "openai",
        "EMBEDDING_MODEL": "text-embedding-3-small",
    }


def _make_llm_mock(response_text: str = "resposta mock") -> MagicMock:
    mock = MagicMock()
    mock.complete_messages.return_value = (
        response_text,
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    return mock


def _make_emb_mock() -> MagicMock:
    mock = MagicMock()
    mock.embed.return_value = ([[0.1] * 10], {})
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Minimal lutz project root with initialised SQLite DB."""
    lutz_dir = tmp_path / ".lutz"
    lutz_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=openai\nLLM_MODEL=gpt-4o-mini\nOPENAI_API_KEY=test-key\n"
        "EMBEDDING_PROVIDER=openai\nEMBEDDING_MODEL=text-embedding-3-small\n",
        encoding="utf-8",
    )
    from lutz.server import db as _db
    _db.init_db(tmp_path)
    return tmp_path


@pytest.fixture()
def client(project_root: Path) -> TestClient:
    """FastAPI TestClient wired to project_root."""
    from lutz.server.app import app

    os.environ["LUTZ_PROJECT_ROOT"] = str(project_root)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    os.environ.pop("LUTZ_PROJECT_ROOT", None)


@pytest.fixture()
def reports_dir(project_root: Path) -> Path:
    """Creates and returns the execution_reports directory."""
    d = project_root / "analysis" / "execution_reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_report(reports_dir: Path, name: str, data: dict) -> Path:
    """Helper to write a JSON report file and return the path."""
    path = reports_dir / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. GET /api/chat/reports — diretório inexistente
# ---------------------------------------------------------------------------

class TestListChatReportsEmpty:

    def test_list_reports_empty_when_no_dir(self, client: TestClient) -> None:
        """GET /api/chat/reports retorna {"reports": []} quando o diretório não existe."""
        resp = client.get("/api/chat/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert data["reports"] == []


# ---------------------------------------------------------------------------
# 2. GET /api/chat/reports — com relatório real
# ---------------------------------------------------------------------------

class TestListChatReportsMetadata:

    def test_list_reports_returns_metadata(
        self, client: TestClient, reports_dir: Path
    ) -> None:
        """GET /api/chat/reports retorna id, filename, analysis_type e article_count corretos."""
        report_data = {
            "analysis_type": "screening",
            "created_at": "2026-05-20T10:00:00Z",
            "results": [
                {"filename": "artigo1.pdf", "decision": "INCLUDE", "justification": "Relevante"},
                {"filename": "artigo2.pdf", "decision": "EXCLUDE", "justification": "Fora do escopo"},
            ],
        }
        _write_report(reports_dir, "screening_2026-05-20", report_data)

        resp = client.get("/api/chat/reports")
        assert resp.status_code == 200
        reports = resp.json()["reports"]
        assert len(reports) == 1

        r = reports[0]
        assert r["id"] == "screening_2026-05-20"
        assert r["filename"] == "screening_2026-05-20.json"
        assert r["analysis_type"] == "screening"
        assert r["article_count"] == 2
        assert r["timestamp"] == "2026-05-20T10:00:00Z"

    def test_list_reports_fallback_analysis_type(
        self, client: TestClient, reports_dir: Path
    ) -> None:
        """Quando analysis_type ausente, tenta campo 'type'; se ambos ausentes usa 'analysis'."""
        _write_report(reports_dir, "sem_tipo", {"results": []})

        resp = client.get("/api/chat/reports")
        reports = resp.json()["reports"]
        assert reports[0]["analysis_type"] == "analysis"

    def test_list_reports_uses_type_field_as_fallback(
        self, client: TestClient, reports_dir: Path
    ) -> None:
        """Quando analysis_type ausente mas 'type' presente, usa 'type'."""
        _write_report(reports_dir, "com_type", {"type": "qualidade", "results": []})

        resp = client.get("/api/chat/reports")
        reports = resp.json()["reports"]
        assert reports[0]["analysis_type"] == "qualidade"

    def test_list_reports_article_count_zero_when_no_results(
        self, client: TestClient, reports_dir: Path
    ) -> None:
        """article_count é 0 quando 'results' não existe no JSON."""
        _write_report(reports_dir, "sem_results", {"analysis_type": "test"})

        resp = client.get("/api/chat/reports")
        reports = resp.json()["reports"]
        assert reports[0]["article_count"] == 0

    def test_list_reports_timestamp_falls_back_to_mtime(
        self, client: TestClient, reports_dir: Path, project_root: Path
    ) -> None:
        """Quando created_at ausente, timestamp usa mtime do arquivo (string não vazia)."""
        _write_report(reports_dir, "sem_timestamp", {"analysis_type": "test", "results": []})

        resp = client.get("/api/chat/reports")
        reports = resp.json()["reports"]
        # Deve retornar algum timestamp (não vazio)
        assert reports[0]["timestamp"]


# ---------------------------------------------------------------------------
# 3. _run_chat injeta relatório selecionado no system prompt
# ---------------------------------------------------------------------------

class TestRunChatInjectsSelectedReport:

    def test_run_chat_injects_selected_report(
        self, project_root: Path, reports_dir: Path
    ) -> None:
        """_run_chat com selected_report_ids injeta '[Relatório:' no system prompt."""
        report_data = {
            "analysis_type": "screening",
            "created_at": "2026-05-20T10:00:00Z",
            "results": [
                {
                    "filename": "artigo1.pdf",
                    "decision": "INCLUDE",
                    "justification": "Muito relevante",
                    "title": "Artigo sobre NLP",
                },
            ],
        }
        _write_report(reports_dir, "test_report", report_data)

        captured_system: list[str] = []

        llm_mock = _make_llm_mock()

        def fake_complete_messages(system: str, messages: list, **kwargs):
            captured_system.append(system)
            return "resposta mock", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

        llm_mock.complete_messages.side_effect = fake_complete_messages
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        from lutz.server.app import _run_chat

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            result = _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Qual é o resultado?"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    "selected_report_ids": ["test_report"],
                },
                language="pt",
                memories=[],
            )

        assert len(captured_system) == 1
        system_prompt = captured_system[0]
        assert "[Relatório:" in system_prompt
        assert "test_report" in system_prompt
        assert "## Relatórios de Análise" in system_prompt

    def test_run_chat_sources_include_report(
        self, project_root: Path, reports_dir: Path
    ) -> None:
        """_run_chat com relatório selecionado adiciona fonte com page=0 no retorno."""
        report_data = {
            "analysis_type": "screening",
            "created_at": "2026-05-20T10:00:00Z",
            "results": [
                {"filename": "artigo1.pdf", "decision": "INCLUDE", "justification": "Ok"},
            ],
        }
        _write_report(reports_dir, "fonte_report", report_data)

        from lutz.server.app import _run_chat

        llm_mock = _make_llm_mock("resposta")
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            result = _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Pergunta"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    "selected_report_ids": ["fonte_report"],
                },
                language="pt",
                memories=[],
            )

        sources = result["sources"]
        report_sources = [s for s in sources if s["filename"] == "fonte_report.json"]
        assert len(report_sources) >= 1
        assert report_sources[0]["page"] == 0


# ---------------------------------------------------------------------------
# 4. _run_chat ignora relatório inexistente
# ---------------------------------------------------------------------------

class TestRunChatIgnoresMissingReport:

    def test_run_chat_ignores_missing_report(self, project_root: Path) -> None:
        """_run_chat com ID inexistente não lança exceção; chat continua normalmente."""
        from lutz.server.app import _run_chat

        llm_mock = _make_llm_mock("ok")
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            # Não deve lançar exceção
            result = _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Pergunta"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    "selected_report_ids": ["id_que_nao_existe"],
                },
                language="pt",
                memories=[],
            )

        # Chat deve ter completado normalmente
        assert result["response"] == "ok"

    def test_run_chat_empty_selected_report_ids_unchanged(
        self, project_root: Path
    ) -> None:
        """selected_report_ids=[] não altera comportamento — backward compatible."""
        from lutz.server.app import _run_chat

        captured_system: list[str] = []

        llm_mock = _make_llm_mock()

        def fake_complete(system: str, messages: list, **kwargs):
            captured_system.append(system)
            return "ok", {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}

        llm_mock.complete_messages.side_effect = fake_complete
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Oi"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    "selected_report_ids": [],
                },
                language="pt",
                memories=[],
            )

        # Não deve conter seção de relatórios
        assert "## Relatórios de Análise" not in captured_system[0]

    def test_run_chat_no_selected_report_ids_key_unchanged(
        self, project_root: Path
    ) -> None:
        """options sem selected_report_ids não altera comportamento — backward compatible."""
        from lutz.server.app import _run_chat

        captured_system: list[str] = []

        llm_mock = _make_llm_mock()

        def fake_complete(system: str, messages: list, **kwargs):
            captured_system.append(system)
            return "ok", {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}

        llm_mock.complete_messages.side_effect = fake_complete
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Oi"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    # sem selected_report_ids
                },
                language="pt",
                memories=[],
            )

        assert "## Relatórios de Análise" not in captured_system[0]


# ---------------------------------------------------------------------------
# 5. _run_chat trunca relatório grande
# ---------------------------------------------------------------------------

class TestRunChatTruncatesLargeReport:

    def test_run_chat_truncates_large_report(
        self, project_root: Path, reports_dir: Path
    ) -> None:
        """JSON com 200 artigos → contexto injetado ≤ 8000 chars no system prompt."""
        # Criar relatório com 200 artigos
        results = [
            {
                "filename": f"artigo_{i:03d}.pdf",
                "decision": "INCLUDE" if i % 2 == 0 else "EXCLUDE",
                "justification": (
                    f"Justificativa detalhada para o artigo número {i} com texto longo para inflar "
                    "o tamanho total do payload e garantir que o truncamento seja acionado "
                    "corretamente pelo mecanismo de proteção do context window."
                ),
                "title": f"Título do Artigo Científico Número {i}",
            }
            for i in range(200)
        ]
        report_data = {
            "analysis_type": "screening_grande",
            "created_at": "2026-05-20T10:00:00Z",
            "results": results,
        }
        _write_report(reports_dir, "large_report", report_data)

        captured_system: list[str] = []

        llm_mock = _make_llm_mock()

        def fake_complete(system: str, messages: list, **kwargs):
            captured_system.append(system)
            return "ok", {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}

        llm_mock.complete_messages.side_effect = fake_complete
        emb_mock = _make_emb_mock()
        ctx_mock = MagicMock()
        ctx_mock.is_empty.return_value = True

        from lutz.server.app import _run_chat

        with (
            patch("lutz.server.app.load_env", return_value=_make_env()),
            patch("lutz.core.llm_client.LLMClient.from_env", return_value=llm_mock),
            patch("lutz.core.embedding_client.EmbeddingClient.from_env", return_value=emb_mock),
            patch("lutz.server.app.ContextStore", return_value=ctx_mock),
        ):
            _run_chat(
                root=project_root,
                messages=[{"role": "user", "content": "Resumo?"}],
                options={
                    "use_rag": False,
                    "use_model_knowledge": True,
                    "use_context_files": False,
                    "use_library": False,
                    "selected_report_ids": ["large_report"],
                },
                language="pt",
                memories=[],
            )

        system_prompt = captured_system[0]

        # A seção de relatórios deve estar presente
        assert "## Relatórios de Análise" in system_prompt

        # Extrair apenas a seção de relatórios para verificar o tamanho
        start = system_prompt.index("## Relatórios de Análise")
        rest = system_prompt[start:]
        next_section = rest.find("\n##", 2)
        if next_section == -1:
            report_section = rest
        else:
            report_section = rest[:next_section]

        # A seção de relatórios deve ter sido truncada a ≤ 8000 chars + margem
        assert len(report_section) <= 8000 + 200
