"""Calibrated mode: a blind pilot with one or two human raters.

Flow::

    plan (pre-registered, hashed) -> sample (seeded, stratified, reserve block, quick-test
    articles excluded) -> blank sheets per rater -> import -> consensus (two raters) ->
    adjustment rounds (free, each codebook change is a new frozen version) -> validation
    (one run, frozen codebook) -> compare -> per-field decision + level calibration

Blinding: Lutz answers for pilot articles stay hidden in results, adjudication and exports
until every declared rater sheet has been imported (``piloto.cegamento_aberto``).
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz

from lutz.config.settings import Settings, hash_obj
from lutz.core import codebook as cbk
from lutz.core import metricas as M
from lutz.core.db import agora, jdump, jload, transacao, um
from lutz.core.errors import EstadoInvalido, LutzError
from lutz.core.texto import iguais_numericos, normalizar, parse_numero
from lutz.extraction.regras import normalizar_valor
from lutz.revisao.adjudicacao import SIM, _ler_csv

VAZIO = "∅"
SEM_VALOR = "(sem valor)"


# ── plan and sample ──────────────────────────────────────────────────────────


def atual(con) -> dict | None:
    return um(con, "SELECT * FROM piloto ORDER BY id DESC LIMIT 1")


def planejar(con, settings: Settings, *, n_ajuste: int, n_validacao: int, n_reserva: int = 0,
             estratos: str = "", avaliadores: list[str] | None = None) -> dict:
    avaliadores = avaliadores or ["A", "B"]
    if not 1 <= len(avaliadores) <= 2:
        raise LutzError("O piloto aceita um ou dois avaliadores humanos.")
    if estratos not in ("", "ano", "revista"):
        raise LutzError("Estratos aceitos: ano, revista (ou nenhum).")
    if n_ajuste < 0 or n_validacao < 5:
        raise LutzError("O conjunto de validação precisa de pelo menos 5 artigos.")
    cb_row = cbk.ultimo_congelado(con) or cbk.linha_codebook(con)
    if cb_row is None:
        raise EstadoInvalido("Crie o codebook antes de planejar o piloto.")
    n_corpus = con.execute("SELECT count(*) FROM artigo WHERE status='pronto'").fetchone()[0]
    lim = settings.limiares
    plano = {
        "n_ajuste": n_ajuste, "n_validacao": n_validacao, "n_reserva": n_reserva,
        "estratos": estratos, "semente": settings.sementes.piloto, "avaliadores": avaliadores,
        "codebook_versao_planilha": cb_row["versao"], "codebook_hash_planilha": cb_row["hash"],
        "regra_decisao": {"alto": lim.decisao_alto, "ic_inferior": lim.decisao_ic_inferior,
                          "medio": lim.decisao_medio, "texto_alto": lim.decisao_texto_alto,
                          "texto_medio": lim.decisao_texto_medio},
        "calibracao_alta_minima": lim.calibracao_alta_minima,
        "bootstrap": {"repeticoes": settings.metricas.bootstrap_repeticoes, "semente": settings.sementes.bootstrap},
        "corpus_no_planejamento": n_corpus,
        "criado_em": agora(),
    }
    h = hash_obj(plano)[:16]
    with transacao(con):
        cur = con.execute(
            """INSERT INTO piloto (n_total, n_ajuste, n_validacao, n_reserva, estratos, semente, avaliadores,
               plano, hash_plano, codebook_id, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (n_ajuste + n_validacao + n_reserva, n_ajuste, n_validacao, n_reserva, estratos,
             settings.sementes.piloto, jdump(avaliadores), jdump(plano), h, cb_row["id"], agora()))
        for a in avaliadores:
            con.execute("INSERT OR IGNORE INTO avaliador (nome, tipo) VALUES (?, 'humano')", (a,))
        con.execute("INSERT OR IGNORE INTO avaliador (nome, tipo) VALUES ('consenso', 'consenso')")
    return um(con, "SELECT * FROM piloto WHERE id=?", (cur.lastrowid,))


def avisos_plano(n_corpus: int, n_validacao: int) -> list[str]:
    out = []
    if n_corpus < 60:
        out.append(
            f"O corpus tem {n_corpus} artigos. Abaixo de ~60, extrair tudo em dupla pode valer mais "
            "que um piloto."
        )
    t = {r["n"]: r for r in M.tabela_tamanho_piloto(tamanhos=(n_validacao,))}
    meia = t[n_validacao]["meia_largura"]
    if meia > 0.2:
        out.append(f"Com {n_validacao} artigos de validação, o IC95% do kappa terá cerca de ±{meia:.2f}.")
    return out


