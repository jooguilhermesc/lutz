"""Every worked example of the validation document becomes a test."""

from __future__ import annotations

import math

import numpy as np
import pytest

from lutz.core import metricas as m


def _de_matriz(tabela, rotulos):
    a, b = [], []
    for i, linha in enumerate(tabela):
        for j, n in enumerate(linha):
            a += [rotulos[i]] * n
            b += [rotulos[j]] * n
    return a, b


def test_cohen_exemplo_desenho_estudo():
    a, b = _de_matriz([[14, 2, 0], [1, 15, 1], [0, 1, 6]], ["E", "O", "R"])
    assert len(a) == 40
    assert m.concordancia(a, b) == pytest.approx(0.875)
    assert m.cohen_kappa(a, b) == pytest.approx(0.80, abs=0.005)


def test_cohen_contra_sklearn():
    sk = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(1)
    a = list(rng.choice(["x", "y", "z"], 50))
    b = [x if rng.random() < 0.7 else "y" for x in a]
    assert m.cohen_kappa(a, b) == pytest.approx(sk.cohen_kappa_score(a, b))


def test_kappa_ponderado_exemplo_risco_vies():
    ordem = ["baixo", "moderado", "alto"]
    a, b = _de_matriz([[10, 2, 0], [1, 8, 2], [1, 1, 5]], ordem)
    assert m.cohen_kappa(a, b) == pytest.approx(0.64, abs=0.005)
    assert m.kappa_ponderado(a, b, ordem, "linear") == pytest.approx(0.68, abs=0.005)
    assert m.kappa_ponderado(a, b, ordem, "quadratico") == pytest.approx(0.72, abs=0.005)


def test_kappa_ponderado_contra_sklearn():
    sk = pytest.importorskip("sklearn.metrics")
    ordem = ["baixo", "moderado", "alto"]
    a, b = _de_matriz([[10, 2, 0], [1, 8, 2], [1, 1, 5]], ordem)
    cod = {v: i for i, v in enumerate(ordem)}
    esperado = sk.cohen_kappa_score([cod[x] for x in a], [cod[x] for x in b], weights="quadratic")
    assert m.kappa_ponderado(a, b, ordem) == pytest.approx(esperado)


def test_pabak_paradoxo_do_kappa():
    a = ["sim"] * 36 + ["sim"] * 2 + ["nao"] * 1 + ["nao"]
    b = ["sim"] * 36 + ["nao"] * 2 + ["sim"] * 1 + ["nao"]
    assert m.concordancia(a, b) == pytest.approx(0.925)
    assert m.cohen_kappa(a, b) == pytest.approx(0.36, abs=0.01)
    assert m.pabak(a, b) == pytest.approx(0.85)
    cat, frac = m.categoria_dominante(b)
    assert cat == "sim" and frac == pytest.approx(37 / 40)


FLEISS = [["E", "E", "E"], ["O", "O", "O"], ["E", "E", "O"], ["R", "R", "R"], ["O", "O", "O"],
          ["O", "R", "O"]]


def test_fleiss_exemplo():
    assert m.fleiss_kappa(FLEISS) == pytest.approx(0.64, abs=0.005)


def test_fleiss_contra_statsmodels():
    ir = pytest.importorskip("statsmodels.stats.inter_rater")
    cod = {"E": 0, "O": 1, "R": 2}
    tabela, _ = ir.aggregate_raters(np.array([[cod[x] for x in r] for r in FLEISS]))
    assert m.fleiss_kappa(FLEISS) == pytest.approx(ir.fleiss_kappa(tabela))


def test_alfa_exemplo_nominal():
    por_avaliador = [list(col) for col in zip(*FLEISS, strict=False)]
    assert m.alfa_krippendorff(por_avaliador, "nominal") == pytest.approx(0.66, abs=0.005)


