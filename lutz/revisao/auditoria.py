"""Audit of Alta cells (brief decision 10: mandatory, n computed).

A random sample of Alta cells, drawn with the audit seed, is checked by the researcher. The
sample size is the smallest n whose 95% Wilson interval has the target half-width at the
expected accuracy (``auditoria.meia_largura_alvo``, ``auditoria.p_esperado``), capped by the
number of Alta cells. The hit rate is the only human-anchored number available when there is
no pilot; the report says when the audit was not done.

A cell judged wrong is adjudicated with reason ``auditoria``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from lutz.config.settings import Settings
from lutz.core import metricas as M
from lutz.core.db import agora, transacao, um
from lutz.core.errors import EstadoInvalido, LutzError
from lutz.revisao.adjudicacao import SIM, _ler_csv, decidir


def criar(con, execucao_id: int, settings: Settings, n: int | None = None,
          ocultos: set[int] | None = None) -> dict:
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,))
    if ex is None or ex["status"] != "concluida":
        raise EstadoInvalido("A auditoria exige uma execução concluída.")
    existente = um(con, "SELECT * FROM auditoria WHERE execucao_id=? ORDER BY id DESC LIMIT 1", (execucao_id,))
    if existente:
        return existente
    altas = [r[0] for r in con.execute(
        "SELECT id FROM celula WHERE execucao_id=? AND nivel='alta' ORDER BY id", (execucao_id,))
        if not ocultos or con.execute("SELECT artigo_id FROM celula WHERE id=?", (r[0],)).fetchone()[0] not in ocultos]
    if not altas:
        raise EstadoInvalido("Não há células Alta para auditar.")
    alvo = n or M.n_para_meia_largura(settings.auditoria.meia_largura_alvo, settings.auditoria.p_esperado)
    tam = min(alvo, len(altas))
    rng = np.random.default_rng(settings.sementes.auditoria)
    escolha = sorted(rng.choice(altas, size=tam, replace=False).tolist())
    with transacao(con):
        cur = con.execute(
            """INSERT INTO auditoria (execucao_id, semente, meia_largura_alvo, n_alta, n_amostra, criado_em)
               VALUES (?,?,?,?,?,?)""",
            (execucao_id, settings.sementes.auditoria, settings.auditoria.meia_largura_alvo, len(altas), tam, agora()))
        aid = cur.lastrowid
        con.executemany("INSERT INTO auditoria_item (auditoria_id, celula_id) VALUES (?,?)",
                        [(aid, c) for c in escolha])
    return um(con, "SELECT * FROM auditoria WHERE id=?", (aid,))


def atual(con, execucao_id: int) -> dict | None:
    return um(con, "SELECT * FROM auditoria WHERE execucao_id=? ORDER BY id DESC LIMIT 1", (execucao_id,))


def itens(con, auditoria_id: int) -> list[dict]:
    return [dict(r) for r in con.execute(
        """SELECT i.*, c.valor_final, c.nao_reportado, c.trecho, c.pagina, c.campo_chave, a.chave
           FROM auditoria_item i JOIN celula c ON c.id=i.celula_id JOIN artigo a ON a.id=c.artigo_id
           WHERE i.auditoria_id=? ORDER BY c.campo_chave, a.chave""", (auditoria_id,))]


def registrar(con, item_id: int, correto: bool, valor_correto: str | None = None,
              nao_reportado_correto: bool = False, nota: str = "") -> None:
    it = um(con, "SELECT * FROM auditoria_item WHERE id=?", (item_id,))
    if it is None:
        raise EstadoInvalido(f"Item de auditoria {item_id} não existe.")
    if not correto and not valor_correto and not nao_reportado_correto:
        raise LutzError("Informe o valor correto (ou não reportado) para uma célula errada.")
    con.execute(
        """UPDATE auditoria_item SET correto=?, valor_correto=?, nao_reportado_correto=?, nota=?, conferido_em=?
           WHERE id=?""",
        (int(correto), valor_correto, int(nao_reportado_correto), nota, agora(), item_id))
    if not correto:
        decidir(con, it["celula_id"], valor=None if nao_reportado_correto else valor_correto,
                nao_reportado=nao_reportado_correto, justificativa=f"auditoria: {nota}".strip(),
                motivo="auditoria")


def resultado(con, execucao_id: int) -> dict | None:
    a = atual(con, execucao_id)
    if a is None:
        return None
    r = con.execute("SELECT count(*), sum(correto) FROM auditoria_item WHERE auditoria_id=? AND correto IS NOT NULL",
                    (a["id"],)).fetchone()
    n, acertos = r[0], r[1] or 0
    p, lo, hi = M.wilson(acertos, n)
    return {"auditoria_id": a["id"], "n_amostra": a["n_amostra"], "n_alta": a["n_alta"], "conferidas": n,
            "acertos": acertos, "taxa": p if n else None, "ic_inf": lo if n else None, "ic_sup": hi if n else None,
            "completa": n == a["n_amostra"], "semente": a["semente"], "meia_largura_alvo": a["meia_largura_alvo"]}


COLUNAS = ["item_id", "artigo", "campo", "valor_lutz", "nao_reportado_lutz", "trecho", "pagina", "correto",
           "valor_correto", "nao_reportado_correto", "nota"]


def exportar_csv(con, auditoria_id: int, destino: Path, sep: str = ",") -> int:
    linhas = itens(con, auditoria_id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow(COLUNAS)
        for i in linhas:
            w.writerow([i["id"], i["chave"], i["campo_chave"], i["valor_final"] or "",
                        "sim" if i["nao_reportado"] else "", i["trecho"] or "", i["pagina"] or "",
                        "" if i["correto"] is None else ("sim" if i["correto"] else "nao"),
                        i["valor_correto"] or "", "sim" if i["nao_reportado_correto"] else "",
                        i["nota"] or ""])
    return len(linhas)


def importar_csv(con, origem) -> dict:
    aplicadas, erros = 0, []
    for n, linha in enumerate(_ler_csv(origem), start=2):
        c = (linha.get("correto") or "").strip().lower()
        if not c:
            continue
        try:
            anterior = um(con, "SELECT correto FROM auditoria_item WHERE id=?", (int(linha["item_id"]),))
            if anterior is not None and anterior["correto"] is not None and bool(anterior["correto"]) == (c in SIM):
                continue  # already recorded with the same verdict
            registrar(con, int(linha["item_id"]), correto=c in SIM,
                      valor_correto=(linha.get("valor_correto") or "").strip() or None,
                      nao_reportado_correto=(linha.get("nao_reportado_correto") or "").strip().lower() in SIM,
                      nota=(linha.get("nota") or "").strip())
            aplicadas += 1
        except (LutzError, KeyError, ValueError) as exc:
            erros.append({"linha": n, "erro": str(exc)})
    return {"aplicadas": aplicadas, "erros": erros}
