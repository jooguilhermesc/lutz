from __future__ import annotations

import csv
import math

import pytest

from lutz.calibrated import piloto as pil
from lutz.config.settings import carregar_settings
from lutz.core import codebook as cbk
from lutz.core.errors import EstadoInvalido, LutzError
from lutz.core.ingestao import importar_pdf
from lutz.extraction import executor as ex
from lutz.llm import provedores
from lutz.revisao import adjudicacao as adj
from lutz.revisao import auditoria as aud
from tests import fakes, pdfs


@pytest.fixture(autouse=True)
def _limpa():
    yield
    provedores.registrar_fake("*", None)


def _corpus(projeto, con, pasta, n=8):
    for i in range(n):
        importar_pdf(projeto, con, pdfs.artigo_simples(
            pasta, nome=f"a{i}.pdf", autor=f"Autor{i} Sobrenome{i}", titulo=f"Study number {i} on tutors",
            ano=2015 + i % 3, metodos=fakes.T_DESENHO + " " + fakes.T_AMOSTRA + " " + fakes.T_GRUPOS))
    cbk.salvar_rascunho(con, cbk.ler_yaml(fakes.CODEBOOK))
    cbk.congelar(con)


@pytest.fixture
def executado(projeto, con, pasta_pdfs):
    _corpus(projeto, con, pasta_pdfs, n=3)
    r = fakes.Roteiro()
    r.definir("fake-b", "sobrenome02015", "desenho_estudo", valor="observacional", trecho=fakes.T_DESENHO, pagina=2)
    r.definir("fake-c", "sobrenome02015", "desenho_estudo", valor="revisao", trecho=fakes.T_DESENHO, pagina=2)
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto))
    ex.executar(projeto, eid)
    return eid


def test_fila_decisao_e_csv(projeto, con, executado, tmp_path):
    eid = executado
    f = adj.fila(con, eid)
    assert f and all(c["nivel"] == "baixa" for c in f)
    assert f[0]["escore"] is None  # tie first
    alvo = f[0]
    with pytest.raises(LutzError):
        adj.decidir(con, alvo["id"], valor="quase-experimental", nao_reportado=False)
    cel = adj.decidir(con, alvo["id"], valor="Experimental", nao_reportado=False, justificativa="ver p. 2")
    assert cel["valor_final"] == "experimental" and cel["origem"] == "adjudicacao"
    assert alvo["id"] not in [c["id"] for c in adj.fila(con, eid)]
    est = adj.estatisticas(con, eid)
    assert est["total"]["decididas"] == 1 and est["total"]["alteradas"] == 1
    d = adj.detalhe_celula(con, alvo["id"])
    assert len(d["brutas"]) == 3 and d["adjudicacoes"][0]["valor_anterior"] is None

    # Manual send of an Alta cell and CSV round trip.
    alta = con.execute("SELECT id FROM celula WHERE execucao_id=? AND nivel='alta' LIMIT 1", (eid,)).fetchone()[0]
    adj.enviar_manual(con, alta, "conferir")
    destino = tmp_path / "adj.csv"
    n = adj.exportar_csv(con, eid, destino, sep=";")
    assert n == len(adj.fila(con, eid))
    linhas = list(csv.DictReader(open(destino, encoding="utf-8-sig"), delimiter=";"))
    for linha in linhas:
        linha["valor_decidido"] = "=" if linha["celula_id"] == str(alta) else ""
        linha["justificativa"] = "ok"
    linhas.append({**linhas[0], "celula_id": "999999", "valor_decidido": "x"})
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=adj.COLUNAS, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    rel = adj.importar_csv(con, destino)
    assert rel["aplicadas"] == 1 and len(rel["erros"]) == 1
    assert con.execute("SELECT alterou FROM adjudicacao WHERE celula_id=?", (alta,)).fetchone()[0] == 0


