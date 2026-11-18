"""Deterministic codebook rules.

* Per extraction (gate on each raw answer): type, value in the list, plausible range.
* Per article (after consolidation): cross-field rules declared in ``regras``.

A failed rule sends the cell to Baixa. A rule that references a field reported as absent
is "not applicable" and does not fail.
"""

from __future__ import annotations

from lutz.core.codebook import Campo, Codebook
from lutz.core.texto import iguais_numericos, normalizar_rotulo, parse_numero


def normalizar_valor(campo: Campo, valor: str | None, nao_reportado: bool) -> tuple[str | None, str]:
    """Map a raw answer to the canonical form used for agreement.

    Returns (normalized value or None, error message or ""). For categorical/ordinal fields the
    normalized value is the canonical spelling from ``valores``.
    """
    if nao_reportado:
        return None, ""
    if valor is None or str(valor).strip() == "":
        return None, "valor vazio sem marcar não reportado"
    if campo.tipo in ("categorico", "ordinal"):
        alvo = normalizar_rotulo(valor)
        for v in campo.valores:
            if normalizar_rotulo(v) == alvo:
                return v, ""
        return None, f"valor '{valor}' fora da lista do codebook"
    if campo.tipo == "numerico":
        n = parse_numero(valor)
        if n is None:
            return None, f"'{valor}' não é um número"
        from lutz.core.texto import formatar_numero

        return formatar_numero(n), ""
    return str(valor).strip(), ""


def checar_bruta(campo: Campo, valor: str | None, nao_reportado: bool) -> tuple[bool, str, str | None]:
    """Gate for one raw extraction. Returns (ok, detail, normalized value)."""
    norm, erro = normalizar_valor(campo, valor, nao_reportado)
    if erro:
        return False, erro, None
    if nao_reportado:
        return True, "", None
    if campo.tipo == "numerico" and campo.faixa is not None:
        n = float(norm)  # type: ignore[arg-type]
        lo, hi = campo.faixa
        if not (lo <= n <= hi):
            return False, f"{norm} fora da faixa plausível [{lo:g}, {hi:g}]", norm
    return True, "", norm


def checar_artigo(cb: Codebook, valores: dict[str, tuple[str | None, bool]]) -> dict[str, list[str]]:
    """Cross-field rules for one article.

    *valores*: {field: (final normalized value or None, nao_reportado)}.
    Returns {field: [violation messages]} for fields whose rules failed.
    """
    falhas: dict[str, list[str]] = {}

    def num(nome: str) -> float | None:
        v, nr = valores.get(nome, (None, True))
        if nr or v is None:
            return None
        return parse_numero(v)

    for c in cb.campos:
        for r in c.regras:
            msg = None
            if r.tipo == "soma_igual":
                alvo = num(c.nome)
                partes = [num(x) for x in r.campos]
                if alvo is not None and all(p is not None for p in partes):
                    soma = sum(partes)  # type: ignore[arg-type]
                    if not iguais_numericos(alvo, soma, r.tolerancia_relativa):
                        msg = f"soma de {', '.join(r.campos)} = {soma:g}, diferente de {alvo:g}"
            elif r.tipo in ("menor_ou_igual", "maior_ou_igual"):
                a, b = num(c.nome), num(r.campo or "")
                if a is not None and b is not None:
                    if r.tipo == "menor_ou_igual" and a > b:
                        msg = f"{c.nome} ({a:g}) maior que {r.campo} ({b:g})"
                    if r.tipo == "maior_ou_igual" and a < b:
                        msg = f"{c.nome} ({a:g}) menor que {r.campo} ({b:g})"
            elif r.tipo == "requer":
                v, nr = valores.get(c.nome, (None, True))
                v2, nr2 = valores.get(r.campo or "", (None, True))
                if not nr and v is not None and (nr2 or v2 is None):
                    msg = f"{c.nome} foi reportado mas {r.campo} não"
            elif r.tipo == "valor_implica":
                v, nr = valores.get(c.nome, (None, True))
                v2, nr2 = valores.get(r.campo or "", (None, True))
                if (not nr and v is not None and normalizar_rotulo(v) == normalizar_rotulo(r.se)
                        and not nr2 and v2 is not None
                        and normalizar_rotulo(v2) not in {normalizar_rotulo(x) for x in r.entao}):
                    msg = f"{c.nome} = {r.se} exige {r.campo} em {r.entao}, mas veio '{v2}'"
            if msg:
                for nome in [c.nome, *r.referencias()]:
                    falhas.setdefault(nome, []).append(msg)
    return falhas