def _hamilton(contagens: dict[str, int], n: int) -> dict[str, int]:
    total = sum(contagens.values())
    cotas = {k: n * v / total for k, v in contagens.items()}
    base = {k: min(contagens[k], int(math.floor(q))) for k, q in cotas.items()}
    resto = n - sum(base.values())
    for k in sorted(cotas, key=lambda k: (-(cotas[k] - math.floor(cotas[k])), k)):
        if resto <= 0:
            break
        if base[k] < contagens[k]:
            base[k] += 1
            resto -= 1
    return base


def sortear(con, piloto_id: int) -> dict:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    if p is None:
        raise EstadoInvalido("Piloto não encontrado.")
    if p["sorteado_em"]:
        raise EstadoInvalido("Este piloto já foi sorteado; o sorteio não se repete.")
    excluidos = {r[0] for r in con.execute("SELECT DISTINCT artigo_id FROM teste_rapido")}
    artigos = [dict(r) for r in con.execute("SELECT id, ano, revista FROM artigo WHERE status='pronto' ORDER BY id")]
    elegiveis = [a for a in artigos if a["id"] not in excluidos]
    n = p["n_total"]
    if len(elegiveis) < n:
        raise EstadoInvalido(
            f"Há {len(elegiveis)} artigos elegíveis (excluídos {len(excluidos)} usados no teste rápido) "
            f"e o piloto pede {n}."
        )
    rng = np.random.default_rng(p["semente"])
    if p["estratos"]:
        def estrato(a):
            v = a.get(p["estratos"])
            return str(v) if v not in (None, "") else "desconhecido"
        grupos: dict[str, list[dict]] = {}
        for a in elegiveis:
            grupos.setdefault(estrato(a), []).append(a)
        cotas = _hamilton({k: len(v) for k, v in grupos.items()}, n)
        escolhidos = []
        for k in sorted(grupos):
            ids = [a["id"] for a in grupos[k]]
            escolhidos += [(int(i), k) for i in rng.choice(ids, size=cotas[k], replace=False)]
    else:
        ids = [a["id"] for a in elegiveis]
        escolhidos = [(int(i), "") for i in rng.choice(ids, size=n, replace=False)]
    ordem = rng.permutation(len(escolhidos))
    escolhidos = [escolhidos[i] for i in ordem]
    conjuntos = (["ajuste"] * p["n_ajuste"] + ["validacao"] * p["n_validacao"] + ["reserva"] * p["n_reserva"])
    with transacao(con):
        con.executemany(
            "INSERT INTO piloto_amostra (piloto_id, artigo_id, conjunto, estrato) VALUES (?,?,?,?)",
            [(piloto_id, a, c, e) for (a, e), c in zip(escolhidos, conjuntos, strict=True)])
        con.execute("UPDATE piloto SET sorteado_em=? WHERE id=?", (agora(), piloto_id))
    return {"ajuste": p["n_ajuste"], "validacao": p["n_validacao"], "reserva": p["n_reserva"],
            "excluidos_teste_rapido": len(excluidos)}


def amostra(con, piloto_id: int, conjuntos=("ajuste", "validacao")) -> list[dict]:
    marc = ",".join("?" * len(conjuntos))
    return [dict(r) for r in con.execute(
        f"""SELECT s.*, a.chave, a.titulo, a.ano, a.revista FROM piloto_amostra s JOIN artigo a ON a.id=s.artigo_id
            WHERE s.piloto_id=? AND s.conjunto IN ({marc}) ORDER BY s.conjunto, a.chave""",
        (piloto_id, *conjuntos))]


def artigos_ocultos(con) -> set[int]:
    """Articles whose Lutz answers must stay hidden (blind pilot not yet imported)."""
    out: set[int] = set()
    for p in con.execute("SELECT id FROM piloto WHERE cegamento_aberto=0 AND sorteado_em IS NOT NULL"):
        out |= {r[0] for r in con.execute(
            "SELECT artigo_id FROM piloto_amostra WHERE piloto_id=? AND conjunto IN ('ajuste','validacao')", (p[0],))}
    return out


# ── human sheets ─────────────────────────────────────────────────────────────


def _codebook_planilha(con, p: dict) -> cbk.Codebook:
    v = um(con, "SELECT versao FROM codebook WHERE id=?", (p["codebook_id"],))["versao"]
    return cbk.carregar(con, v)


