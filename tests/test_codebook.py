from __future__ import annotations

import pytest

from lutz.core import codebook as cbk
from lutz.core.errors import CodebookInvalido, EstadoInvalido
from lutz.extraction import regras

YAML = """
descricao: Teste
campos:
  - nome: desenho_estudo
    tipo: categorico
    valores: [experimental, observacional, revisao, outro]
    instrucao: Classifique o desenho principal do estudo.
    secoes: [metodos]
  - nome: tamanho_amostra
    tipo: numerico
    unidade: participantes
    faixa: [1, 100000]
    instrucao: Número total de participantes que completaram o estudo.
    regras:
      - {tipo: soma_igual, campos: [n_intervencao, n_controle]}
  - nome: n_intervencao
    tipo: numerico
    unidade: participantes
    faixa: [0, 100000]
    instrucao: Participantes no grupo de intervenção.
  - nome: n_controle
    tipo: numerico
    unidade: participantes
    faixa: [0, 100000]
    instrucao: Participantes no grupo controle.
  - nome: risco_vies
    tipo: ordinal
    valores: [baixo, moderado, alto]
    instrucao: Julgue o risco de viés com base no método de alocação.
    papel: risco_vies
  - nome: limitacoes
    tipo: texto
    instrucao: Principal limitação declarada pelos autores.
"""


def test_ler_e_hash_estavel():
    a = cbk.ler_yaml(YAML)
    b = cbk.ler_yaml(YAML)
    assert a.hash() == b.hash()
    assert a.campo("tamanho_amostra").hash() == b.campo("tamanho_amostra").hash()
    # The label does not change the field hash.
    c = cbk.ler_yaml(YAML.replace("nome: limitacoes", "nome: limitacoes\n    rotulo: Limitações"))
    assert c.campo("limitacoes").hash() == a.campo("limitacoes").hash()
    assert c.campo("limitacoes").rotulo == "Limitações"
    d = cbk.ler_yaml(YAML.replace("Principal limitação", "A limitação"))
    assert d.campo("limitacoes").hash() != a.campo("limitacoes").hash()


def test_yaml_invalido_mensagens_por_campo():
    with pytest.raises(CodebookInvalido, match="campo 'x'"):
        cbk.ler_yaml("campos:\n  - nome: x\n    tipo: desconhecido\n    instrucao: abc")
    with pytest.raises(CodebookInvalido):
        cbk.ler_yaml("campos: [")


def test_lint_aponta_problemas():
    cb = cbk.ler_yaml("""
campos:
  - nome: Pais
    tipo: categorico
    valores: [brasil, Brasil, nao_reportado]
    instrucao: País?
  - nome: n
    tipo: numerico
    instrucao: Número de participantes e também a idade média dos participantes.
    regras: [{tipo: soma_igual, campos: [a, b]}]
  - nome: lim
    tipo: texto
    instrucao: Indique se o estudo reporta limitações explicitamente.
""")
    codigos = {(a["campo"], a["codigo"]) for a in cbk.lint(cb)}
    assert ("Pais", "L001") in codigos
    assert ("Pais", "L004") in codigos
    assert ("Pais", "L010") in codigos
    assert ("Pais", "L007") in codigos
    assert ("n", "L005") in codigos and ("n", "L006") in codigos
    assert ("n", "L008") in codigos
    assert ("n", "L013") in codigos
    assert ("lim", "L009") in codigos
    assert cbk.tem_erros(cbk.lint(cb))


def test_lint_codebook_bom_sem_erros():
    achados = cbk.lint(cbk.ler_yaml(YAML))
    assert not cbk.tem_erros(achados), achados


