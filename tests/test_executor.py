from __future__ import annotations

import pytest

from lutz.config.settings import carregar_settings, validar_yaml
from lutz.core import codebook as cbk
from lutz.core.errors import EstadoInvalido
from lutz.core.ingestao import importar_pdf
from lutz.extraction import executor as ex
from lutz.extraction.metricas_autonomo import metricas
from lutz.llm import provedores
from tests import fakes, pdfs
from tests.conftest import YAML_FAKE


@pytest.fixture(autouse=True)
def _limpa_fakes():
    yield
    provedores.registrar_fake("*", None)


@pytest.fixture
def preparado(projeto, con, pasta_pdfs):
    importar_pdf(projeto, con, pdfs.artigo_simples(pasta_pdfs))
    importar_pdf(projeto, con, pdfs.artigo_simples(
        pasta_pdfs, nome="costa2022.pdf", autor="Bia Costa", titulo="Chatbots in classrooms", ano=2022))
    cbk.salvar_rascunho(con, cbk.ler_yaml(fakes.CODEBOOK))
    cbk.congelar(con)
    return projeto


def _celula(con, eid, chave, campo):
    return dict(con.execute(
        """SELECT c.* FROM celula c JOIN artigo a ON a.id=c.artigo_id
           WHERE c.execucao_id=? AND a.chave=? AND c.campo_chave=?""", (eid, chave, campo)).fetchone())


def _settings(projeto, **kw):
    s = carregar_settings(projeto)
    return s.model_copy(update=kw) if kw else s


def test_exige_codebook_congelado(projeto, con, pasta_pdfs):
    importar_pdf(projeto, con, pdfs.artigo_simples(pasta_pdfs))
    with pytest.raises(EstadoInvalido, match="congelado"):
        ex.planejar(projeto, con, carregar_settings(projeto))


def test_execucao_completa_niveis_regras_e_metricas(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    # costa2022: E3 invents a number not present in its quote -> e=0 for E3, 2 of 3 agree.
    r.definir("fake-c", "costa2022", "tamanho_amostra", valor="250", trecho=fakes.T_AMOSTRA, pagina=2)
    # costa2022: three different designs -> tie.
    r.definir("fake-b", "costa2022", "desenho_estudo", valor="observacional", trecho=fakes.T_DESENHO, pagina=2)
    r.definir("fake-c", "costa2022", "desenho_estudo", valor="revisao", trecho=fakes.T_DESENHO, pagina=2)
    # costa2022: all say n_controle = 100 (quote supports 106? no) -> sum rule fails.
    for m in ("fake-a", "fake-b", "fake-c"):
        r.definir(m, "costa2022", "n_controle", valor="100", trecho="the control group (n = 100)", pagina=2)
    # silva2021: limitations not reported by all.
    for m in ("fake-a", "fake-b", "fake-c"):
        r.definir(m, "silva2021", "limitacoes", nr=True)
    fakes.instalar(r)
    s = carregar_settings(projeto)
    eid = ex.planejar(projeto, con, s)
    est = ex.estimar(projeto, con, eid)
    assert est["chamadas"] > 0 and est["custo_usd"] is not None and est["cabe_no_orcamento"]
    eventos = []
    res = ex.executar(projeto, eid, progresso=eventos.append)
    assert res["status"] == "concluida", res
    assert res["celulas_prontas"] == res["celulas"] == 10
    assert any(e["tipo"] == "fim" for e in eventos)

    c = _celula(con, eid, "silva2021", "tamanho_amostra")
    assert c["nivel"] == "alta" and c["valor_final"] == "212" and c["a"] == 1 and c["e"] == 1
    assert c["trecho"] and c["pagina"] == 2

    c = _celula(con, eid, "costa2022", "tamanho_amostra")
    # 212/212/250: majority 212; sum rule 106 + 100 != 212 fails -> baixa.
    assert c["valor_final"] == "212" and c["nivel"] == "baixa"
    assert any("soma" in m for m in __import__("json").loads(c["motivos"]))

    c = _celula(con, eid, "costa2022", "desenho_estudo")
    assert c["valor_final"] is None and c["nivel"] == "baixa" and c["escore"] is None

    c = _celula(con, eid, "silva2021", "limitacoes")
    assert c["nao_reportado"] == 1 and c["nivel"] == "media"

    c = _celula(con, eid, "costa2022", "n_controle")
    # "n = 100" is not in the text -> e = 0 for everyone.
    assert c["e"] == 0 and c["nivel"] == "baixa"

    m = metricas(con, eid)
    assert "alfa" in m["desenho_estudo"] and "unanimes" in m["limitacoes"]
    assert m[None]["pct_alta"]["valor"] > 0
    # Verifier was called for non-tie cells.
    assert any(x[1].startswith("V:") for x in r.chamadas)


def test_cache_nova_execucao_nao_paga_de_novo(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    fakes.instalar(r)
    s = carregar_settings(projeto)
    e1 = ex.planejar(projeto, con, s)
    ex.executar(projeto, e1)
    n_chamadas = len(r.chamadas)
    e2 = ex.planejar(projeto, con, s)
    est = ex.estimar(projeto, con, e2)
    assert est["chamadas"] == 0 + (est["por_papel"][-1]["chamadas"] if est["por_papel"] and
                                   est["por_papel"][-1]["rotulo"] == "V" else 0)
    assert est["em_cache"] > 0
    res = ex.executar(projeto, e2)
    assert res["status"] == "concluida"
    assert len(r.chamadas) == n_chamadas  # everything served from cache
    assert res["custo_usd"] == 0 and res["chamadas_cache"] == res["chamadas"]


def test_resposta_malformada_tenta_de_novo(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    r.malformar.add(("fake-a", "silva2021"))
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto), artigos=["silva2021"])
    res = ex.executar(projeto, eid)
    assert res["status"] == "concluida"
    st = [x[0] for x in con.execute("SELECT status FROM chamada_llm WHERE execucao_id=? AND rotulo='E1'", (eid,))]
    assert "malformada" in st and "ok" in st
    assert _celula(con, eid, "silva2021", "tamanho_amostra")["nivel"] == "alta"


def test_orcamento_pausa_e_retomada_sem_repetir(preparado, con):
    projeto = preparado
    yaml_caro = YAML_FAKE.replace("orcamento_usd: 10", "orcamento_usd: 0.001")
    projeto.yaml.write_text(yaml_caro, encoding="utf-8")
    r = fakes.Roteiro()
    fakes.instalar(r)
    s = carregar_settings(projeto)
    eid = ex.planejar(projeto, con, s)
    res = ex.executar(projeto, eid, max_threads=1)
    assert res["status"] == "pausada" and "Orçamento" in res["motivo"]
    feitas = len(r.chamadas)
    assert feitas >= 1
    # Raise the budget in the stored config of the run and resume.
    import json

    cfg = json.loads(con.execute("SELECT config FROM execucao WHERE id=?", (eid,)).fetchone()[0])
    cfg["custo"]["orcamento_usd"] = 100
    con.execute("UPDATE execucao SET config=? WHERE id=?", (json.dumps(cfg), eid))
    res = ex.executar(projeto, eid)
    assert res["status"] == "concluida"
    # 2 articles x 3 extractors x 2 groups (Methods / no section), each requested exactly once.
    hashes = [x[0] for x in con.execute(
        "SELECT hash_requisicao FROM chamada_llm WHERE papel='extrator' AND cache=0")]
    assert len(hashes) == len(set(hashes)) == 12


def test_pausa_pela_pesquisadora(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto))
    ex.pausar(con, eid)
    res = ex.executar(projeto, eid)
    # executar sets 'rodando' first, so a pause before start does not block the run.
    assert res["status"] == "concluida"
    import threading

    eid2 = ex.planejar(projeto, con, carregar_settings(projeto))
    parar = threading.Event()
    parar.set()
    res = ex.executar(projeto, eid2, parar=parar)
    assert res["status"] == "pausada"
    assert ex.reparar_interrompidas(con) == []