def test_alfa_dados_faltantes_e_degenerados():
    assert math.isnan(m.alfa_krippendorff([["a", "a"], ["a", "a"]], "nominal"))
    assert math.isnan(m.alfa_krippendorff([], "nominal"))
    v = m.alfa_krippendorff([[1, 2, 3, None], [1, 2, 4, 5], [1, None, 3, 5]], "interval")
    assert 0.8 < v <= 1
    o = m.alfa_krippendorff([["b", "m", "a"], ["b", "m", "m"], ["b", "x", "a"]], "ordinal",
                            ordem=["b", "m", "a"])
    assert not math.isnan(o)


def test_icc_exemplo_tamanho_amostra():
    humano = [120, 45, 300, 80, 210, 60]
    lutz = [120, 48, 300, 80, 201, 60]
    icc, ms = m.icc_a1(list(zip(humano, lutz, strict=False)))
    assert icc == pytest.approx(0.999, abs=0.0005)
    assert ms["MSR"] == pytest.approx(19560.7, abs=0.1)
    assert ms["MSC"] == pytest.approx(3.0, abs=0.01)
    assert ms["MSE"] == pytest.approx(8.4, abs=0.01)
    e = m.erros_absolutos(lutz, humano)
    assert e["medio"] == pytest.approx(2.0) and e["maximo"] == 9


def test_icc_degenerado():
    assert math.isnan(m.icc_a1([[1, 1]])[0])
    assert math.isnan(m.icc_a1([[5, 5], [5, 5]])[0])


def test_wilson_exemplo():
    p, lo, hi = m.wilson(118, 121)
    assert p == pytest.approx(0.975, abs=0.001)
    assert lo == pytest.approx(0.930, abs=0.001)
    assert hi == pytest.approx(0.992, abs=0.001)
    assert all(math.isnan(x) for x in m.wilson(0, 0))


def test_wilson_contra_statsmodels():
    prop = pytest.importorskip("statsmodels.stats.proportion")
    lo, hi = prop.proportion_confint(55, 64, method="wilson")
    _, a, b = m.wilson(55, 64)
    assert (a, b) == pytest.approx((lo, hi), abs=1e-6)


def test_bootstrap_reprodutivel_e_por_unidade():
    a, b = _de_matriz([[14, 2, 0], [1, 15, 1], [0, 1, 6]], ["E", "O", "R"])
    a, b = np.array(a), np.array(b)

    def k(idx):
        return m.cohen_kappa(list(a[idx]), list(b[idx]))

    ic1 = m.bootstrap_ic(k, len(a), semente=42, repeticoes=500)
    ic2 = m.bootstrap_ic(k, len(a), semente=42, repeticoes=500)
    assert ic1 == ic2
    assert ic1[0] < 0.80 < ic1[1]
    assert all(math.isnan(x) for x in m.bootstrap_ic(k, 1))


def test_tabela_tamanho_piloto():
    t = {r["n"]: r for r in m.tabela_tamanho_piloto()}
    assert t[20]["erro_padrao"] == pytest.approx(0.13, abs=0.005)
    assert t[20]["meia_largura"] == pytest.approx(0.26, abs=0.01)
    assert t[30]["meia_largura"] == pytest.approx(0.21, abs=0.01)
    assert t[100]["meia_largura"] == pytest.approx(0.12, abs=0.01)


def test_n_para_meia_largura():
    n = m.n_para_meia_largura(0.06, 0.95)
    _, lo, hi = m.wilson(round(0.95 * n), n)
    assert (hi - lo) / 2 <= 0.06
    _, lo, hi = m.wilson(round(0.95 * (n - 1)), n - 1)
    assert (hi - lo) / 2 > 0.06 or n == 5


def test_kappa_degenerado():
    assert math.isnan(m.cohen_kappa(["a", "a"], ["a", "a"]))
    assert math.isnan(m.cohen_kappa([], []))
    assert math.isnan(m.kappa_ponderado(["a"], ["a"], ["a"]))
    assert math.isnan(m.concordancia([None], [1]))
