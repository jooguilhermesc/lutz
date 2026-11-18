"""From three raw answers to one cell: agreement ``a``, winner, level.

Definitions fixed by the brief (decisions 5 and 6):

* ``a`` is always computed over the three configured extractors; an extractor that failed or
  whose answer broke a per-answer rule counts as disagreement.
* Categorical/ordinal: same canonical value. Numeric: values within the relative tolerance of
  the median of the reported values (deterministic, no transitivity problem); the final value
  is the value of the winner. Free text: the answer that agrees with most others (medoid) and
  the answers that agree with it, by token-set similarity or overlapping cited units.
* "Not reported" is its own group.
* No group with at least two members (e.g. 1-1-1): ``valor_final`` is NULL, level Baixa, no
  score.
* Winner (whose excerpt is shown and verified): highest ``e`` in the majority group, then the
  lowest extractor index.
* Alta requires a = 1, e = 1, v = 1, rules OK and, when ``alta_exige_evidencia_no_grupo``,
  every answer of the majority group with e ≥ 0.5 (no invented quote among the agreeing ones).
* Not reported: e does not apply (1 by convention); the level is at most Média.
* No verifier configured: v = 1 is declared and reported as a limitation.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from lutz.config.settings import Limiares
from lutz.core.codebook import Campo
from lutz.core.texto import iguais_numericos, normalizar

N_EXTRATORES = 3
VAZIO = "∅"


@dataclass
class Bruta:
    rotulo: str
    ok: bool  # call succeeded and per-answer rules passed
    valor: str | None  # normalized value
    nao_reportado: bool
    e: float | None
    unidades: list[str] = field(default_factory=list)
    trecho: str | None = None
    pagina: int | None = None
    erro: str = ""


@dataclass
class Consolidado:
    valor: str | None
    nao_reportado: bool
    a: float
    vencedor: Bruta | None
    grupo: list[Bruta]
    empate: bool
    motivos: list[str]


def _texto_concorda(x: Bruta, y: Bruta, limiar: float) -> bool:
    if set(x.unidades) & set(y.unidades):
        inter = len(set(x.unidades) & set(y.unidades))
        uniao = len(set(x.unidades) | set(y.unidades))
        if inter / uniao >= 0.5:
            return True
    return fuzz.token_set_ratio(normalizar(x.valor), normalizar(y.valor)) >= limiar


def consolidar(campo: Campo, brutas: list[Bruta], limiares: Limiares) -> Consolidado:
    motivos = [f"{b.rotulo}: {b.erro}" for b in brutas if not b.ok and b.erro]
    validas = [b for b in brutas if b.ok]
    nr = [b for b in validas if b.nao_reportado]
    com_valor = [b for b in validas if not b.nao_reportado and b.valor is not None]

    grupos: list[list[Bruta]] = []
    if nr:
        grupos.append(nr)
    if campo.tipo in ("categorico", "ordinal"):
        por_valor: dict[str, list[Bruta]] = {}
        for b in com_valor:
            por_valor.setdefault(b.valor, []).append(b)  # type: ignore[arg-type]
        grupos += list(por_valor.values())
    elif campo.tipo == "numerico":
        nums = [(b, float(b.valor)) for b in com_valor]  # type: ignore[arg-type]
        if nums:
            med = statistics.median(v for _, v in nums)
            g = [b for b, v in nums if iguais_numericos(v, med, campo.tolerancia_relativa)]
            resto = [b for b, v in nums if b not in g]
            if g:
                grupos.append(g)
            grupos += [[b] for b in resto]
    else:
        if com_valor:
            concordancias = {
                b.rotulo: [o for o in com_valor if o is not b and _texto_concorda(b, o, limiares.texto_similaridade)]
                for b in com_valor
            }
            medoide = max(com_valor, key=lambda b: (len(concordancias[b.rotulo]), -com_valor.index(b)))
            g = [medoide, *concordancias[medoide.rotulo]]
            g.sort(key=lambda b: b.rotulo)
            grupos.append(g)
            grupos += [[b] for b in com_valor if b not in g]

    grupos.sort(key=lambda g: -len(g))
    if not grupos or len(grupos[0]) < 2 or (len(grupos) > 1 and len(grupos[1]) == len(grupos[0])):
        motivos.insert(0, "sem maioria entre os extratores (empate)")
        return Consolidado(None, False, (len(grupos[0]) / N_EXTRATORES) if grupos else 0.0,
                           None, [], True, motivos)
    maior = grupos[0]
    a = len(maior) / N_EXTRATORES
    ordem = {b.rotulo: i for i, b in enumerate(brutas)}
    vencedor = sorted(maior, key=lambda b: (-(b.e or 0.0), ordem[b.rotulo]))[0]
    if maior is nr:
        return Consolidado(None, True, a, vencedor, maior, False, motivos)
    # Numeric groups within a tolerance: the winner's value (it has the best evidence), never an
    # average that no extractor reported.
    valor = vencedor.valor
    return Consolidado(valor, False, a, vencedor, maior, False, motivos)


def nivel(c: Consolidado, v: float | None, regras_ok: bool, limiares: Limiares) -> tuple[str, float | None, float, list[str]]:
    """Returns (level, score, e of the cell, extra reasons)."""
    motivos: list[str] = []
    v_ef = 1.0 if v is None else v
    if c.empate:
        return "baixa", None, 0.0, motivos
    e = 1.0 if c.nao_reportado else (c.vencedor.e or 0.0) if c.vencedor else 0.0
    escore = round(c.a * e * v_ef, 4)
    if not regras_ok:
        motivos.append("regra do codebook violada")
        return "baixa", escore, e, motivos
    if c.nao_reportado:
        if c.a >= 2 / 3 - 1e-9 and v_ef >= 0.5:
            motivos.append("não reportado: nível máximo é Média")
            return "media", escore, e, motivos
        if v_ef < 0.5:
            motivos.append("o verificador encontrou a informação que os extratores deram como ausente")
        return "baixa", escore, e, motivos
    grupo_ok = all((b.e or 0) >= 0.5 for b in c.grupo)
    if c.a == 1 and e == 1 and v_ef == 1:
        if grupo_ok or not limiares.alta_exige_evidencia_no_grupo:
            return "alta", escore, e, motivos
        motivos.append("um extrator do grupo majoritário citou trecho não encontrado")
    if c.a >= 2 / 3 - 1e-9 and e >= 0.5 and v_ef >= 0.5:
        if c.a < 1:
            motivos.append("2 de 3 extratores concordam")
        if e < 1:
            motivos.append("evidência parcial (e = 0,5)")
        if v_ef < 1:
            motivos.append("verificador: sustenta em parte")
        return "media", escore, e, motivos
    if e == 0:
        motivos.append("evidência não encontrada (e = 0)")
    if v_ef == 0:
        motivos.append("verificador: trecho não sustenta o valor")
    if c.a < 2 / 3 - 1e-9:
        motivos.append("concordância insuficiente")
    return "baixa", escore, e, motivos
