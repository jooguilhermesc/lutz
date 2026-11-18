from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from lutz.llm import provedores
from lutz.server.app import criar_app
from tests import fakes, pdfs


@pytest.fixture(autouse=True)
def _limpa():
    fakes.instalar(fakes.Roteiro())
    yield
    provedores.registrar_fake("*", None)


@pytest.fixture
def cliente(projeto):
    return TestClient(criar_app(projeto))


def _esperar(c: TestClient, job_id: str) -> dict:
    for _ in range(200):
        j = c.get(f"/api/v1/jobs/{job_id}").json()
        if j["status"] != "rodando":
            return j
        time.sleep(0.05)
    raise AssertionError("job não terminou")


def _carregar(c, pasta, n=3):
    arquivos = []
    for i in range(n):
        p = pdfs.artigo_simples(pasta, nome=f"a{i}.pdf", autor=f"Ana Autora{i}", titulo=f"Study {i} about tutors",
                                ano=2020 + i)
        arquivos.append(("arquivos", (p.name, p.read_bytes(), "application/pdf")))
    r = c.post("/api/v1/artigos", files=arquivos)
    assert r.status_code == 202
    j = _esperar(c, r.json()["job_id"])
    assert j["status"] == "concluido", j
    return j


def _codebook(c):
    import yaml

    campos = yaml.safe_load(fakes.CODEBOOK)["campos"]
    r = c.put("/api/v1/codebooks/rascunho", json={"campos": campos, "descricao": "teste"})
    assert r.status_code == 200, r.text
    assert c.post("/api/v1/codebooks/congelar", json={}).json()["congelado"]


