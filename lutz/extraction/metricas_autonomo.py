"""Per-field reliability metrics of the autonomous mode (consistency, not accuracy).

* Krippendorff's alpha among E1, E2, E3 (nominal / ordinal / interval by field type) with a
  95% bootstrap interval over articles. "Not reported" is a category in nominal fields and
  missing in ordinal and numeric fields; a failed extractor is missing.
* % unanimous cells (with Wilson interval) — replaces alpha for free-text fields.
* % of cells at each level, % with exact evidence, % not reported (alert above the threshold:
  possible retrieval or reading failure, not true absence).
"""

from __future__ import annotations

import math

import numpy as np

from lutz.config.settings import Settings
from lutz.core import codebook as cbk
from lutz.core import metricas as M
from lutz.core.db import agora, jload, transacao, um
from lutz.extraction.consolidacao import VAZIO


def _valores_por_extrator(con, execucao_id: int, campo_chave: str, extratores) -> tuple[list, list[list]]:
    artigos = [r[0] for r in con.execute(
        "SELECT DISTINCT artigo_id FROM celula WHERE execucao_id=? AND campo_chave=? ORDER BY artigo_id",
        (execucao_id, campo_chave))]
    mat = []
    for rot in extratores:
        linha = []
        for a in artigos:
            r = con.execute(
                """SELECT b.status, b.valor_normalizado, b.nao_reportado, b.regras_ok FROM extracao_bruta b
                   JOIN celula c ON c.id=b.celula_id
                   WHERE c.execucao_id=? AND c.artigo_id=? AND c.campo_chave=? AND b.rotulo=?""",
                (execucao_id, a, campo_chave, rot)).fetchone()
            if r is None or r["status"] != "ok" or not r["regras_ok"]:
                linha.append(None)
            elif r["nao_reportado"]:
                linha.append(VAZIO)
            else:
                linha.append(r["valor_normalizado"])
        mat.append(linha)
    return artigos, mat


def alfa_campo(campo: cbk.Campo, mat: list[list]) -> tuple[float, str]:
    if campo.tipo == "categorico":
        return M.alfa_krippendorff(mat, "nominal"), "nominal"
    if campo.tipo == "ordinal":
        dados = [[x if x != VAZIO else None for x in linha] for linha in mat]
        return M.alfa_krippendorff(dados, "ordinal", ordem=campo.valores), "ordinal"
    if campo.tipo == "numerico":
        dados = [[float(x) if x not in (None, VAZIO) else None for x in linha] for linha in mat]
        return M.alfa_krippendorff(dados, "interval"), "intervalar"
    return math.nan, "-"


def calcular(con, execucao_id: int, settings: Settings) -> list[dict]:
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,))
    cb = cbk.carregar(con, um(con, "SELECT versao FROM codebook WHERE id=?", (ex["codebook_id"],))["versao"])
    extratores = [r[0] for r in con.execute(
        "SELECT rotulo FROM extrator WHERE execucao_id=? AND papel='extrator' ORDER BY rotulo", (execucao_id,))]
    reps = settings.metricas.bootstrap_repeticoes
    semente = settings.sementes.bootstrap
    linhas: list[dict] = []

    def add(campo, nome, valor, ic=(None, None), n=None, nota=""):
        def limpo(x):
            return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)

        linhas.append({"campo_chave": campo, "nome": nome, "valor": limpo(valor), "ic_inf": limpo(ic[0]),
                       "ic_sup": limpo(ic[1]), "n": n, "nota": nota})

    for nome in jload(ex["campos"]):
        campo = cb.campo(nome)
        artigos, mat = _valores_por_extrator(con, execucao_id, nome, extratores)
        n = len(artigos)
        alfa, nivel_med = alfa_campo(campo, mat)
        if campo.tipo != "texto":
            arr = [np.array(linha, dtype=object) for linha in mat]

            def f(idx, campo=campo, arr=arr):
                return alfa_campo(campo, [list(a[idx]) for a in arr])[0]

            ic = M.bootstrap_ic(f, n, semente, reps) if not math.isnan(alfa) else (None, None)
            nota = f"nível {nivel_med}"
            if not math.isnan(alfa):
                if alfa < settings.limiares.alfa_provisorio:
                    nota += "; abaixo de 0,667: reescrever o campo"
                elif alfa < settings.limiares.alfa_confiavel:
                    nota += "; entre 0,667 e 0,800: conclusões provisórias"
            else:
                nota += "; indefinido (sem variação ou dados insuficientes)"
            add(nome, "alfa", alfa, ic, n, nota)
        cel = [dict(r) for r in con.execute(
            "SELECT * FROM celula WHERE execucao_id=? AND campo_chave=?", (execucao_id, nome))]
        tot = len(cel) or 1
        unan = sum(1 for c in cel if c["a"] is not None and c["a"] >= 0.999)
        p, lo, hi = M.wilson(unan, len(cel))
        add(nome, "unanimes", p, (lo, hi), len(cel))
        for niv in ("alta", "media", "baixa"):
            add(nome, f"pct_{niv}", sum(1 for c in cel if c["nivel"] == niv) / tot, n=len(cel))
        com_valor = [c for c in cel if not c["nao_reportado"] and c["valor_final"] is not None]
        add(nome, "pct_evidencia_exata",
            (sum(1 for c in com_valor if (c["e"] or 0) >= 1) / len(com_valor)) if com_valor else None,
            n=len(com_valor))
        pct_nr = sum(1 for c in cel if c["nao_reportado"]) / tot
        add(nome, "pct_nao_reportado", pct_nr, n=len(cel),
            nota="alerta: possível falha de leitura ou recuperação" if pct_nr > settings.limiares.nao_reportado_alerta else "")
        add(nome, "pct_empate", sum(1 for c in cel if c["valor_final"] is None and not c["nao_reportado"]
                                     and c["nivel"] == "baixa" and c["escore"] is None) / tot, n=len(cel))

    todas = [dict(r) for r in con.execute("SELECT * FROM celula WHERE execucao_id=?", (execucao_id,))]
    tot = len(todas) or 1
    for niv in ("alta", "media", "baixa"):
        add(None, f"pct_{niv}", sum(1 for c in todas if c["nivel"] == niv) / tot, n=len(todas))
    with transacao(con):
        con.execute("DELETE FROM metrica WHERE execucao_id=? AND escopo='autonomo'", (execucao_id,))
        con.executemany(
            """INSERT INTO metrica (execucao_id, campo_chave, escopo, nome, valor, ic_inf, ic_sup, n, nota,
               criado_em) VALUES (?,?,'autonomo',?,?,?,?,?,?,?)""",
            [(execucao_id, m["campo_chave"], m["nome"], m["valor"], m["ic_inf"], m["ic_sup"], m["n"],
              m["nota"], agora()) for m in linhas],
        )
    return linhas


def metricas(con, execucao_id: int, escopo: str = "autonomo") -> dict[str | None, dict[str, dict]]:
    out: dict[str | None, dict[str, dict]] = {}
    for r in con.execute("SELECT * FROM metrica WHERE execucao_id=? AND escopo=?", (execucao_id, escopo)):
        out.setdefault(r["campo_chave"], {})[r["nome"]] = dict(r)
    return out