def test_recalcular_com_limiares_atuais(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    r.definir("fake-b", "silva2021", "desenho_estudo", valor="experimental",
              trecho="This invented sentence does not exist anywhere in the article", pagina=2)
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto), artigos=["silva2021"])
    ex.executar(projeto, eid)
    c = _celula(con, eid, "silva2021", "desenho_estudo")
    assert c["nivel"] == "media"  # E2 invented its quote (e=0) inside the agreeing group
    novo = validar_yaml(YAML_FAKE + "limiares: {alta_exige_evidencia_no_grupo: false}\n")
    ex.recalcular(projeto, eid, usar_limiares_atuais=novo)
    c = _celula(con, eid, "silva2021", "desenho_estudo")
    assert c["nivel"] == "alta"


def test_teste_rapido_so_e1(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto), tipo="teste", campos=["tamanho_amostra"],
                      artigos=["silva2021"])
    res = ex.executar(projeto, eid)
    assert res["status"] == "concluida" and res["celulas_prontas"] == 1
    c = _celula(con, eid, "silva2021", "tamanho_amostra")
    assert c["valor_final"] == "212" and c["e"] == 1 and c["nivel"] is None
    assert {x[0] for x in r.chamadas} == {"fake-a"}
    assert con.execute("SELECT count(*) FROM teste_rapido").fetchone()[0] == 1


def test_verificador_ausencia(preparado, con):
    projeto = preparado
    r = fakes.Roteiro()
    for m in ("fake-a", "fake-b", "fake-c"):
        r.definir(m, "silva2021", "desenho_estudo", nr=True)
    r.ausencia["desenho_estudo"] = "presente"
    fakes.instalar(r)
    eid = ex.planejar(projeto, con, carregar_settings(projeto), artigos=["silva2021"])
    ex.executar(projeto, eid)
    c = _celula(con, eid, "silva2021", "desenho_estudo")
    assert c["nao_reportado"] == 1 and c["nivel"] == "baixa" and c["v"] == 0


def test_parse_extracao_tolerante():
    from lutz.core.codebook import Campo

    campos = [Campo(nome="x", tipo="numerico", instrucao="numero de participantes"),
              Campo(nome="y", tipo="texto", instrucao="limitacao principal do estudo")]
    out = ex.parse_extracao('```json\n{"campos":[{"nome":"x","valor":212,"pagina":"p. 4",'
                            '"unidades":"[p4.s2]","nao_reportado":"false","trecho":"t"},'
                            '{"nome":"y","valor":"not reported"}]}\n```', campos)
    assert out["x"]["valor"] == "212" and out["x"]["pagina"] == 4 and out["x"]["unidades"] == ["p4.s2"]
    assert out["y"]["nao_reportado"] is True
    with pytest.raises(ValueError):
        ex.parse_extracao('{"outra": 1}', campos)
    with pytest.raises(ValueError):
        ex.parse_extracao("sem json", campos)