def test_auditoria(projeto, con, executado, tmp_path):
    eid = executado
    s = carregar_settings(projeto)
    a = aud.criar(con, eid, s)
    n_alta = con.execute("SELECT count(*) FROM celula WHERE execucao_id=? AND nivel='alta'", (eid,)).fetchone()[0]
    assert a["n_amostra"] == min(n_alta, 57) or a["n_amostra"] <= n_alta
    assert aud.criar(con, eid, s)["id"] == a["id"]  # idempotent
    itens = aud.itens(con, a["id"])
    aud.registrar(con, itens[0]["id"], True)
    with pytest.raises(LutzError):
        aud.registrar(con, itens[1]["id"], False)
    aud.registrar(con, itens[1]["id"], False, nao_reportado_correto=True, nota="não está no texto")
    res = aud.resultado(con, eid)
    assert res["conferidas"] == 2 and res["acertos"] == 1 and not math.isnan(res["ic_inf"])
    cel = con.execute("SELECT origem, nao_reportado FROM celula WHERE id=?", (itens[1]["celula_id"],)).fetchone()
    assert cel[0] == "adjudicacao" and cel[1] == 1
    destino = tmp_path / "aud.csv"
    assert aud.exportar_csv(con, a["id"], destino) == len(itens)
    linhas = list(csv.DictReader(open(destino, encoding="utf-8-sig")))
    for linha in linhas:
        if not linha["correto"]:
            linha["correto"] = "sim"
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=aud.COLUNAS)
        w.writeheader()
        w.writerows(linhas)
    rel = aud.importar_csv(con, destino)
    assert not rel["erros"]
    assert aud.resultado(con, eid)["completa"]


def _preencher(destino, valores_por_artigo, campos):
    linhas = list(csv.DictReader(open(destino, encoding="utf-8-sig")))
    for linha in linhas:
        vals = valores_por_artigo(linha["artigo"])
        for c in campos:
            v = vals.get(c)
            if v is None:
                linha[f"{c}__nao_reportado"] = "sim"
            else:
                linha[c] = v
            linha[f"{c}__pagina"] = "2"
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)


CAMPOS = ["desenho_estudo", "tamanho_amostra", "n_intervencao", "n_controle", "limitacoes"]


def _humano(chave):
    return {"desenho_estudo": "experimental", "tamanho_amostra": "212", "n_intervencao": "106",
            "n_controle": "106", "limitacoes": "Short follow-up of eight weeks"}


