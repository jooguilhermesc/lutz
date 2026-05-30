"""Tests for US-1 — Deduplicação por similaridade (etapa PRISMA).

Cobre:
  - find_duplicate_groups: lógica pura de clustering por distância de cosseno
  - Comando lutz dedup: smoke tests via CliRunner
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedding(dim: int = 8, seed: int | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# find_duplicate_groups — pure function tests
# ---------------------------------------------------------------------------


class TestFindDuplicateGroups:

    def _call(self, embeddings: dict[str, np.ndarray], threshold: float = 0.05):
        from lutz.utils.dedup import find_duplicate_groups
        return find_duplicate_groups(embeddings, threshold=threshold)

    def test_find_duplicate_groups_detects_near_duplicates(self) -> None:
        """Dois embeddings quase idênticos (distância < 0.01) formam um grupo."""
        base = _make_embedding(seed=42)
        # cria cópia com ruído mínimo para garantir distância < 0.01
        tiny_noise = np.zeros_like(base)
        tiny_noise[0] = 1e-5
        near = base + tiny_noise
        near = near / np.linalg.norm(near)

        embeddings = {"artigo_a.pdf": base, "artigo_b.pdf": near}
        groups = self._call(embeddings, threshold=0.05)

        assert len(groups) == 1
        group = groups[0]
        assert "keep" in group
        assert "duplicates" in group
        assert len(group["duplicates"]) == 1
        dup = group["duplicates"][0]
        assert "filename" in dup
        assert "distance" in dup
        assert dup["distance"] < 0.05
        # keep e o duplicata devem ser os dois artigos
        all_files = {group["keep"], dup["filename"]}
        assert all_files == {"artigo_a.pdf", "artigo_b.pdf"}

    def test_find_duplicate_groups_no_duplicates(self) -> None:
        """Embeddings ortogonais retornam lista vazia."""
        # vetores ortogonais têm distância de cosseno = 1.0
        e1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        e2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        e3 = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        embeddings = {"a.pdf": e1, "b.pdf": e2, "c.pdf": e3}
        groups = self._call(embeddings, threshold=0.05)

        assert groups == []

    def test_find_duplicate_groups_threshold_respected(self) -> None:
        """Par com distância 0.06 não aparece com threshold=0.05."""
        base = _make_embedding(seed=10)
        # Cria vetor com distância de cosseno controlada acima do threshold
        # Distância cosseno = 1 - cos_sim. Para dist=0.08: cos_sim = 0.92
        # Usamos perturbação suficiente para ficar acima de 0.05
        perturbed = base.copy()
        perturbed[0] += 0.5
        perturbed = perturbed / np.linalg.norm(perturbed)

        # Calcula distância real para garantir que está acima de 0.05
        cos_sim = float(np.dot(base, perturbed))
        distance = 1.0 - cos_sim
        # Se a distância for menor que 0.05 com essa perturbação, aumenta
        if distance < 0.06:
            perturbed[1] += 0.5
            perturbed = perturbed / np.linalg.norm(perturbed)

        embeddings = {"artigo_a.pdf": base, "artigo_b.pdf": perturbed}
        groups = self._call(embeddings, threshold=0.05)

        # Com threshold 0.05, par com distância maior não deve aparecer
        assert groups == []

    def test_find_duplicate_groups_three_way_cluster(self) -> None:
        """A≈B, B≈C, A≈C formam um único grupo de 3."""
        base = _make_embedding(seed=99)
        # Três variações quase idênticas
        noise1 = np.zeros_like(base)
        noise1[0] = 1e-5
        noise2 = np.zeros_like(base)
        noise2[1] = 1e-5

        a = base / np.linalg.norm(base)
        b = (base + noise1) / np.linalg.norm(base + noise1)
        c = (base + noise2) / np.linalg.norm(base + noise2)

        embeddings = {"a.pdf": a, "b.pdf": b, "c.pdf": c}
        groups = self._call(embeddings, threshold=0.05)

        assert len(groups) == 1
        group = groups[0]
        # Grupo deve conter os 3 artigos: 1 keep + 2 duplicatas
        keep = group["keep"]
        dup_names = {d["filename"] for d in group["duplicates"]}
        all_names = {keep} | dup_names
        assert all_names == {"a.pdf", "b.pdf", "c.pdf"}
        assert len(group["duplicates"]) == 2

    def test_find_duplicate_groups_deterministic(self) -> None:
        """Mesmo input sempre produz mesmo output."""
        base = _make_embedding(seed=7)
        near = base + np.array([1e-5] + [0.0] * (len(base) - 1), dtype=np.float32)
        near = near / np.linalg.norm(near)

        embeddings = {"x.pdf": base, "y.pdf": near}

        result1 = self._call(embeddings, threshold=0.05)
        result2 = self._call(embeddings, threshold=0.05)

        assert result1 == result2

    def test_find_duplicate_groups_single_article(self) -> None:
        """Store com apenas 1 artigo retorna lista vazia."""
        embeddings = {"solo.pdf": _make_embedding(seed=1)}
        groups = self._call(embeddings, threshold=0.05)
        assert groups == []

    def test_find_duplicate_groups_empty(self) -> None:
        """Store vazio retorna lista vazia."""
        groups = self._call({}, threshold=0.05)
        assert groups == []


# ---------------------------------------------------------------------------
# Comando dedup — smoke tests com CliRunner
# ---------------------------------------------------------------------------


class TestDedupCommand:

    def _get_runner_and_cmd(self):
        from lutz.commands.dedup import dedup
        return CliRunner(), dedup

    def _mock_store(self, embeddings: dict[str, np.ndarray]):
        """Retorna um mock de VectorStore com get_embeddings_by_article configurado."""
        store = MagicMock()
        store.get_embeddings_by_article.return_value = embeddings
        return store

    def test_dedup_command_table_output(self, tmp_path) -> None:
        """Smoke test: formato table exibe mensagem de segurança."""
        base = _make_embedding(seed=42)
        tiny_noise = np.zeros_like(base)
        tiny_noise[0] = 1e-5
        near = (base + tiny_noise) / np.linalg.norm(base + tiny_noise)

        embeddings = {"artigo_a.pdf": base, "artigo_b.pdf": near}

        runner, cmd = self._get_runner_and_cmd()
        with (
            patch("lutz.commands.dedup.require_project_root", return_value=tmp_path),
            patch("lutz.commands.dedup.VectorStore") as MockStore,
        ):
            MockStore.return_value = self._mock_store(embeddings)
            result = runner.invoke(cmd, ["--format", "table", "--threshold", "0.05"])

        assert result.exit_code == 0, result.output
        assert "No files were deleted" in result.output

    def test_dedup_command_json_output(self, tmp_path) -> None:
        """Saída JSON deve ser parseable e com formato correto."""
        base = _make_embedding(seed=42)
        tiny_noise = np.zeros_like(base)
        tiny_noise[0] = 1e-5
        near = (base + tiny_noise) / np.linalg.norm(base + tiny_noise)

        embeddings = {"artigo_a.pdf": base, "artigo_b.pdf": near}

        runner, cmd = self._get_runner_and_cmd()
        with (
            patch("lutz.commands.dedup.require_project_root", return_value=tmp_path),
            patch("lutz.commands.dedup.VectorStore") as MockStore,
        ):
            MockStore.return_value = self._mock_store(embeddings)
            result = runner.invoke(cmd, ["--format", "json", "--threshold", "0.05"])

        assert result.exit_code == 0, result.output
        # A saída JSON pode vir antes da mensagem final — extrair a parte JSON
        output = result.output.strip()
        # Encontra o bloco JSON (começa com '[')
        json_start = output.find("[")
        assert json_start != -1, f"Nenhum JSON encontrado em: {output}"
        json_str = output[json_start:]
        # O JSON termina antes de qualquer mensagem de texto depois dele
        # Tenta parsear — se falhar, isola até o último ']'
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            json_end = json_str.rfind("]") + 1
            data = json.loads(json_str[:json_end])

        assert isinstance(data, list)
        assert len(data) == 1
        group = data[0]
        assert "group_id" in group
        assert "keep" in group
        assert "duplicates" in group
        assert isinstance(group["duplicates"], list)
        assert len(group["duplicates"]) == 1
        dup = group["duplicates"][0]
        assert "filename" in dup
        assert "distance" in dup

    def test_dedup_command_empty_store(self, tmp_path) -> None:
        """Store vazio deve emitir mensagem descritiva de erro."""
        runner, cmd = self._get_runner_and_cmd()
        with (
            patch("lutz.commands.dedup.require_project_root", return_value=tmp_path),
            patch("lutz.commands.dedup.VectorStore") as MockStore,
        ):
            MockStore.return_value = self._mock_store({})
            result = runner.invoke(cmd, [])

        # Comando deve terminar com código 0 (não é erro fatal) ou 1 (abort)
        # mas deve exibir mensagem informativa
        assert "empty" in result.output.lower() or "vectorize" in result.output.lower() or \
               "no articles" in result.output.lower(), \
               f"Mensagem esperada não encontrada em: {result.output}"

    def test_dedup_command_no_duplicates_message(self, tmp_path) -> None:
        """Sem duplicatas exibe mensagem de corpus limpo."""
        e1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        e2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        embeddings = {"a.pdf": e1, "b.pdf": e2}

        runner, cmd = self._get_runner_and_cmd()
        with (
            patch("lutz.commands.dedup.require_project_root", return_value=tmp_path),
            patch("lutz.commands.dedup.VectorStore") as MockStore,
        ):
            MockStore.return_value = self._mock_store(embeddings)
            result = runner.invoke(cmd, ["--threshold", "0.05"])

        assert result.exit_code == 0, result.output
        assert "No near-duplicates found" in result.output or "threshold" in result.output

    def test_dedup_command_output_file(self, tmp_path) -> None:
        """Com --output PATH salva resultado em arquivo."""
        base = _make_embedding(seed=42)
        tiny_noise = np.zeros_like(base)
        tiny_noise[0] = 1e-5
        near = (base + tiny_noise) / np.linalg.norm(base + tiny_noise)

        embeddings = {"artigo_a.pdf": base, "artigo_b.pdf": near}
        out_file = tmp_path / "dedup_report.json"

        runner, cmd = self._get_runner_and_cmd()
        with (
            patch("lutz.commands.dedup.require_project_root", return_value=tmp_path),
            patch("lutz.commands.dedup.VectorStore") as MockStore,
        ):
            MockStore.return_value = self._mock_store(embeddings)
            result = runner.invoke(
                cmd,
                ["--format", "json", "--output", str(out_file), "--threshold", "0.05"],
            )

        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert isinstance(data, list)