def test_fluxo_completo_pela_api(cliente, pasta_pdfs):
    c = cliente
    assert c.get("/api/v1/projeto").json()["artigos"]["total"] == 0
    assert c.get("/api/v1/codebooks/atual").json() is None
    j = _carregar(c, pasta_pdfs)
    assert all(x["status"] == "importado" for x in j["resultado"])
    arts = c.get("/api/v1/artigos").json()
    assert len(arts) == 3 and arts[0]["secoes"]
    chave = arts[0]["chave"]
    assert c.get(f"/api/v1/artigos/{chave}").json()["paginas"]
    pg = c.get(f"/api/v1/artigos/{chave}/paginas/2").json()
    assert "212 participants" in pg["texto"] and pg["unidades"]
    assert c.get(f"/api/v1/artigos/{chave}/pdf").headers["content-type"] == "application/pdf"
    assert c.get("/api/v1/artigos/nada").status_code == 404

    # Codebook: lint errors are reported; a valid draft is saved and frozen.
    r = c.post("/api/v1/codebooks/lint", json={"campos": [{"nome": "X", "tipo": "texto", "instrucao": "abc"}]})
    assert r.json()["erros"]
    r = c.put("/api/v1/codebooks/rascunho", json={"campos": [{"nome": "X", "tipo": "texto", "instrucao": "abc"}]})
    assert r.status_code == 422 and "erro" in r.json()
    assert c.get("/api/v1/assistente/modelos").json()
    assert c.post("/api/v1/assistente/modelo", json={"area": "educacao"}).json()["campos"]
    _codebook(c)
    cb = c.get("/api/v1/codebooks/atual").json()
    assert cb["congelado"] and len(cb["campos"]) == 5 and "yaml" in cb

    # Quick test.
    r = c.post("/api/v1/codebooks/teste", json={"campos": ["tamanho_amostra"], "n": 1})
    j = _esperar(c, r.json()["job_id"])
    assert j["status"] == "concluido" and j["resultado"]["resultados"][0]["valor_final"] == "212"

    # Run: estimate, refuse without confirmation, start, follow.
    est = c.post("/api/v1/execucoes/estimativa", json={}).json()
    eid = est["execucao_id"]
    assert est["chamadas"] > 0
    r = c.post(f"/api/v1/execucoes/{eid}/iniciar", json={})
    # confirmar is false in the test settings, so the run starts anyway.
    assert r.status_code == 202
    j = _esperar(c, r.json()["job_id"])
    assert j["status"] == "concluido", j
    d = c.get(f"/api/v1/execucoes/{eid}").json()
    assert d["status"] == "concluida" and len(d["extratores"]) == 4
    assert c.get(f"/api/v1/execucoes/{eid}/metricas").json()["campos"]
    ch = c.get(f"/api/v1/execucoes/{eid}/checagens").json()
    assert ch["celulas"] == 15 and ch["niveis"]["alta"] > 0
    assert c.get(f"/api/v1/execucoes/{eid}/log").json()
    t = c.get(f"/api/v1/execucoes/{eid}/tabela").json()
    assert len(t["linhas"]) == 3 and len(t["campos"]) == 5
    cid = t["linhas"][0]["celulas"]["tamanho_amostra"]["id"]
    cel = c.get(f"/api/v1/celulas/{cid}").json()
    assert len(cel["brutas"]) == 3
    assert c.get(f"/api/v1/execucoes/{eid}/exportar.csv").text.startswith("﻿artigo")

    # Adjudication of a manually sent cell.
    assert c.post(f"/api/v1/celulas/{cid}/enviar", json={"nota": "ver"}).json()["ok"]
    fila = c.get(f"/api/v1/execucoes/{eid}/fila").json()
    assert any(x["id"] == cid for x in fila)
    r = c.post("/api/v1/adjudicacoes", json={"celula_id": cid, "valor": "212", "justificativa": "ok"})
    assert r.json()["origem"] == "adjudicacao"
    assert c.post("/api/v1/adjudicacoes", json={"celula_id": cid, "valor": "abc"}).status_code == 400
    assert c.get(f"/api/v1/execucoes/{eid}/adjudicacao/estatisticas").json()["total"]["decididas"] == 1
    assert c.get(f"/api/v1/execucoes/{eid}/adjudicacao.csv").status_code == 200

    # Audit.
    a = c.get(f"/api/v1/execucoes/{eid}/auditoria").json()
    assert a["auditoria"] is None and a["n_sugerido"] > 0
    c.post(f"/api/v1/execucoes/{eid}/auditoria", json={"n": 2})
    a = c.get(f"/api/v1/execucoes/{eid}/auditoria").json()
    assert len(a["itens"]) == 2
    c.post(f"/api/v1/auditoria/itens/{a['itens'][0]['id']}", json={"correto": True})

    # Report.
    prev = c.get(f"/api/v1/relatorios/{eid}/previa?idioma=en").json()
    assert "Data extraction reliability report" in prev["markdown"]
    r = c.post("/api/v1/relatorios", json={"execucao_id": eid, "idiomas": ["pt"], "formatos": ["md"]})
    j = _esperar(c, r.json()["job_id"])
    assert j["status"] == "concluido", j
    assert c.get("/api/v1/relatorios").json()[0]["execucao_id"] == eid
    assert c.get(f"/api/v1/relatorios/{eid}/arquivos/relatorio_pt.md").status_code == 200
    assert c.get(f"/api/v1/relatorios/{eid}/arquivos/..%2Flutz.db").status_code in (400, 404)

    # Config (the mechanism kept from 0.5), usage and MCP info.
    cfg = c.get("/api/v1/config").json()
    assert cfg["lutz_yaml"]["valido"] and cfg["lutz_yaml"]["papeis"]
    assert c.put("/api/v1/config", json={"OPENAI_API_KEY": "sk-teste-123456"}).json()["ok"]
    assert c.put("/api/v1/config", json={"LLM_MODEL": "x"}).status_code == 422
    cons = c.get("/api/v1/consumo").json()
    assert cons["total"]["chamadas"] > 0 and cons["chamadas"]
    assert c.get("/api/v1/consumo.csv").status_code == 200
    assert c.get("/api/v1/mcp").json()["somente_leitura"]
    info = c.get("/api/v1/projeto").json()
    assert info["codebook"]["congelado"] and info["consumo"]["chamadas"] > 0
    assert c.put("/api/v1/projeto", json={"pergunta": "nova"}).json()["pergunta"] == "nova"
    assert c.get("/api/v1/jobs").json()