def exportar_planilha(con, piloto_id: int, avaliador: str, destino: Path, sep: str = ",") -> int:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    if not p or not p["sorteado_em"]:
        raise EstadoInvalido("Sorteie o piloto antes de gerar as planilhas.")
    if avaliador not in jload(p["avaliadores"]):
        raise LutzError(f"Avaliador '{avaliador}' não está no plano ({', '.join(jload(p['avaliadores']))}).")
    cb = _codebook_planilha(con, p)
    cab = ["artigo", "titulo"]
    for c in cb.campos:
        cab += [c.nome, f"{c.nome}__nao_reportado", f"{c.nome}__pagina"]
    linhas = amostra(con, piloto_id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow(cab)
        for a in linhas:
            w.writerow([a["chave"], a["titulo"]] + [""] * (3 * len(cb.campos)))
    guia = destino.with_name(f"guia_{destino.stem}.md")
    partes = [f"# Guia da planilha do piloto — avaliador {avaliador}\n",
              "Extraia cada artigo sem consultar as respostas do Lutz. Para cada campo, preencha o valor "
              "ou marque `sim` na coluna `__nao_reportado`. Informe a página física do PDF.\n"]
    for c in cb.campos:
        partes.append(f"## {c.nome} ({c.tipo})\n\n{c.instrucao}\n")
        if c.valores:
            partes.append("Valores aceitos: " + ", ".join(f"`{v}`" for v in c.valores) + "\n")
        for v, d in c.definicoes.items():
            partes.append(f"- `{v}`: {d}")
        if c.unidade:
            partes.append(f"Unidade: {c.unidade}\n")
    guia.write_text("\n".join(partes) + "\n", encoding="utf-8")
    return len(linhas)


def importar_planilha(con, piloto_id: int, avaliador: str, origem) -> dict:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    if not p or not p["sorteado_em"]:
        raise EstadoInvalido("Piloto não sorteado.")
    if avaliador != "consenso" and avaliador not in jload(p["avaliadores"]):
        raise LutzError(f"Avaliador '{avaliador}' não está no plano.")
    cb = _codebook_planilha(con, p)
    av = um(con, "SELECT id FROM avaliador WHERE nome=?", (avaliador,))["id"]
    por_chave = {a["chave"]: a for a in amostra(con, piloto_id, ("ajuste", "validacao", "reserva"))}
    erros, vazias, gravadas = [], 0, 0
    registros = []
    vistos = set()
    for n, linha in enumerate(_ler_csv(origem), start=2):
        chave = (linha.get("artigo") or "").strip()
        if not chave:
            continue
        if chave not in por_chave:
            erros.append({"linha": n, "erro": f"artigo '{chave}' não pertence à amostra do piloto"})
            continue
        vistos.add(chave)
        for c in cb.campos:
            valor = (linha.get(c.nome) or "").strip()
            nr = (linha.get(f"{c.nome}__nao_reportado") or "").strip().lower() in SIM
            pag = (linha.get(f"{c.nome}__pagina") or "").strip()
            if not valor and not nr:
                vazias += 1
                erros.append({"linha": n, "erro": f"{chave}/{c.nome}: vazio (preencha ou marque não reportado)"})
                continue
            norm, erro = normalizar_valor(c, None if nr else valor, nr)
            if erro:
                erros.append({"linha": n, "erro": f"{chave}/{c.nome}: {erro}"})
                continue
            registros.append((piloto_id, av, por_chave[chave]["artigo_id"], c.nome, c.hash(), norm, int(nr),
                              int(pag) if pag.isdigit() else None, agora()))
    faltando = sorted(set(a["chave"] for a in amostra(con, piloto_id)) - vistos)
    if erros:
        return {"gravadas": 0, "erros": erros, "faltando": faltando, "vazias": vazias}
    with transacao(con):
        for r in registros:
            con.execute(
                """INSERT OR REPLACE INTO extracao_humana (piloto_id, avaliador_id, artigo_id, campo_chave, campo_hash,
                   valor, nao_reportado, pagina, importado_em) VALUES (?,?,?,?,?,?,?,?,?)""", r)
            gravadas += 1
    _atualizar_cegamento(con, piloto_id)
    return {"gravadas": gravadas, "erros": [], "faltando": faltando, "vazias": 0}


def _cobertura(con, piloto_id: int, avaliador: str) -> tuple[int, int]:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    cb = _codebook_planilha(con, p)
    esperado = len(amostra(con, piloto_id)) * len(cb.campos)
    feito = con.execute(
        """SELECT count(*) FROM extracao_humana h JOIN avaliador v ON v.id=h.avaliador_id
           JOIN piloto_amostra s ON s.artigo_id=h.artigo_id AND s.piloto_id=h.piloto_id
           WHERE h.piloto_id=? AND v.nome=? AND s.conjunto IN ('ajuste','validacao')""",
        (piloto_id, avaliador)).fetchone()[0]
    return feito, esperado


def _atualizar_cegamento(con, piloto_id: int) -> None:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    completos = all(_cobertura(con, piloto_id, a)[0] >= _cobertura(con, piloto_id, a)[1]
                    for a in jload(p["avaliadores"]))
    if completos:
        con.execute("UPDATE piloto SET cegamento_aberto=1 WHERE id=?", (piloto_id,))


def respostas_humanas(con, piloto_id: int, avaliador: str) -> dict[tuple[int, str], dict]:
    return {(r["artigo_id"], r["campo_chave"]): dict(r) for r in con.execute(
        """SELECT h.* FROM extracao_humana h JOIN avaliador v ON v.id=h.avaliador_id
           WHERE h.piloto_id=? AND v.nome=?""", (piloto_id, avaliador))}


def _chave_valor(campo: cbk.Campo, valor: str | None, nr: bool):
    if nr:
        return VAZIO
    if valor is None:
        return SEM_VALOR
    return valor


def _concordam(campo: cbk.Campo, a: tuple, b: tuple, limiar_texto: float) -> bool:
    (va, nra), (vb, nrb) = a, b
    if nra or nrb:
        return bool(nra) and bool(nrb)
    if va is None or vb is None:
        return False
    if campo.tipo == "numerico":
        x, y = parse_numero(va), parse_numero(vb)
        return x is not None and y is not None and iguais_numericos(x, y, campo.tolerancia_relativa)
    if campo.tipo == "texto":
        return fuzz.token_set_ratio(normalizar(va), normalizar(vb)) >= limiar_texto
    return va == vb


def exportar_consenso(con, piloto_id: int, destino: Path, settings: Settings, sep: str = ",") -> dict:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    avs = jload(p["avaliadores"])
    if len(avs) != 2:
        raise LutzError("O consenso só existe com dois avaliadores.")
    for a in avs:
        f, e = _cobertura(con, piloto_id, a)
        if f < e:
            raise EstadoInvalido(f"Planilha do avaliador {a} incompleta ({f} de {e} células).")
    cb = _codebook_planilha(con, p)
    ha, hb = respostas_humanas(con, piloto_id, avs[0]), respostas_humanas(con, piloto_id, avs[1])
    divergentes = 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow(["artigo", "campo", f"valor_{avs[0]}", f"valor_{avs[1]}", "consenso_valor",
                    "consenso_nao_reportado", "nota"])
        for art in amostra(con, piloto_id):
            for c in cb.campos:
                x, y = ha[(art["artigo_id"], c.nome)], hb[(art["artigo_id"], c.nome)]
                if _concordam(c, (x["valor"], x["nao_reportado"]), (y["valor"], y["nao_reportado"]),
                              settings.limiares.texto_similaridade) and c.tipo != "texto":
                    continue
                if c.tipo == "texto" and x["valor"] == y["valor"] and x["nao_reportado"] == y["nao_reportado"]:
                    continue
                divergentes += 1
                w.writerow([art["chave"], c.nome, "não reportado" if x["nao_reportado"] else x["valor"],
                            "não reportado" if y["nao_reportado"] else y["valor"], "", "", ""])
    return {"divergentes": divergentes}


def importar_consenso(con, piloto_id: int, origem, settings: Settings) -> dict:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    avs = jload(p["avaliadores"])
    cb = _codebook_planilha(con, p)
    ha, hb = respostas_humanas(con, piloto_id, avs[0]), respostas_humanas(con, piloto_id, avs[1])
    decisoes = {}
    erros = []
    por_chave = {a["chave"]: a for a in amostra(con, piloto_id)}
    for n, linha in enumerate(_ler_csv(origem), start=2):
        chave, campo = (linha.get("artigo") or "").strip(), (linha.get("campo") or "").strip()
        if chave not in por_chave:
            erros.append({"linha": n, "erro": f"artigo '{chave}' fora da amostra"})
            continue
        try:
            c = cb.campo(campo)
        except KeyError:
            erros.append({"linha": n, "erro": f"campo '{campo}' inexistente"})
            continue
        valor = (linha.get("consenso_valor") or "").strip()
        nr = (linha.get("consenso_nao_reportado") or "").strip().lower() in SIM
        if not valor and not nr:
            erros.append({"linha": n, "erro": f"{chave}/{campo}: consenso vazio"})
            continue
        norm, erro = normalizar_valor(c, None if nr else valor, nr)
        if erro:
            erros.append({"linha": n, "erro": f"{chave}/{campo}: {erro}"})
            continue
        decisoes[(por_chave[chave]["artigo_id"], campo)] = (norm, nr)
    linhas = []
    for art in amostra(con, piloto_id):
        for c in cb.campos:
            k = (art["artigo_id"], c.nome)
            if k in decisoes:
                v, nr = decisoes[k]
            else:
                x, y = ha[k], hb[k]
                iguais = (x["valor"] == y["valor"] and x["nao_reportado"] == y["nao_reportado"]) or (
                    c.tipo != "texto" and _concordam(c, (x["valor"], x["nao_reportado"]),
                                                     (y["valor"], y["nao_reportado"]), 100))
                if not iguais:
                    erros.append({"linha": None, "erro": f"{art['chave']}/{c.nome}: divergência sem consenso"})
                    continue
                v, nr = x["valor"], bool(x["nao_reportado"])
            linhas.append((art["chave"], c.nome, v, nr))
    if erros:
        return {"gravadas": 0, "erros": erros}
    av = um(con, "SELECT id FROM avaliador WHERE nome='consenso'")["id"]
    with transacao(con):
        for chave, campo, v, nr in linhas:
            c = cb.campo(campo)
            con.execute(
                """INSERT OR REPLACE INTO extracao_humana (piloto_id, avaliador_id, artigo_id, campo_chave, campo_hash,
                   valor, nao_reportado, pagina, importado_em) VALUES (?,?,?,?,?,?,?,NULL,?)""",
                (piloto_id, av, por_chave[chave]["artigo_id"], campo, c.hash(), v, int(nr), agora()))
    return {"gravadas": len(linhas), "erros": []}


# ── comparison ───────────────────────────────────────────────────────────────


def _padrao_ouro(con, p: dict) -> str:
    avs = jload(p["avaliadores"])
    if len(avs) == 1:
        return avs[0]
    tem = con.execute("""SELECT count(*) FROM extracao_humana h JOIN avaliador v ON v.id=h.avaliador_id
                         WHERE h.piloto_id=? AND v.nome='consenso'""", (p["id"],)).fetchone()[0]
    if not tem:
        raise EstadoInvalido("Com dois avaliadores, faça o consenso antes ('lutz pilot consensus').")
    return "consenso"


def _valor_lutz(con, cel: dict) -> tuple[str | None, bool]:
    """Lutz's automatic answer (before any adjudication)."""
    adj = con.execute("SELECT valor_anterior, nao_reportado_anterior FROM adjudicacao WHERE celula_id=? "
                      "ORDER BY id LIMIT 1", (cel["id"],)).fetchone()
    if adj is not None:
        return adj[0], bool(adj[1])
    return cel["valor_final"], bool(cel["nao_reportado"])


def _compativel(campo_exec: cbk.Campo, campo_hash_humano: str, campo_planilha: cbk.Campo | None) -> bool:
    if campo_exec.hash() == campo_hash_humano:
        return True
    if campo_planilha is None:
        return False
    if campo_exec.tipo != campo_planilha.tipo:
        return False
    if campo_exec.tipo in ("categorico", "ordinal"):
        return list(campo_exec.valores) == list(campo_planilha.valores)
    return True


def _metricas_par(campo: cbk.Campo, pares: list[tuple[tuple, tuple]], settings: Settings) -> dict:
    """pares: [((valor_a, nr_a), (valor_b, nr_b))] one per article."""
    lim = settings.limiares
    reps, sem = settings.metricas.bootstrap_repeticoes, settings.sementes.bootstrap
    n = len(pares)
    concord = [_concordam(campo, a, b, lim.texto_similaridade) for a, b in pares]
    pct = sum(concord) / n if n else math.nan
    out: dict = {"n": n, "pct_concordancia": pct, "metrica": None, "valor": math.nan, "ic": (math.nan, math.nan),
                 "notas": []}
    if campo.tipo == "categorico":
        a = [_chave_valor(campo, *x) for x, _ in pares]
        b = [_chave_valor(campo, *y) for _, y in pares]
        out["metrica"] = "kappa"
        out["valor"] = M.cohen_kappa(a, b)
        aa, bb = np.array(a, dtype=object), np.array(b, dtype=object)
        out["ic"] = M.bootstrap_ic(lambda i: M.cohen_kappa(list(aa[i]), list(bb[i])), n, sem, reps)
        cat, frac = M.categoria_dominante(a + b)
        if frac > lim.pabak_categoria_dominante:
            out["pabak"] = M.pabak(a, b, k=max(2, len(campo.valores) + 1))
            out["notas"].append(f"PABAK {out['pabak']:.2f}: {frac:.0%} das respostas são '{cat}'")
    elif campo.tipo == "ordinal":
        a = [_chave_valor(campo, *x) for x, _ in pares]
        b = [_chave_valor(campo, *y) for _, y in pares]
        out["metrica"] = "kappa_ponderado"
        out["valor"] = M.kappa_ponderado(a, b, campo.valores)
        aa, bb = np.array(a, dtype=object), np.array(b, dtype=object)
        out["ic"] = M.bootstrap_ic(lambda i: M.kappa_ponderado(list(aa[i]), list(bb[i]), campo.valores), n, sem, reps)
        out["kappa_simples"] = M.cohen_kappa(a, b)
    elif campo.tipo == "numerico":
        pares_num = [(parse_numero(x[0]), parse_numero(y[0])) for x, y in pares
                     if not x[1] and not y[1] and x[0] is not None and y[0] is not None]
        pares_num = [(x, y) for x, y in pares_num if x is not None and y is not None]
        out["metrica"] = "icc"
        icc, _ = M.icc_a1([[x, y] for x, y in pares_num])
        out["valor"] = icc
        arr = np.array(pares_num, dtype=float) if pares_num else np.zeros((0, 2))
        out["ic"] = M.bootstrap_ic(lambda i: M.icc_a1(arr[i].tolist())[0], len(arr), sem, reps)
        out["erros"] = M.erros_absolutos([x for x, _ in pares_num], [y for _, y in pares_num])
        exatos = sum(1 for x, y in pares_num if iguais_numericos(x, y, campo.tolerancia_relativa))
        out["pct_exato"] = exatos / len(pares_num) if pares_num else math.nan
        presenca = [(x[1], y[1]) for x, y in pares]
        out["pct_presenca"] = sum(1 for a, b in presenca if a == b) / n if n else math.nan
        if pares_num and out["pct_exato"] < 1:
            out["notas"].append(f"{len(pares_num) - exatos} de {len(pares_num)} valores diferentes "
                                f"(erro mediano {out['erros']['mediano']:g}, máximo {out['erros']['maximo']:g})")
    else:
        out["metrica"] = "pct_equivalencia"
        p_, lo, hi = M.wilson(sum(concord), n)
        out["valor"], out["ic"] = p_, (lo, hi)
        out["notas"].append("equivalência automática (similaridade de texto); confira as divergências")
    return out


def decidir_campo(campo: cbk.Campo, m: dict, lim) -> tuple[str, str]:
    v, lo = m["valor"], m["ic"][0]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "indefinida", "métrica indefinida (sem variação ou poucos dados): decidir manualmente"
    if campo.tipo == "texto":
        if v >= lim.decisao_texto_alto and (lo or 0) >= lim.decisao_texto_medio:
            return "lutz_sozinho", ""
        if v >= lim.decisao_texto_medio:
            return "revisar_media_baixa", ""
        return "reescrever", ""
    if v >= lim.decisao_alto and lo is not None and not math.isnan(lo) and lo >= lim.decisao_ic_inferior:
        if campo.tipo == "numerico" and (m.get("pct_exato", 1) or 0) < lim.decisao_numerico_exato:
            return "revisar_media_baixa", (f"ICC alto, mas só {m['pct_exato']:.0%} dos valores iguais "
                                           "(dentro da tolerância)")
        return "lutz_sozinho", ""
    if v >= lim.decisao_medio:
        nota = "IC inferior abaixo do limiar" if v >= lim.decisao_alto else ""
        return "revisar_media_baixa", nota
    return "reescrever", "reescreva a instrução e faça nova rodada de ajuste; se não melhorar, extração humana"


def execucao_do_conjunto(con, piloto_id: int, conjunto: str) -> dict | None:
    return um(con, """SELECT * FROM execucao WHERE piloto_id=? AND conjunto_piloto=? AND status='concluida'
                     ORDER BY id DESC LIMIT 1""", (piloto_id, conjunto))


def comparar(con, piloto_id: int, conjunto: str, settings: Settings, execucao_id: int | None = None) -> dict:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    if p is None:
        raise EstadoInvalido("Piloto não encontrado.")
    if not p["cegamento_aberto"]:
        raise EstadoInvalido("Importe todas as planilhas humanas antes de comparar (piloto cego).")
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,)) if execucao_id else \
        execucao_do_conjunto(con, piloto_id, conjunto)
    if ex is None or ex["piloto_id"] != piloto_id or ex["conjunto_piloto"] != conjunto:
        raise EstadoInvalido(f"Rode a extração do conjunto '{conjunto}' antes ('lutz extract --piloto {conjunto}').")
    ouro = _padrao_ouro(con, p)
    cb_exec = cbk.carregar(con, um(con, "SELECT versao FROM codebook WHERE id=?", (ex["codebook_id"],))["versao"])
    cb_plan = _codebook_planilha(con, p)
    humanos = respostas_humanas(con, piloto_id, ouro)
    avs = jload(p["avaliadores"])
    h_a = respostas_humanas(con, piloto_id, avs[0])
    h_b = respostas_humanas(con, piloto_id, avs[1]) if len(avs) == 2 else None
    artigos = [a["artigo_id"] for a in amostra(con, piloto_id, (conjunto,))]
    resultado: dict = {"piloto_id": piloto_id, "execucao_id": ex["id"], "conjunto": conjunto, "padrao_ouro": ouro,
                       "campos": [], "niveis": [], "avisos": []}
    calib: dict[str, list[bool]] = {"alta": [], "media": [], "baixa": []}
    linhas_metrica = []
    decisoes = []
    for nome in jload(ex["campos"]):
        c = cb_exec.campo(nome)
        try:
            c_plan = cb_plan.campo(nome)
        except KeyError:
            c_plan = None
        pares, pares_hh = [], []
        incompat = False
        for aid in artigos:
            h = humanos.get((aid, nome))
            cel = um(con, "SELECT * FROM celula WHERE execucao_id=? AND artigo_id=? AND campo_chave=?",
                     (ex["id"], aid, nome))
            if h is None or cel is None:
                continue
            if not _compativel(c, h["campo_hash"], c_plan):
                incompat = True
                break
            lutz = _valor_lutz(con, cel)
            pares.append((lutz, (h["valor"], bool(h["nao_reportado"]))))
            if cel["nivel"] in calib:
                calib[cel["nivel"]].append(_concordam(c, lutz, (h["valor"], bool(h["nao_reportado"])),
                                                      settings.limiares.texto_similaridade))
            if h_b is not None:
                xa, xb = h_a.get((aid, nome)), h_b.get((aid, nome))
                if xa and xb:
                    pares_hh.append(((xa["valor"], bool(xa["nao_reportado"])), (xb["valor"], bool(xb["nao_reportado"]))))
        if incompat:
            resultado["avisos"].append(f"{nome}: tipo ou valores mudaram desde a planilha humana; comparação inválida")
            continue
        if not pares:
            continue
        m = _metricas_par(c, pares, settings)
        hh = _metricas_par(c, pares_hh, settings) if pares_hh else None
        dec, nota = decidir_campo(c, m, settings.limiares)
        if hh is not None and not math.isnan(hh["valor"]) and not math.isnan(m["valor"]) and m["valor"] < hh["valor"] - 0.1:
            nota = (nota + "; " if nota else "") + "abaixo do humano × humano"
        resultado["campos"].append({"campo": nome, "tipo": c.tipo, "lutz_ouro": m, "humano_humano": hh,
                                    "decisao": dec if conjunto == "validacao" else None, "nota": nota})
        par = f"lutz×{ouro}"
        linhas_metrica.append((nome, m["metrica"], m["valor"], m["ic"][0], m["ic"][1], m["n"], par,
                               "; ".join(m["notas"])))
        linhas_metrica.append((nome, "pct_concordancia", m["pct_concordancia"], None, None, m["n"], par, ""))
        for extra in ("pabak", "kappa_simples", "pct_exato", "pct_presenca"):
            if extra in m:
                linhas_metrica.append((nome, extra, m[extra], None, None, m["n"], par, ""))
        if "erros" in m:
            linhas_metrica.append((nome, "erro_abs_mediano", m["erros"]["mediano"], None, None, m["erros"]["n"], par, ""))
            linhas_metrica.append((nome, "erro_abs_maximo", m["erros"]["maximo"], None, None, m["erros"]["n"], par, ""))
        if hh is not None:
            linhas_metrica.append((nome, hh["metrica"], hh["valor"], hh["ic"][0], hh["ic"][1], hh["n"],
                                   f"{avs[0]}×{avs[1]}", ""))
        if conjunto == "validacao":
            decisoes.append((nome, m["metrica"], m["valor"], m["ic"][0], m["ic"][1], dec, nota))
    for niv in ("alta", "media", "baixa"):
        acertos, n = sum(calib[niv]), len(calib[niv])
        p_, lo, hi = M.wilson(acertos, n)
        resultado["niveis"].append({"nivel": niv, "n": n, "acertos": acertos, "taxa": p_, "ic_inf": lo, "ic_sup": hi})
        linhas_metrica.append((None, f"acerto_{niv}", p_, lo, hi, n, f"lutz×{ouro}", f"{acertos} de {n}"))
    alta = resultado["niveis"][0]
    if alta["n"] and alta["taxa"] < settings.limiares.calibracao_alta_minima:
        resultado["avisos"].append(
            f"Células Alta acertaram {alta['taxa']:.1%} (< {settings.limiares.calibracao_alta_minima:.0%}): "
            "os limiares do Modo Autônomo estão frouxos.")

    def limpo(x):
        return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)

    with transacao(con):
        con.execute("DELETE FROM metrica WHERE execucao_id=? AND piloto_id=? AND escopo IN ('calibrado','nivel')",
                    (ex["id"], piloto_id))
        for nome, met, v, lo, hi, n, par, nota in linhas_metrica:
            con.execute(
                """INSERT INTO metrica (execucao_id, piloto_id, campo_chave, escopo, nome, valor, ic_inf, ic_sup, n,
                   par, nota, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ex["id"], piloto_id, nome, "nivel" if nome is None else "calibrado", met, limpo(v), limpo(lo),
                 limpo(hi), n, par, nota, agora()))
        if conjunto == "validacao":
            for nome, met, v, lo, hi, dec, nota in decisoes:
                con.execute(
                    """INSERT OR REPLACE INTO decisao_campo (piloto_id, execucao_id, campo_chave, metrica, valor, ic_inf,
                       ic_sup, decisao, nota, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (piloto_id, ex["id"], nome, met, limpo(v), limpo(lo), limpo(hi), dec, nota, agora()))
    return resultado


def rodadas(con, piloto_id: int) -> list[dict]:
    out = []
    ant = None
    for r in con.execute("""SELECT e.id, e.conjunto_piloto, e.status, e.criada_em, c.versao, c.hash FROM execucao e
                            JOIN codebook c ON c.id=e.codebook_id WHERE e.piloto_id=? ORDER BY e.id""", (piloto_id,)):
        d = dict(r)
        d["mudancas"] = None
        if ant is not None and ant != d["versao"]:
            df = cbk.diff(con, ant, d["versao"])
            d["mudancas"] = {"adicionados": df["adicionados"], "removidos": df["removidos"],
                             "alterados": [x["campo"] for x in df["alterados"]]}
        ant = d["versao"]
        out.append(d)
    return out


def estado(con, piloto_id: int | None = None) -> dict | None:
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,)) if piloto_id else atual(con)
    if p is None:
        return None
    avs = jload(p["avaliadores"])
    cobertura = {a: dict(zip(("feito", "esperado"), _cobertura(con, p["id"], a), strict=True))
                 if p["sorteado_em"] else None for a in avs}
    tem_consenso = con.execute("""SELECT count(*) FROM extracao_humana h JOIN avaliador v ON v.id=h.avaliador_id
                                  WHERE h.piloto_id=? AND v.nome='consenso'""", (p["id"],)).fetchone()[0] > 0
    conj = Counter(r[0] for r in con.execute("SELECT conjunto FROM piloto_amostra WHERE piloto_id=?", (p["id"],)))
    decisoes = [dict(r) for r in con.execute("SELECT * FROM decisao_campo WHERE piloto_id=? ORDER BY campo_chave",
                                             (p["id"],))]
    return {
        "piloto": p | {"plano": jload(p["plano"]), "avaliadores": avs},
        "amostra": dict(conj), "cobertura": cobertura, "consenso": tem_consenso,
        "rodadas": rodadas(con, p["id"]),
        "validacao": execucao_do_conjunto(con, p["id"], "validacao"),
        "decisoes": decisoes,
        "tamanho": M.tabela_tamanho_piloto(),
    }


