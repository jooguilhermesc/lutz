"""Evidence check without an LLM: does the quoted excerpt exist where the extractor says?

Scores (spec §6 step 4, refined by the brief):

* ``e = 1``: the normalized excerpt is found literally in the indicated page (in either the
  column order or the raw block order), in the cited units, or across the boundary between the
  indicated page and the next/previous one;
* ``e = 0.5``: found literally on a neighbouring page (±1) or elsewhere in the article, or
  partial similarity ≥ ``evidencia_similaridade`` on the indicated page when the excerpt has at
  least ``evidencia_min_chars_fuzzy`` characters (short excerpts such as "n = 40" match
  anywhere, so they never get fuzzy credit);
* ``e = 0``: not found, found only in hidden text, or — for numeric fields — the extracted
  number does not appear inside the excerpt.

The page may be given as the physical page (1..N, preferred) or as the printed page label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from lutz.config.settings import Limiares
from lutz.core.codebook import Campo
from lutz.core.texto import normalizar, numero_no_trecho, parse_numero


@dataclass
class TextoArtigo:
    paginas: dict[int, tuple[str, str]]  # physical page -> (ordered text, raw-order text)
    rotulos: dict[int, str]  # physical page -> printed label
    unidades: dict[str, tuple[int, str]]  # uid -> (page, text)
    oculto: str = ""

    def __post_init__(self) -> None:
        self._norm = {p: (normalizar(a), normalizar(b)) for p, (a, b) in self.paginas.items()}
        self._norm_unid = {u: normalizar(t) for u, (_, t) in self.unidades.items()}
        self._oculto_norm = normalizar(self.oculto)

    def norm(self, p: int) -> tuple[str, str]:
        return self._norm.get(p, ("", ""))

    def pagina_fisica(self, pagina: int | str | None, uids: list[str]) -> int | None:
        if pagina is not None:
            try:
                p = int(pagina)
            except (TypeError, ValueError):
                p = None
            if p is not None and p in self.paginas:
                return p
            for fis, rot in self.rotulos.items():
                if rot and str(pagina).strip() == rot:
                    return fis
        for u in uids:
            if u in self.unidades:
                return self.unidades[u][0]
        return None


@dataclass
class Evidencia:
    e: float
    detalhe: str
    pagina: int | None
    trecho: str


def _contem(t: str, *textos: str) -> bool:
    return any(t and t in x for x in textos)


def avaliar(
    texto: TextoArtigo, campo: Campo, valor_norm: str | None, nao_reportado: bool,
    trecho: str | None, pagina: int | str | None, uids: list[str], limiares: Limiares,
) -> Evidencia:
    if nao_reportado:
        return Evidencia(1.0, "não reportado: evidência não se aplica", None, "")
    uids_validos = [u for u in uids if u in texto.unidades]
    # Models sometimes write escaped line breaks ("\\n") when stitching several units together.
    trecho = re.sub(r"(\\n|\\r)+", "\n", (trecho or "")).strip()
    if not trecho and uids_validos:
        trecho = " ".join(texto.unidades[u][1] for u in uids_validos)
    t = normalizar(trecho)
    if len(t) < 3:
        return Evidencia(0.0, "sem trecho citado", None, trecho)

    p = texto.pagina_fisica(pagina, uids_validos)
    candidatas = [p] if p is not None else []
    for u in uids_validos:
        pu = texto.unidades[u][0]
        if pu not in candidatas:
            candidatas.append(pu)

    e, detalhe, pagina_ok = 0.0, "", p

    unid_cit = " ".join(texto._norm_unid[u] for u in uids_validos)
    if _contem(t, unid_cit):
        e, detalhe = 1.0, "exato nas unidades citadas"
        pagina_ok = texto.unidades[uids_validos[0]][0]
    if e < 1:
        for c in candidatas:
            a, b = texto.norm(c)
            unid_pag = " ".join(texto._norm_unid[u] for u, (pg, _) in texto.unidades.items() if pg == c)
            if _contem(t, a, b, unid_pag):
                e, detalhe, pagina_ok = 1.0, f"exato na página {c}", c
                break
            prox_a, _ = texto.norm(c + 1)
            ant_a, _ = texto.norm(c - 1)
            if not _contem(t, prox_a, ant_a) and _contem(t, f"{a} {prox_a}", f"{ant_a} {a}"):
                e, detalhe, pagina_ok = 1.0, f"exato atravessando a página {c}", c
                break
    if e < 1 and candidatas:
        for c in candidatas:
            for viz in (c - 1, c + 1):
                if viz in texto.paginas and _contem(t, *texto.norm(viz)):
                    e, detalhe, pagina_ok = 0.5, f"exato na página vizinha {viz} (indicada: {c})", viz
                    break
            if e:
                break
    if e < 1 and e == 0 and len(t) >= limiares.evidencia_min_chars_fuzzy:
        for c in candidatas:
            a, _ = texto.norm(c)
            if not a:
                continue
            sim = fuzz.partial_ratio(t, a)
            if sim >= limiares.evidencia_similaridade:
                if campo.tipo == "numerico" and valor_norm is not None:
                    n = parse_numero(valor_norm)
                    if n is not None and not numero_no_trecho(n, texto.paginas[c][0],
                                                              campo.tolerancia_relativa):
                        return Evidencia(0.0, f"trecho parecido na página {c}, mas o número "
                                         f"{valor_norm} não aparece nela", c, trecho)
                e, detalhe, pagina_ok = 0.5, f"similaridade {sim:.0f} na página {c}", c
                break
    if e == 0:
        for pg in texto.paginas:
            if pg in candidatas:
                continue
            if _contem(t, *texto.norm(pg)):
                e, detalhe, pagina_ok = 0.5, f"exato em outra página ({pg})", pg
                break
    if e == 0:
        frag = [normalizar(f) for f in re.split(r"\n+|\s*(?:\.\.\.|…)\s*", trecho)]
        frag = [f for f in frag if len(f) >= 12]
        if len(frag) >= 2:
            alvo = " ".join(" ".join(texto.norm(c)) for c in candidatas) + " " + unid_cit
            achados = [f for f in frag if f in alvo]
            if len(achados) == len(frag):
                e, detalhe = 1.0, f"exato em {len(frag)} fragmentos contíguos citados"
            elif sum(len(f) for f in achados) >= 0.5 * sum(len(f) for f in frag):
                e, detalhe = 0.5, f"{len(achados)} de {len(frag)} fragmentos encontrados"
    if e == 0:
        if texto._oculto_norm and t in texto._oculto_norm:
            return Evidencia(0.0, "trecho existe só em texto oculto do PDF", p, trecho)
        return Evidencia(0.0, "trecho não encontrado no texto do artigo", p, trecho)

    if campo.tipo == "numerico" and valor_norm is not None:
        n = parse_numero(valor_norm)
        apoio = trecho + " " + " ".join(texto.unidades[u][1] for u in uids_validos)
        if n is not None and not numero_no_trecho(n, apoio, campo.tolerancia_relativa):
            return Evidencia(0.0, f"o número {valor_norm} não aparece no trecho citado", pagina_ok,
                             trecho)
    return Evidencia(e, detalhe, pagina_ok, trecho)
