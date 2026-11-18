"""What each extractor reads: the article as addressable units, with physical page markers.

Rule (brief, decision 3 and M4): the full text (without references and acknowledgements) is
always sent when it fits in the model
window (``contexto.fracao_janela`` of the window, minus the answer budget). When it does not
fit, only the units of the sections declared by the fields of the group are sent (plus the
abstract). When even that does not fit, the cells fail with reason ``excede_contexto``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from lutz.config.settings import ModeloPapel, Settings
from lutz.core.codebook import Campo
from lutz.core.ingestao import secao_canonica
from lutz.core.texto import estimar_tokens

MAX_CAMPOS_POR_GRUPO = 12
# Never sent to extractors: they hold no study data and take a large share of the text.
SECOES_EXCLUIDAS = {"referencias", "agradecimentos"}


@dataclass
class Unidade:
    uid: str
    pagina: int
    ordem: int
    tipo: str
    secao: str
    texto: str


@dataclass
class Contexto:
    texto: str
    estrategia: str  # completo | secoes
    tokens: int


def carregar_unidades(con: sqlite3.Connection, artigo_id: int) -> list[Unidade]:
    return [
        Unidade(r["uid"], r["pagina"], r["ordem"], r["tipo"], r["secao"], r["texto"])
        for r in con.execute(
            "SELECT * FROM unidade WHERE artigo_id=? ORDER BY pagina, ordem", (artigo_id,)
        )
    ]


def rotulos_paginas(con: sqlite3.Connection, artigo_id: int) -> dict[int, str]:
    return {r[0]: r[1] for r in con.execute(
        "SELECT numero, rotulo FROM pagina WHERE artigo_id=?", (artigo_id,))}


def renderizar(unidades: list[Unidade], rotulos: dict[int, str]) -> str:
    partes: list[str] = []
    pagina_atual = None
    secao_atual = None
    for u in unidades:
        if u.pagina != pagina_atual:
            rot = rotulos.get(u.pagina) or ""
            extra = f" | printed page {rot}" if rot and rot != str(u.pagina) else ""
            partes.append(f"\n<<p.{u.pagina}{extra}>>")
            pagina_atual = u.pagina
        if u.secao and u.secao != secao_atual:
            secao_atual = u.secao
        partes.append(f"[{u.uid}] {u.texto}")
    return "\n".join(partes).strip()


def secoes_canonicas(campo_secoes: list[str]) -> set[str]:
    out = set()
    for s in campo_secoes:
        c = secao_canonica(s) or s.strip().lower()
        out.add(c)
    return out


def grupos(campos: list[Campo]) -> list[tuple[str, list[Campo]]]:
    """Group fields that share the same sections, at most MAX_CAMPOS_POR_GRUPO per call."""
    por_chave: dict[tuple, list[Campo]] = {}
    for c in campos:
        chave = tuple(sorted(secoes_canonicas(c.secoes)))
        por_chave.setdefault(chave, []).append(c)
    out = []
    n = 0
    for chave in sorted(por_chave, key=lambda k: (len(k) == 0, k)):
        lista = por_chave[chave]
        for i in range(0, len(lista), MAX_CAMPOS_POR_GRUPO):
            n += 1
            out.append((f"g{n}", lista[i : i + MAX_CAMPOS_POR_GRUPO]))
    return out


def orcamento_tokens(cfg: ModeloPapel, settings: Settings) -> int:
    janela = cfg.janela_tokens or settings.contexto.janela_tokens_padrao
    return int(janela * settings.contexto.fracao_janela) - cfg.max_tokens


def montar(
    unidades: list[Unidade], rotulos: dict[int, str], campos: list[Campo], cfg: ModeloPapel,
    settings: Settings, overhead_tokens: int,
) -> Contexto | None:
    limite = orcamento_tokens(cfg, settings) - overhead_tokens
    unidades = [u for u in unidades if u.secao not in SECOES_EXCLUIDAS]
    completo = renderizar(unidades, rotulos)
    tok = estimar_tokens(completo)
    if tok <= limite:
        return Contexto(completo, "completo", tok)
    alvo: set[str] = set()
    for c in campos:
        alvo |= secoes_canonicas(c.secoes)
    if not alvo:
        return None
    alvo.add("resumo")
    sel = [u for u in unidades if u.secao in alvo]
    if not sel:
        return None
    texto = renderizar(sel, rotulos)
    tok = estimar_tokens(texto)
    if tok <= limite:
        return Contexto(texto, "secoes", tok)
    return None


def janela_unidades(unidades: list[Unidade], uids: list[str], raio: int = 2) -> str:
    """Text of the cited units plus *raio* neighbours on each side (verifier window)."""
    pos = {u.uid: i for i, u in enumerate(unidades)}
    idx = sorted(pos[x] for x in uids if x in pos)
    if not idx:
        return ""
    ini, fim = max(0, idx[0] - raio), min(len(unidades), idx[-1] + raio + 1)
    sel = unidades[ini:fim]
    # Table rows: include the other rows of the same table (they hold the column headers).
    tabelas = {u.uid.split(".r")[0] for u in (unidades[i] for i in idx) if u.tipo == "linha_tabela"}
    if tabelas:
        extra = [u for u in unidades if u.tipo == "linha_tabela" and u.uid.split(".r")[0] in tabelas]
        vistos = {u.uid for u in sel}
        sel = sel + [u for u in extra if u.uid not in vistos]
    return "\n".join(f"[{u.uid}] {u.texto}" for u in sel)
