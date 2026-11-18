from __future__ import annotations

import json

import pymupdf
import pytest

from lutz.config.settings import carregar_settings
from lutz.core.errors import EstadoInvalido
from lutz.extraction import executor as ex
from lutz.llm import provedores
from lutz.report import render
from lutz.report.gerar import gerar
from lutz.revisao import auditoria as aud
from tests import fakes
from tests.test_revisao_piloto import _corpus


@pytest.fixture(autouse=True)
def _limpa():
    yield
    provedores.registrar_fake("*", None)


def test_relatorio_sem_piloto(projeto, con, pasta_pdfs):
    _corpus(projeto, con, pasta_pdfs, n=3)
    fakes.instalar(fakes.Roteiro())
    s = carregar_settings(projeto)
    eid = ex.planejar(projeto, con, s)
    t = ex.planejar(projeto, con, s, tipo="teste", campos=["tamanho_amostra"], artigos=["sobrenome02015"])
    ex.executar(projeto, t)
    with pytest.raises(EstadoInvalido):
        gerar(projeto, con, t)
    with pytest.raises(EstadoInvalido, match="concluída"):
        gerar(projeto, con, eid)
    ex.executar(projeto, eid)
    r = gerar(projeto, con, eid)
    pasta = projeto.relatorios / "execucao-0001"
    for nome in ("relatorio_pt.md", "relatorio_en.md", "relatorio_pt.pdf", "relatorio_en.pdf",
                 "anexo_B_tabela_longa.csv", "anexo_B_tabela_larga.csv", "anexo_C_chamadas.csv",
                 "anexo_A_codebook_v1.yaml", "execucao.json", "metricas.csv", "manifest.json"):
        assert (pasta / nome).exists(), nome
    md = (pasta / "relatorio_pt.md").read_text(encoding="utf-8")
    for k in range(1, 8):
        assert f"## {k}. " in md
    assert "não comprova que os valores estejam corretos" in md
    assert "auditoria das células Alta não foi feita" in md
    assert "sem piloto" in md
    en = (pasta / "relatorio_en.md").read_text(encoding="utf-8")
    assert "does not demonstrate that the values are correct" in en
    import unicodedata

    texto_pdf = unicodedata.normalize("NFKC", pymupdf.open(pasta / "relatorio_pt.pdf")[0].get_text())
    assert "Relatório de confiabilidade" in texto_pdf
    man = json.loads((pasta / "manifest.json").read_text())
    assert set(r["manifesto"]) == set(man)
    assert con.execute("SELECT count(*) FROM relatorio").fetchone()[0] == 4

    a = aud.criar(con, eid, s)
    for it in aud.itens(con, a["id"]):
        aud.registrar(con, it["id"], True)
    gerar(projeto, con, eid, idiomas=["pt"], formatos=["md"])
    md = (pasta / "relatorio_pt.md").read_text(encoding="utf-8")
    assert "auditoria das células Alta não foi feita" not in md
    assert "conferidas manualmente" in md or "conferida manualmente" in md


def test_md_para_html():
    h = render.md_para_html("# T\n\ntexto **forte** e `cod`\n\n| a | b \\| c |\n|---|---|\n| 1 | 2 |\n\n- x\n- y\n\n> nota")
    assert "<h1>T</h1>" in h and "<b>forte</b>" in h and "<td>1</td>" in h and "b | c" in h
    assert "<ul><li>x</li>" in h and "<blockquote>nota</blockquote>" in h
