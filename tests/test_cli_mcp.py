from __future__ import annotations

import asyncio
import csv
import zipfile

import pytest
from click.testing import CliRunner

from lutz.cli import cli
from lutz.llm import provedores
from lutz.server.mcp import Ferramentas, servidor
from tests import fakes, pdfs
from tests.conftest import YAML_FAKE


@pytest.fixture(autouse=True)
def _limpa():
    fakes.instalar(fakes.Roteiro())
    yield
    provedores.registrar_fake("*", None)


def _run(args, ok=True):
    r = CliRunner().invoke(cli, args, catch_exceptions=False)
    if ok:
        assert r.exit_code == 0, r.output
    return r


def test_fluxo_cli_completo(tmp_path, pasta_pdfs):
    raiz = tmp_path / "rev"
    _run(["init", str(raiz), "--pergunta", "LLM tutores?"])
    (raiz / "lutz.yaml").write_text(YAML_FAKE, encoding="utf-8")
    p = ["--projeto", str(raiz)]
    for i in range(4):
        pdfs.artigo_simples(pasta_pdfs, nome=f"a{i}.pdf", autor=f"Bia Souza{i}", titulo=f"Tutors {i}", ano=2019 + i)
    pdfs.artigo_escaneado(pasta_pdfs)
    r = _run(["load", str(pasta_pdfs), *p])
    assert "4 importado" in r.output and "sem_texto" in r.output
    assert "souza02019" in _run(["library", *p]).output
    cb = tmp_path / "cb.yaml"
    cb.write_text(fakes.CODEBOOK, encoding="utf-8")
    _run(["codebook", "check", str(cb)])
    _run(["codebook", "import", str(cb), *p])
    r = _run(["codebook", "test", "--campo", "tamanho_amostra", "--n", "1", *p])
    assert "212" in r.output
    _run(["codebook", "freeze", *p])
    assert "congelado" in _run(["codebook", "show", *p]).output
    _run(["codebook", "history", *p])
    _run(["codebook", "export", "-o", str(tmp_path / "out.yaml"), *p])
    assert (tmp_path / "out.yaml").exists()

    r = _run(["extract", "--estimar", *p])
    assert "Estimativa" in r.output and "planejada" in r.output
    r = _run(["extract", "--retomar", "2", "--sim", *p])
    assert "concluida" in r.output and "Confiabilidade por campo" in r.output
    _run(["extract", "list", *p])
    _run(["extract", "status", "2", *p])
    _run(["extract", "recompute", "2", *p])
    r = _run(["results", "--formato", "longo", *p])
    assert "linhas" in r.output

    _run(["adjudicate", "queue", *p])
    r = _run(["adjudicate", "export", *p])
    alta = _run(["results", *p])  # noqa: F841
    r = _run(["audit", "sample", "--n", "2", *p])
    arq = raiz / "exports" / "auditoria_0002.csv"
    linhas = list(csv.DictReader(open(arq, encoding="utf-8-sig")))
    for linha in linhas:
        linha["correto"] = "sim"
    with open(arq, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    _run(["audit", "import", str(arq), *p])
    assert "2/2 conferidas" in _run(["audit", "status", *p]).output

    r = _run(["report", "--idioma", "pt", "--formato", "md", *p])
    assert "relatorio_pt.md" in r.output
    r = _run(["usage", *p])
    assert "Total" in r.output
    r = _run(["config", "show", *p])
    assert "diversidade" in r.output
    _run(["config", "set", "OPENROUTER_API_KEY", "sk-1234567890", *p])
    _run(["config", "unset", "OPENROUTER_API_KEY", *p])
    assert _run(["config", "set", "LLM_MODEL", "x", *p], ok=False).exit_code != 0
    r = _run(["doctor", *p])
    assert "lutz.yaml" in r.output
    _run(["status", *p])
    _run(["bundle", "export", "-o", str(tmp_path / "b.zip"), *p])
    nomes = zipfile.ZipFile(tmp_path / "b.zip").namelist()
    assert "lutz.db" in nomes and "manifest.json" in nomes and ".env" not in nomes
    assert not any(n.startswith("pdfs/") for n in nomes)

    # Pilot through the CLI.
    _run(["pilot", "plan", "--n", "5", "--ajuste", "0", "--avaliadores", "A", *p])
    r = CliRunner().invoke(cli, ["pilot", "sample", *p])
    assert r.exit_code != 0 and "elegíveis" in r.output  # 4 ready, 1 used in the quick test: 3 eligible < 5
    _run(["pilot", "status", *p])


def test_cli_erros_claros(tmp_path):
    r = CliRunner().invoke(cli, ["status", "--projeto", str(tmp_path)])
    assert r.exit_code != 0 and "Nenhum projeto" in r.output
    r = CliRunner().invoke(cli, ["web", "--host", "0.0.0.0", "--projeto", str(tmp_path)])
    assert r.exit_code != 0
    assert "Fluxo" in _run(["--help"]).output
    assert "1.0" in _run(["--version"]).output


def test_mcp_ferramentas_somente_leitura(projeto, con, pasta_pdfs):
    from lutz.config.settings import carregar_settings
    from lutz.core import codebook as cbk
    from lutz.core.ingestao import importar_pdf
    from lutz.extraction import executor as ex

    importar_pdf(projeto, con, pdfs.artigo_simples(pasta_pdfs))
    f = Ferramentas(projeto)
    assert f.consultar_celulas()["celulas"] == []
    assert "erro" in f.metricas_execucao()
    cbk.salvar_rascunho(con, cbk.ler_yaml(fakes.CODEBOOK))
    cbk.congelar(con)
    eid = ex.planejar(projeto, con, carregar_settings(projeto))
    ex.executar(projeto, eid)
    assert f.listar_projeto()["codebook"]["congelado"]
    assert len(f.ler_codebook()["campos"]) == 5
    cel = f.consultar_celulas(campo="tamanho_amostra", nivel="alta")
    assert cel["celulas"][0]["valor"] == "212"
    assert len(f.detalhe_celula(cel["celulas"][0]["id"])["brutas"]) == 3
    assert "erro" in f.detalhe_celula(99999)
    assert f.metricas_execucao()["por_campo"]
    b = f.buscar_trechos("participants completed protocol")
    assert b["resultados"][0]["pagina"] == 2
    rel = f.ler_relatorio()
    assert "Relatório de confiabilidade" in rel["markdown"]

    s = servidor(projeto)
    nomes = {t.name for t in asyncio.run(s.list_tools())}
    assert nomes == {"listar_projeto", "ler_codebook", "consultar_celulas", "detalhe_celula", "metricas_execucao",
                     "buscar_trechos", "ler_relatorio"}
    r = asyncio.run(s.call_tool("consultar_celulas", {"campo": "tamanho_amostra"}))
    assert not r.is_error