def test_versoes_rascunho_congelar(con):
    cb = cbk.ler_yaml(YAML)
    r1 = cbk.salvar_rascunho(con, cb)
    assert r1["versao"] == 1 and not r1["congelado"]
    # Saving again with a change edits the same draft.
    cb2 = cbk.ler_yaml(YAML.replace("Teste", "Teste 2"))
    r1b = cbk.salvar_rascunho(con, cb2)
    assert r1b["versao"] == 1 and r1b["hash"] != r1["hash"]
    f = cbk.congelar(con)
    assert f["congelado"] == 1
    # After freezing, a change creates version 2 pointing to version 1.
    r2 = cbk.salvar_rascunho(con, cbk.ler_yaml(YAML.replace("risco de viés", "risco de viés global")))
    assert r2["versao"] == 2 and r2["versao_anterior_id"] == f["id"]
    # Identical content is a no-op.
    assert cbk.salvar_rascunho(con, cbk.carregar(con, 2))["id"] == r2["id"]
    d = cbk.diff(con, 1, 2)
    assert [x["campo"] for x in d["alterados"]] == ["risco_vies"]
    hist = cbk.historico(con)
    assert [h["versao"] for h in hist] == [1, 2]
    assert cbk.ultimo_congelado(con)["versao"] == 1
    assert cbk.carregar(con, 1).campo("tamanho_amostra").faixa == (1, 100000)


def test_rascunho_com_erro_recusado(con):
    with pytest.raises(CodebookInvalido):
        cbk.salvar_rascunho(con, cbk.ler_yaml("campos:\n - {nome: X, tipo: texto, instrucao: abc}"))
    with pytest.raises(EstadoInvalido):
        cbk.congelar(con)


def test_export_yaml_roundtrip():
    cb = cbk.ler_yaml(YAML)
    assert cbk.ler_yaml(cb.para_yaml()).hash() == cb.hash()


def test_regras_por_bruta():
    cb = cbk.ler_yaml(YAML)
    ok, det, norm = regras.checar_bruta(cb.campo("desenho_estudo"), "Experimental", False)
    assert ok and norm == "experimental"
    ok, det, _ = regras.checar_bruta(cb.campo("desenho_estudo"), "quasi", False)
    assert not ok and "fora da lista" in det
    ok, det, norm = regras.checar_bruta(cb.campo("tamanho_amostra"), "1,212", False)
    assert ok and norm == "1212"
    ok, det, _ = regras.checar_bruta(cb.campo("tamanho_amostra"), "0", False)
    assert not ok and "faixa" in det
    ok, det, _ = regras.checar_bruta(cb.campo("tamanho_amostra"), "muitos", False)
    assert not ok
    assert regras.checar_bruta(cb.campo("tamanho_amostra"), None, True) == (True, "", None)
    ok, det, _ = regras.checar_bruta(cb.campo("limitacoes"), "", False)
    assert not ok


def test_regras_entre_campos():
    cb = cbk.ler_yaml(YAML)
    falhas = regras.checar_artigo(cb, {
        "tamanho_amostra": ("212", False), "n_intervencao": ("106", False), "n_controle": ("100", False),
    })
    assert set(falhas) == {"tamanho_amostra", "n_intervencao", "n_controle"}
    ok = regras.checar_artigo(cb, {
        "tamanho_amostra": ("212", False), "n_intervencao": ("106", False), "n_controle": ("106", False),
    })
    assert ok == {}
    # Absent field: rule not applicable.
    assert regras.checar_artigo(cb, {"tamanho_amostra": ("212", False),
                                     "n_intervencao": (None, True), "n_controle": ("1", False)}) == {}


def test_regras_outros_tipos():
    cb = cbk.ler_yaml("""
campos:
  - {nome: a, tipo: numerico, instrucao: valor a do estudo, unidade: x, faixa: [0, 10],
     regras: [{tipo: menor_ou_igual, campo: b}]}
  - {nome: b, tipo: numerico, instrucao: valor b do estudo, unidade: x, faixa: [0, 10],
     regras: [{tipo: maior_ou_igual, campo: a}]}
  - {nome: c, tipo: categorico, valores: [sim, nao], instrucao: "houve randomizacao?",
     regras: [{tipo: requer, campo: a}, {tipo: valor_implica, se: sim, campo: d, entao: [rct]}]}
  - {nome: d, tipo: categorico, valores: [rct, coorte], instrucao: desenho do estudo informado}
""")
    f = regras.checar_artigo(cb, {"a": ("5", False), "b": ("3", False), "c": ("sim", False),
                                  "d": ("coorte", False)})
    assert "a" in f and "b" in f and "d" in f
    f2 = regras.checar_artigo(cb, {"a": (None, True), "b": ("3", False), "c": ("sim", False),
                                   "d": ("rct", False)})
    assert "c" in f2 and "a" in f2
