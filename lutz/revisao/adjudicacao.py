"""Adjudication: the researcher's final decision on doubtful cells.

Queue (spec §8, brief M6/M14): every Baixa cell; Média cells of fields that the pilot sent to
review; cells sent manually from Results. Ordered by level (Baixa first), then score
(ties without a score first), then field and article.

Every decision stores the previous value, the decided value, the justification and the date.
The level of an adjudicated cell is kept as computed (the report uses original levels); the
cell is flagged ``origem = adjudicacao``.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from lutz.core import codebook as cbk
from lutz.core.db import agora, jload, transacao, um
from lutz.core.errors import EstadoInvalido, LutzError
from lutz.extraction.regras import normalizar_valor

SIM = {"sim", "s", "yes", "y", "true", "1", "x", "verdadeiro"}


def campos_revisar_media(con, execucao_id: int) -> set[str]:
    """Fields whose latest pilot decision asks to review Média cells too."""
    out = set()
    for r in con.execute(
        """SELECT campo_chave, decisao FROM decisao_campo d WHERE id IN
           (SELECT max(id) FROM decisao_campo GROUP BY campo_chave)"""):
        if r["decisao"] in ("revisar_media_baixa", "reescrever"):
            out.add(r["campo_chave"])
    return out


def _motivo_fila(cel: dict, revisar_media: set[str], manuais: set[int]) -> str | None:
    if cel["id"] in manuais:
        return "manual"
    if cel["nivel"] == "baixa":
        return "baixa"
    if cel["nivel"] == "media" and cel["campo_chave"] in revisar_media:
        return "media"
    return None


def fila(con, execucao_id: int, incluir_decididas: bool = False, ocultos: set[int] | None = None) -> list[dict]:
    revisar = campos_revisar_media(con, execucao_id)
    manuais = {r[0] for r in con.execute(
        "SELECT celula_id FROM envio_manual e JOIN celula c ON c.id=e.celula_id WHERE c.execucao_id=?",
        (execucao_id,))}
    out = []
    for r in con.execute(
        """SELECT c.*, a.chave, a.titulo, cp.rotulo campo_rotulo, cp.tipo campo_tipo
           FROM celula c JOIN artigo a ON a.id=c.artigo_id JOIN campo cp ON cp.id=c.campo_id
           WHERE c.execucao_id=? AND c.estado IN ('consolidada','adjudicada')""", (execucao_id,)):
        cel = dict(r)
        if ocultos and cel["artigo_id"] in ocultos:
            continue
        motivo = _motivo_fila(cel, revisar, manuais)
        if motivo is None and cel["estado"] == "adjudicada" and incluir_decididas:
            r = con.execute("SELECT motivo FROM adjudicacao WHERE celula_id=? ORDER BY id LIMIT 1",
                            (cel["id"],)).fetchone()
            motivo = r[0] if r else None
        if motivo is None:
            continue
        if cel["estado"] == "adjudicada" and not incluir_decididas:
            continue
        cel["motivo_fila"] = motivo
        cel["motivos"] = jload(cel["motivos"], [])
        out.append(cel)
    ordem_nivel = {"baixa": 0, "media": 1, "alta": 2}
    out.sort(key=lambda c: (ordem_nivel.get(c["nivel"], 3), c["escore"] is not None, c["escore"] or 0,
                            c["campo_chave"], c["chave"]))
    return out


def brutas(con, celula_id: int) -> list[dict]:
    return [dict(r) | {"unidades": jload(r["unidades"], [])} for r in con.execute(
        "SELECT * FROM extracao_bruta WHERE celula_id=? ORDER BY rotulo", (celula_id,))]


def _campo_da_celula(con, cel: dict) -> cbk.Campo:
    r = um(con, "SELECT definicao FROM campo WHERE id=?", (cel["campo_id"],))
    return cbk.Campo.model_validate(jload(r["definicao"]))


def decidir(con, celula_id: int, *, valor: str | None, nao_reportado: bool, justificativa: str = "",
            motivo: str | None = None) -> dict:
    cel = um(con, "SELECT * FROM celula WHERE id=?", (celula_id,))
    if cel is None:
        raise EstadoInvalido(f"Célula {celula_id} não existe.")
    if cel["estado"] not in ("consolidada", "adjudicada"):
        raise EstadoInvalido("A célula ainda não foi consolidada.")
    campo = _campo_da_celula(con, cel)
    norm, erro = normalizar_valor(campo, valor, nao_reportado)
    if erro:
        raise LutzError(f"Valor inválido para {campo.nome}: {erro}")
    if motivo is None:
        manual = con.execute("SELECT 1 FROM envio_manual WHERE celula_id=?", (celula_id,)).fetchone()
        motivo = "manual" if manual else ("baixa" if cel["nivel"] == "baixa" else "media")
    alterou = int(norm != cel["valor_final"] or bool(nao_reportado) != bool(cel["nao_reportado"]))
    with transacao(con):
        con.execute(
            """INSERT INTO adjudicacao (celula_id, motivo, valor_anterior, nao_reportado_anterior,
               valor_decidido, nao_reportado, alterou, justificativa, decidido_em) VALUES (?,?,?,?,?,?,?,?,?)""",
            (celula_id, motivo, cel["valor_final"], cel["nao_reportado"], norm, int(nao_reportado), alterou,
             justificativa, agora()),
        )
        con.execute("UPDATE celula SET valor_final=?, nao_reportado=?, origem='adjudicacao', estado='adjudicada', "
                    "atualizada_em=? WHERE id=?", (norm, int(nao_reportado), agora(), celula_id))
    return um(con, "SELECT * FROM celula WHERE id=?", (celula_id,))


def enviar_manual(con, celula_id: int, nota: str = "") -> None:
    con.execute("INSERT OR REPLACE INTO envio_manual (celula_id, nota, criado_em) VALUES (?,?,?)",
                (celula_id, nota, agora()))


COLUNAS = ["celula_id", "artigo", "campo", "nivel", "escore", "motivo_fila", "motivos", "valor_lutz",
           "nao_reportado_lutz", "E1", "E2", "E3", "trecho", "pagina", "valor_decidido",
           "nao_reportado_decidido", "justificativa"]

INSTRUCOES_CSV = (
    "Preencha valor_decidido (use '=' para aceitar o valor do Lutz) ou nao_reportado_decidido=sim, "
    "e uma justificativa. Linhas com as duas colunas vazias são ignoradas."
)


def _resumo_bruta(b: dict) -> str:
    if b["status"] != "ok":
        return f"[falha: {b['erro']}]"
    if b["nao_reportado"]:
        return "não reportado"
    return f"{b['valor']} (e={b['e']:g})" if b["e"] is not None else str(b["valor"])


def exportar_csv(con, execucao_id: int, destino: Path, sep: str = ",", ocultos=None) -> int:
    linhas = fila(con, execucao_id, ocultos=ocultos)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow(COLUNAS)
        for c in linhas:
            bs = {b["rotulo"]: _resumo_bruta(b) for b in brutas(con, c["id"])}
            w.writerow([c["id"], c["chave"], c["campo_chave"], c["nivel"],
                        "" if c["escore"] is None else f"{c['escore']:.3f}", c["motivo_fila"],
                        "; ".join(c["motivos"]), c["valor_final"] or "", "sim" if c["nao_reportado"] else "",
                        bs.get("E1", ""), bs.get("E2", ""), bs.get("E3", ""), c["trecho"] or "",
                        c["pagina"] or "", "", "", ""])
    return len(linhas)


def _ler_csv(origem: Path | str | bytes) -> list[dict]:
    if isinstance(origem, bytes):
        texto = origem.decode("utf-8-sig")
    else:
        texto = Path(origem).read_text(encoding="utf-8-sig")
    try:
        dialeto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=",;\t")
    except (csv.Error, IndexError):
        dialeto = csv.excel
    return list(csv.DictReader(io.StringIO(texto), dialect=dialeto))


def importar_csv(con, origem: Path | str | bytes) -> dict:
    aplicadas, ignoradas, erros = 0, 0, []
    for i, linha in enumerate(_ler_csv(origem), start=2):
        valor = (linha.get("valor_decidido") or "").strip()
        nr = (linha.get("nao_reportado_decidido") or "").strip().lower() in SIM
        if not valor and not nr:
            ignoradas += 1
            continue
        try:
            cid = int(linha["celula_id"])
            cel = um(con, "SELECT * FROM celula WHERE id=?", (cid,))
            if cel is None:
                raise LutzError(f"célula {cid} não existe")
            if valor == "=":
                valor, nr = cel["valor_final"], bool(cel["nao_reportado"])
                if valor is None and not nr:
                    raise LutzError("não há valor do Lutz para aceitar (empate)")
            decidir(con, cid, valor=None if nr else valor, nao_reportado=nr,
                    justificativa=(linha.get("justificativa") or "").strip())
            aplicadas += 1
        except (LutzError, KeyError, ValueError) as exc:
            erros.append({"linha": i, "erro": str(exc)})
    return {"aplicadas": aplicadas, "ignoradas": ignoradas, "erros": erros}


def estatisticas(con, execucao_id: int) -> dict:
    """Cells sent and changed, by field and by level (report part 5)."""
    enviadas = fila(con, execucao_id, incluir_decididas=True)
    por: dict[tuple[str, str], dict] = {}
    for c in enviadas:
        d = por.setdefault((c["campo_chave"], c["nivel"]), {"enviadas": 0, "decididas": 0, "alteradas": 0})
        d["enviadas"] += 1
        ult = con.execute("SELECT alterou FROM adjudicacao WHERE celula_id=? ORDER BY id DESC LIMIT 1",
                          (c["id"],)).fetchone()
        if ult is not None:
            d["decididas"] += 1
            d["alteradas"] += ult[0]
    tot = {"enviadas": len(enviadas), "decididas": sum(d["decididas"] for d in por.values()),
           "alteradas": sum(d["alteradas"] for d in por.values())}
    por_nivel: dict[str, dict] = {}
    for (_, niv), d in por.items():
        x = por_nivel.setdefault(niv, {"enviadas": 0, "decididas": 0, "alteradas": 0})
        for k in x:
            x[k] += d[k]
    return {"total": tot, "por_nivel": por_nivel,
            "por_campo_nivel": [{"campo": k[0], "nivel": k[1], **v} for k, v in sorted(por.items())]}


def detalhe_celula(con, celula_id: int) -> dict:
    cel = um(con, """SELECT c.*, a.chave, a.titulo, a.caminho_pdf, cp.rotulo campo_rotulo, cp.tipo campo_tipo,
                     cp.definicao FROM celula c JOIN artigo a ON a.id=c.artigo_id JOIN campo cp ON cp.id=c.campo_id
                     WHERE c.id=?""", (celula_id,))
    if cel is None:
        raise EstadoInvalido(f"Célula {celula_id} não existe.")
    cel["motivos"] = jload(cel["motivos"], [])
    cel["unidades"] = jload(cel["unidades"], [])
    cel["definicao"] = jload(cel["definicao"])
    cel["v_justificativa"] = jload(cel["v_justificativa"], {}) if cel["v_justificativa"] else {}
    cel["brutas"] = brutas(con, celula_id)
    cel["adjudicacoes"] = [dict(r) for r in con.execute(
        "SELECT * FROM adjudicacao WHERE celula_id=? ORDER BY id", (celula_id,))]
    cel["enviada_manual"] = bool(con.execute("SELECT 1 FROM envio_manual WHERE celula_id=?",
                                             (celula_id,)).fetchone())
    return json.loads(json.dumps(cel, default=str))