def salvar_resposta(con, piloto_id: int, avaliador: str, chave: str, campo_nome: str, valor: str | None,
                    nao_reportado: bool, pagina: int | None = None) -> dict:
    """One answer typed in the blind side-by-side form of the web interface."""
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    if not p or not p["sorteado_em"]:
        raise EstadoInvalido("Piloto não sorteado.")
    if avaliador not in jload(p["avaliadores"]):
        raise LutzError(f"Avaliador '{avaliador}' não está no plano.")
    art = {a["chave"]: a for a in amostra(con, piloto_id, ("ajuste", "validacao", "reserva"))}.get(chave)
    if art is None:
        raise LutzError(f"O artigo {chave} não pertence ao piloto.")
    cb = _codebook_planilha(con, p)
    c = cb.campo(campo_nome)
    norm, erro = normalizar_valor(c, None if nao_reportado else valor, nao_reportado)
    if erro:
        raise LutzError(erro)
    av = um(con, "SELECT id FROM avaliador WHERE nome=?", (avaliador,))["id"]
    con.execute(
        """INSERT OR REPLACE INTO extracao_humana (piloto_id, avaliador_id, artigo_id, campo_chave, campo_hash, valor,
           nao_reportado, pagina, importado_em) VALUES (?,?,?,?,?,?,?,?,?)""",
        (piloto_id, av, art["artigo_id"], c.nome, c.hash(), norm, int(nao_reportado), pagina, agora()))
    _atualizar_cegamento(con, piloto_id)
    feito, esperado = _cobertura(con, piloto_id, avaliador)
    return {"valor": norm, "nao_reportado": nao_reportado, "feito": feito, "esperado": esperado}


def formulario(con, piloto_id: int, avaliador: str) -> dict:
    """Articles and fields of the blind form, with the answers of THIS rater only."""
    p = um(con, "SELECT * FROM piloto WHERE id=?", (piloto_id,))
    cb = _codebook_planilha(con, p)
    respostas = respostas_humanas(con, piloto_id, avaliador)
    artigos = []
    for a in amostra(con, piloto_id):
        artigos.append({"chave": a["chave"], "titulo": a["titulo"], "conjunto": a["conjunto"],
                        "respostas": {c.nome: (lambda r: None if r is None else {
                            "valor": r["valor"], "nao_reportado": bool(r["nao_reportado"]), "pagina": r["pagina"]})(
                            respostas.get((a["artigo_id"], c.nome))) for c in cb.campos}})
    return {"campos": [c.model_dump(mode="json") for c in cb.campos], "artigos": artigos,
            "cobertura": dict(zip(("feito", "esperado"), _cobertura(con, piloto_id, avaliador), strict=True))}