def test_piloto_completo(projeto, con, pasta_pdfs, tmp_path):
    _corpus(projeto, con, pasta_pdfs, n=12)
    s = carregar_settings(projeto)
    # A quick test excludes its article from the draw.
    r = fakes.Roteiro()
    fakes.instalar(r)
    t = ex.planejar(projeto, con, s, tipo="teste", campos=["tamanho_amostra"], artigos=["sobrenome02015"])
    ex.executar(projeto, t)

    p = pil.planejar(con, s, n_ajuste=3, n_validacao=6, n_reserva=2, estratos="ano")
    assert p["hash_plano"] and pil.avisos_plano(12, 6)
    res = pil.sortear(con, p["id"])
    assert res["excluidos_teste_rapido"] == 1
    sorteados = {a["chave"] for a in pil.amostra(con, p["id"], ("ajuste", "validacao", "reserva"))}
    assert len(sorteados) == 11 and "sobrenome02015" not in sorteados
    with pytest.raises(EstadoInvalido):
        pil.sortear(con, p["id"])
    # Same seed, same draw: reproducible.
    ocultos = pil.artigos_ocultos(con)
    assert len(ocultos) == 9

    for av in ("A", "B"):
        pil.exportar_planilha(con, p["id"], av, tmp_path / f"humano_{av}.csv")
        assert (tmp_path / f"guia_humano_{av}.md").exists()
    with pytest.raises(EstadoInvalido):
        pil.comparar(con, p["id"], "validacao", s)

    # Rater A: everything as the default answer. Rater B: disagrees on one design.
    _preencher(tmp_path / "humano_A.csv", _humano, CAMPOS)
    alvo_div = sorted(sorteados - {a["chave"] for a in pil.amostra(con, p["id"], ("reserva",))})[0]

    def humano_b(chave):
        d = _humano(chave)
        if chave == alvo_div:
            d["desenho_estudo"] = "observacional"
        return d

    _preencher(tmp_path / "humano_B.csv", humano_b, CAMPOS)
    ruim = tmp_path / "ruim.csv"
    ruim.write_text("artigo,desenho_estudo\nxyz,experimental\n", encoding="utf-8")
    assert pil.importar_planilha(con, p["id"], "A", ruim)["erros"]
    assert pil.importar_planilha(con, p["id"], "A", tmp_path / "humano_A.csv")["gravadas"] == 45
    assert pil.artigos_ocultos(con)  # B still missing: still blind
    assert pil.importar_planilha(con, p["id"], "B", tmp_path / "humano_B.csv")["gravadas"] == 45
    assert not pil.artigos_ocultos(con)

    with pytest.raises(EstadoInvalido, match="consenso"):
        ex_aj = ex.planejar(projeto, con, s, piloto_id=p["id"], conjunto="ajuste")
        ex.executar(projeto, ex_aj)
        pil.comparar(con, p["id"], "ajuste", s)
    div = pil.exportar_consenso(con, p["id"], tmp_path / "consenso.csv", s)
    assert div["divergentes"] == 1
    linhas = list(csv.DictReader(open(tmp_path / "consenso.csv", encoding="utf-8-sig")))
    linhas[0]["consenso_valor"] = "experimental"
    with open(tmp_path / "consenso.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    assert pil.importar_consenso(con, p["id"], tmp_path / "consenso.csv", s)["gravadas"] == 45

    aj = pil.comparar(con, p["id"], "ajuste", s)
    assert aj["padrao_ouro"] == "consenso" and all(c["decisao"] is None for c in aj["campos"])

    ev = ex.planejar(projeto, con, s, piloto_id=p["id"], conjunto="validacao")
    ex.executar(projeto, ev)
    with pytest.raises(EstadoInvalido, match="única vez"):
        ex.planejar(projeto, con, s, piloto_id=p["id"], conjunto="validacao")
    val = pil.comparar(con, p["id"], "validacao", s)
    campos = {c["campo"]: c for c in val["campos"]}
    assert campos["tamanho_amostra"]["lutz_ouro"]["metrica"] == "icc"
    assert campos["desenho_estudo"]["lutz_ouro"]["pct_concordancia"] == 1
    assert campos["limitacoes"]["lutz_ouro"]["metrica"] == "pct_equivalencia"
    assert campos["desenho_estudo"]["humano_humano"] is not None
    alta = val["niveis"][0]
    assert alta["n"] > 0 and alta["taxa"] == 1
    decs = {d["campo_chave"]: d for d in pil.estado(con)["decisoes"]}
    assert set(decs) == set(CAMPOS)
    st = pil.estado(con)
    assert st["consenso"] and st["amostra"]["validacao"] == 6 and len(st["rodadas"]) == 2


def test_decidir_campo_regra_exaustiva():
    from lutz.config.settings import Limiares

    lim = Limiares()
    c = cbk.Campo(nome="x", tipo="categorico", valores=["a", "b"], instrucao="classifique o estudo")
    assert pil.decidir_campo(c, {"valor": 0.85, "ic": (0.65, 0.95)}, lim)[0] == "lutz_sozinho"
    assert pil.decidir_campo(c, {"valor": 0.85, "ic": (0.5, 0.95)}, lim)[0] == "revisar_media_baixa"
    assert pil.decidir_campo(c, {"valor": 0.70, "ic": (0.5, 0.9)}, lim)[0] == "revisar_media_baixa"
    assert pil.decidir_campo(c, {"valor": 0.5, "ic": (0.3, 0.7)}, lim)[0] == "reescrever"
    assert pil.decidir_campo(c, {"valor": math.nan, "ic": (math.nan, math.nan)}, lim)[0] == "indefinida"
    n = cbk.Campo(nome="n", tipo="numerico", instrucao="numero total de participantes")
    assert pil.decidir_campo(n, {"valor": 0.99, "ic": (0.97, 1), "pct_exato": 0.8}, lim)[0] == "revisar_media_baixa"
    t = cbk.Campo(nome="t", tipo="texto", instrucao="limitacao principal do estudo")
    assert pil.decidir_campo(t, {"valor": 0.95, "ic": (0.8, 0.99)}, lim)[0] == "lutz_sozinho"
    assert pil.decidir_campo(t, {"valor": 0.5, "ic": (0.3, 0.7)}, lim)[0] == "reescrever"


def test_hamilton():
    assert pil._hamilton({"a": 10, "b": 5, "c": 5}, 4) == {"a": 2, "b": 1, "c": 1}
    assert sum(pil._hamilton({"a": 3, "b": 3, "c": 1}, 5).values()) == 5


def test_relatorio_com_piloto(projeto, con, pasta_pdfs, tmp_path):
    from lutz.report.gerar import gerar

    test_piloto_completo(projeto, con, pasta_pdfs, tmp_path)
    val = pil.execucao_do_conjunto(con, pil.atual(con)["id"], "validacao")
    gerar(projeto, con, val["id"], idiomas=["pt", "en"], formatos=["md"])
    md = (projeto.relatorios / f"execucao-{val['id']:04d}" / "relatorio_pt.md").read_text(encoding="utf-8")
    assert "Modo Calibrado" in md and "Plano pré-registrado" in md
    assert "concordaram com o padrão-ouro" in md
    assert "κ" in md and "ICC" in md