def test_piloto_pela_api_e_cegamento(cliente, pasta_pdfs):
    c = cliente
    _carregar(c, pasta_pdfs, n=6)
    _codebook(c)
    assert c.get("/api/v1/piloto").json()["estado"] is None
    p = c.post("/api/v1/piloto/plano", json={"n_ajuste": 0, "n_validacao": 5, "avaliadores": ["A"]}).json()
    assert p["hash_plano"]
    assert c.post("/api/v1/piloto/sorteio").json()["validacao"] == 5
    st = c.get("/api/v1/piloto").json()["estado"]
    assert st["amostra"]["validacao"] == 5
    assert c.get("/api/v1/piloto/planilha/A.csv").status_code == 200
    form = c.get("/api/v1/piloto/formulario/A").json()
    assert len(form["artigos"]) == 5 and form["cobertura"]["esperado"] == 25

    est = c.post("/api/v1/execucoes/estimativa", json={}).json()
    j = _esperar(c, c.post(f"/api/v1/execucoes/{est['execucao_id']}/iniciar", json={}).json()["job_id"])
    assert j["status"] == "concluido"
    t = c.get(f"/api/v1/execucoes/{est['execucao_id']}/tabela").json()
    assert t["ocultos_piloto"] == 25 and len(t["linhas"]) == 1
    oculta = next(a for a in form["artigos"])["chave"]
    assert c.post("/api/v1/relatorios", json={"execucao_id": est["execucao_id"]}).status_code == 202

    # Fill the blind form one answer at a time.
    for art in form["artigos"]:
        for campo in form["campos"]:
            valor = fakes.padrao_silva(campo["nome"])["valor"]
            r = c.post("/api/v1/piloto/respostas", json={"avaliador": "A", "artigo": art["chave"],
                                                          "campo": campo["nome"], "valor": valor, "pagina": 2})
            assert r.status_code == 200, r.text
    assert c.post("/api/v1/piloto/respostas", json={"avaliador": "A", "artigo": oculta, "campo": "desenho_estudo",
                                                     "valor": "nada"}).status_code == 400
    t = c.get(f"/api/v1/execucoes/{est['execucao_id']}/tabela").json()
    assert t["ocultos_piloto"] == 0

    ev = c.post("/api/v1/execucoes/estimativa", json={"conjunto": "validacao"}).json()
    j = _esperar(c, c.post(f"/api/v1/execucoes/{ev['execucao_id']}/iniciar", json={}).json()["job_id"])
    assert j["status"] == "concluido"
    comp = c.post("/api/v1/piloto/comparacao", json={"conjunto": "validacao"}).json()
    assert comp["padrao_ouro"] == "A" and comp["campos"]
    assert c.post("/api/v1/execucoes/estimativa", json={"conjunto": "validacao"}).status_code == 409


def test_spa_ausente_ou_servida(projeto):
    c = TestClient(criar_app(projeto))
    r = c.get("/")
    assert r.status_code == 200
    assert c.get("/api/v1").json()["lutz"]


def test_erros_de_validacao_viram_422(cliente):
    ruim = {"campos": [{"nome": "x", "tipo": "zzz", "instrucao": "a"}]}
    for rota, metodo in (("/api/v1/codebooks/rascunho", "put"), ("/api/v1/codebooks/lint", "post")):
        r = getattr(cliente, metodo)(rota, json=ruim)
        assert r.status_code == 422 and "campo 'x'" in r.json()["erro"]
    r = cliente.post("/api/v1/piloto/plano", json={"n_ajuste": 0, "n_validacao": 5, "avaliadores": ["A"]})
    assert r.status_code == 409  # no codebook yet
