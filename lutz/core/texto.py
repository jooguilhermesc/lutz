"""Text normalization shared by ingestion, evidence checking and consolidation."""

from __future__ import annotations

import math
import re
import unicodedata

_HIFEN_QUEBRA = re.compile(r"(\w)[-­‐‑]\s*\n\s*(\w)")
_ASPAS = re.compile(r"[‘’‚‛′`´]")
_ASPAS_DUPLAS = re.compile(r"[“”„‟″«»]")
_TRACOS = re.compile(r"[‐‑‒–—―−]")
_INVISIVEIS = re.compile(r"[­​‌‍⁠﻿]")
_ESPACOS = re.compile(r"\s+")


def normalizar(txt: str | None) -> str:
    """Normalization applied identically to the quoted excerpt and to the page text.

    NFKC (ligatures, full-width forms), soft hyphens and zero-width characters removed,
    words hyphenated across a line break re-joined, quotes and dashes unified, lower case,
    whitespace collapsed.
    """
    if not txt:
        return ""
    t = unicodedata.normalize("NFKC", txt)
    t = _HIFEN_QUEBRA.sub(r"\1\2", t)
    t = _INVISIVEIS.sub("", t)
    t = t.replace(" ", " ").replace(" ", " ")
    t = _ASPAS.sub("'", t)
    t = _ASPAS_DUPLAS.sub('"', t)
    t = _TRACOS.sub("-", t)
    t = t.casefold()
    t = _ESPACOS.sub(" ", t)
    return t.strip()


def normalizar_rotulo(txt: str | None) -> str:
    """Normalization for categorical values: NFKC, casefold, no accents, single spaces."""
    if txt is None:
        return ""
    t = unicodedata.normalize("NFKD", str(txt))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.casefold().strip()
    t = re.sub(r"[\s_\-]+", " ", t)
    return t


# ── numbers ──────────────────────────────────────────────────────────────────

_NUM = re.compile(
    r"(?<![\w.,])[-+]?(?:\d{1,3}(?:[.,   ]\d{3})+|\d+)(?:[.,]\d+)?(?:\s*[x×]\s*10\^?[-+]?\d+)?"
    r"|(?<![\w.,])[-+]?[.,]\d+"
)
_EXTENSO = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100,
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "vinte": 20, "trinta": 30,
    "cem": 100,
}


def _parse_token(tok: str) -> float | None:
    t = tok.strip().replace(" ", " ").replace(" ", " ")
    exp = 0
    m = re.search(r"\s*[x×]\s*10\^?([-+]?\d+)$", t)
    if m:
        exp = int(m.group(1))
        t = t[: m.start()]
    t = t.replace(" ", "")
    sinal = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("+-")
    if not t:
        return None
    # Decide which separator is decimal.
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # 1.234,5
        else:
            t = t.replace(",", "")  # 1,234.5
    elif "," in t:
        partes = t.split(",")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3 and partes[0] not in ("", "0")):
            t = t.replace(",", "")  # 1,212 -> thousands
        else:
            t = t.replace(",", ".")  # 0,875 -> decimal
    elif "." in t:
        partes = t.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3 and partes[0] not in ("", "0")
                               and len(partes[0]) <= 3):
            # 1.212 is ambiguous; in excerpts of pt/es/de papers it is a thousands separator.
            # We keep BOTH readings available through numeros_em(); here prefer decimal.
            pass
    try:
        return sinal * float(t) * (10.0**exp)
    except ValueError:
        return None


def parse_numero(valor: str | float | int | None) -> float | None:
    """Parse a value returned by an extractor (e.g. '212', '1,212', '45.3%', 'n = 40')."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return None if (isinstance(valor, float) and math.isnan(valor)) else float(valor)
    s = str(valor).strip()
    if not s:
        return None
    if re.search(r"\d\s*[-–—]\s*\d", s) and not re.match(r"^\s*-\d", s):
        return None  # ranges like 20–30 are not a single number
    m = _NUM.search(s)
    if m:
        return _parse_token(m.group(0))
    palavra = normalizar_rotulo(s)
    if palavra in _EXTENSO:
        return float(_EXTENSO[palavra])
    return None


def numeros_em(texto: str) -> list[float]:
    """Every number that appears in *texto*, with both readings of ambiguous separators."""
    out: list[float] = []
    for m in _NUM.finditer(texto or ""):
        tok = m.group(0)
        v = _parse_token(tok)
        if v is not None:
            out.append(v)
        # "1.212" / "1,212": also read as thousands (1212) and as decimal (1.212).
        limpo = tok.strip()
        if re.fullmatch(r"[-+]?\d{1,3}([.,])\d{3}", limpo):
            out.append(float(re.sub(r"[.,]", "", limpo)))
            out.append(float(limpo.replace(",", ".")))
    for palavra in re.findall(r"[a-zçãé]+", normalizar(texto)):
        if palavra in _EXTENSO:
            out.append(float(_EXTENSO[palavra]))
    return out


def numero_no_trecho(valor: float, trecho: str, tolerancia_relativa: float = 0.0) -> bool:
    """True when the extracted number appears in the excerpt (percent or plain)."""
    for n in numeros_em(trecho):
        if iguais_numericos(valor, n, tolerancia_relativa):
            return True
        if iguais_numericos(valor, n * 100, tolerancia_relativa) or iguais_numericos(
            valor * 100, n, tolerancia_relativa
        ):
            # 0.45 in the field vs "45%" in the text, and vice versa.
            if "%" in trecho:
                return True
    return False


def iguais_numericos(a: float, b: float, tolerancia_relativa: float = 0.0) -> bool:
    if tolerancia_relativa <= 0:
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return abs(a - b) <= tolerancia_relativa * max(abs(a), abs(b)) + 1e-12


def formatar_numero(v: float) -> str:
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.6g}"


def estimar_tokens(texto: str) -> int:
    """Conservative estimate: 1 token per 3.5 characters (mixed pt/en scientific text)."""
    return int(len(texto) / 3.5) + 1
