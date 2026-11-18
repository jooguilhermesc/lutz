"""Agreement statistics. Pure functions over plain Python lists / numpy arrays.

Formulas and worked examples: docs/metodos-estatisticos.md. The tests check every worked
example of that document (Cohen 0.80, weighted 0.68/0.72, PABAK 0.85, Fleiss 0.64,
Krippendorff 0.66, ICC 0.999, Wilson 93.0–99.2 %).

Degenerate inputs return ``nan`` (never raise); the report turns ``nan`` into an explanation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

NAN = float("nan")


def _validos(a: Sequence[Any], b: Sequence[Any]) -> tuple[list, list]:
    pa, pb = [], []
    for x, y in zip(a, b, strict=True):
        if x is None or y is None:
            continue
        pa.append(x)
        pb.append(y)
    return pa, pb


def concordancia(a: Sequence[Any], b: Sequence[Any]) -> float:
    a, b = _validos(a, b)
    if not a:
        return NAN
    return sum(x == y for x, y in zip(a, b, strict=False)) / len(a)


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> float:
    a, b = _validos(a, b)
    n = len(a)
    if n == 0:
        return NAN
    cats = sorted(set(a) | set(b), key=str)
    po = sum(x == y for x, y in zip(a, b, strict=False)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    if math.isclose(pe, 1.0):
        return NAN
    return (po - pe) / (1 - pe)


def kappa_ponderado(
    a: Sequence[Any], b: Sequence[Any], ordem: Sequence[Any], pesos: str = "quadratico"
) -> float:
    """Weighted kappa. *ordem* is the codebook order of the ordinal values.

    Values outside *ordem* (e.g. "não reportado") are ignored here; they enter the simple kappa.
    """
    idx = {v: i for i, v in enumerate(ordem)}
    pares = [(idx[x], idx[y]) for x, y in zip(a, b, strict=True) if x in idx and y in idx]
    k = len(ordem)
    n = len(pares)
    if n == 0 or k < 2:
        return NAN
    obs = np.zeros((k, k))
    for i, j in pares:
        obs[i, j] += 1
    obs /= n
    linhas, colunas = obs.sum(axis=1), obs.sum(axis=0)
    i, j = np.indices((k, k))
    if pesos == "linear":
        w = 1 - np.abs(i - j) / (k - 1)
    else:
        w = 1 - (i - j) ** 2 / (k - 1) ** 2
    po = float((w * obs).sum())
    pe = float((w * np.outer(linhas, colunas)).sum())
    if math.isclose(pe, 1.0):
        return NAN
    return (po - pe) / (1 - pe)


def pabak(a: Sequence[Any], b: Sequence[Any], k: int | None = None) -> float:
    """Prevalence-adjusted bias-adjusted kappa: (k·po − 1)/(k − 1)."""
    a, b = _validos(a, b)
    if not a:
        return NAN
    k = k or len(set(a) | set(b))
    k = max(k, 2)
    po = concordancia(a, b)
    return (k * po - 1) / (k - 1)


def categoria_dominante(valores: Sequence[Any]) -> tuple[Any, float]:
    vals = [v for v in valores if v is not None]
    if not vals:
        return None, 0.0
    melhor = max(set(vals), key=lambda v: (vals.count(v), str(v)))
    return melhor, vals.count(melhor) / len(vals)


def fleiss_kappa(dados: Sequence[Sequence[Any]]) -> float:
    """*dados*: one row per unit (article), one column per rater; no missing values."""
    linhas = [list(r) for r in dados if all(x is not None for x in r)]
    if not linhas:
        return NAN
    m = len(linhas[0])
    if m < 2:
        return NAN
    cats = sorted({x for r in linhas for x in r}, key=str)
    n_ij = np.array([[r.count(c) for c in cats] for r in linhas], dtype=float)
    N = len(linhas)
    P_i = (n_ij * (n_ij - 1)).sum(axis=1) / (m * (m - 1))
    P_bar = P_i.mean()
    p_j = n_ij.sum(axis=0) / (N * m)
    Pe = float((p_j**2).sum())
    if math.isclose(Pe, 1.0):
        return NAN
    return float((P_bar - Pe) / (1 - Pe))


def alfa_krippendorff(dados: Sequence[Sequence[Any]], nivel: str = "nominal",
                      ordem: Sequence[Any] | None = None) -> float:
    """Krippendorff's alpha. *dados*: one row per RATER, one column per unit; None = missing.

    ``nivel``: nominal | ordinal | interval. For nominal data the values are mapped to codes;
    for ordinal data the codes follow *ordem* (values outside it count as missing).
    """
    import krippendorff

    if not dados or not dados[0]:
        return NAN
    if nivel == "nominal":
        cats = sorted({x for r in dados for x in r if x is not None}, key=str)
        cod = {c: i for i, c in enumerate(cats)}
        mat = np.array([[cod[x] if x is not None else np.nan for x in r] for r in dados], dtype=float)
    elif nivel == "ordinal":
        cod = {c: i for i, c in enumerate(ordem or [])}
        mat = np.array([[cod.get(x, np.nan) if x is not None else np.nan for x in r] for r in dados],
                       dtype=float)
    else:
        mat = np.array([[float(x) if x is not None else np.nan for x in r] for r in dados], dtype=float)
    # Units with fewer than two values carry no pairable information.
    pareaveis = (~np.isnan(mat)).sum(axis=0) >= 2
    mat = mat[:, pareaveis]
    if mat.shape[1] < 2:
        return NAN  # a single unit carries no information about chance agreement
    valores = mat[~np.isnan(mat)]
    if len(np.unique(valores)) < 2:
        return NAN  # no variation: alpha undefined
    try:
        kw: dict[str, Any] = {"reliability_data": mat, "level_of_measurement": nivel}
        if nivel == "ordinal":
            kw["value_domain"] = list(range(len(ordem or [])))
        return float(krippendorff.alpha(**kw))
    except (ValueError, ZeroDivisionError):  # pragma: no cover - degenerate after filtering
        return NAN


def icc_a1(matriz: Sequence[Sequence[float]]) -> tuple[float, dict]:
    """ICC(A,1): two-way random effects, absolute agreement, single rater (McGraw & Wong).

    *matriz*: n units × k raters, complete cases only. Returns (icc, {MSR, MSC, MSE}).
    """
    x = np.array([r for r in matriz if all(v is not None and not math.isnan(v) for v in r)],
                 dtype=float)
    if x.ndim != 2 or x.shape[0] < 2 or x.shape[1] < 2:
        return NAN, {}
    n, k = x.shape
    media = x.mean()
    ss_linhas = k * ((x.mean(axis=1) - media) ** 2).sum()
    ss_colunas = n * ((x.mean(axis=0) - media) ** 2).sum()
    ss_total = ((x - media) ** 2).sum()
    ss_erro = ss_total - ss_linhas - ss_colunas
    msr = ss_linhas / (n - 1)
    msc = ss_colunas / (k - 1)
    mse = ss_erro / ((n - 1) * (k - 1))
    denom = msr + (k - 1) * mse + (k / n) * (msc - mse)
    if math.isclose(denom, 0.0):
        return NAN, {"MSR": msr, "MSC": msc, "MSE": mse}
    return float((msr - mse) / denom), {"MSR": float(msr), "MSC": float(msc), "MSE": float(mse)}


def erros_absolutos(a: Sequence[float | None], b: Sequence[float | None]) -> dict:
    d = [abs(x - y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    if not d:
        return {"mediano": NAN, "medio": NAN, "maximo": NAN, "n": 0}
    return {"mediano": float(np.median(d)), "medio": float(np.mean(d)), "maximo": float(max(d)),
            "n": len(d)}


def wilson(acertos: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n <= 0:
        return NAN, NAN, NAN
    p = acertos / n
    den = 1 + z**2 / n
    centro = (p + z**2 / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return p, max(0.0, centro - meia), min(1.0, centro + meia)


def bootstrap_ic(
    metrica: Callable[[np.ndarray], float],
    n_unidades: int,
    semente: int = 42,
    repeticoes: int = 2000,
) -> tuple[float, float]:
    """Percentile bootstrap over UNITS (articles), never over cells.

    *metrica* receives an array of resampled unit indices and returns a value (nan allowed).
    """
    if n_unidades < 2:
        return NAN, NAN
    rng = np.random.default_rng(semente)
    vals = []
    for _ in range(repeticoes):
        idx = rng.integers(0, n_unidades, n_unidades)
        v = metrica(idx)
        if v is not None and not math.isnan(v):
            vals.append(v)
    if len(vals) < repeticoes * 0.5:
        return NAN, NAN
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def ep_kappa(po: float, pe: float, n: int) -> float:
    return math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))


def tabela_tamanho_piloto(po: float = 0.90, pe: float = 0.50,
                          tamanhos: Sequence[int] = (20, 30, 40, 60, 100)) -> list[dict]:
    out = []
    for n in tamanhos:
        ep = ep_kappa(po, pe, n)
        out.append({"n": n, "erro_padrao": ep, "meia_largura": 1.96 * ep})
    return out


def n_para_meia_largura(meia_largura: float, p: float = 0.95, maximo: int = 100_000) -> int:
    """Smallest n whose Wilson 95% interval at proportion *p* has half-width ≤ target."""
    for n in range(5, maximo):
        acertos = round(p * n)
        _, lo, hi = wilson(acertos, n)
        if (hi - lo) / 2 <= meia_largura:
            return n
    return maximo  # pragma: no cover
