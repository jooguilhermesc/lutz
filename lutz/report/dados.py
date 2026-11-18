"""Everything the reliability report says, read from the project database.

Each part of the report is built from these structures only; the renderers never query the
database. Annex ``origem_dos_dados`` documents where each number comes from.
"""

from __future__ import annotations

import math
from collections import Counter

from lutz.calibrated import piloto as pil
from lutz.config.settings import Settings, temperatura_aplicada
from lutz.core import codebook as cbk
from lutz.core.db import jload, um
from lutz.core.errors import EstadoInvalido
from lutz.core.ingestao import legibilidade
from lutz.extraction.metricas_autonomo import metricas
from lutz.llm.cliente import consumo
from lutz.revisao import adjudicacao as adj
from lutz.revisao import auditoria as aud


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _piloto_aplicavel(con, ex: dict, settings: Settings) -> tuple[dict | None, str]:
    """The pilot whose validation run used the same frozen codebook and thresholds as *ex*."""
    melhor_motivo = "não houve piloto"
    for p in con.execute("SELECT * FROM piloto ORDER BY id DESC"):
        val = pil.execucao_do_conjunto(con, p["id"], "validacao")
        if val is None:
            melhor_motivo = "o piloto não chegou à validação final"
            continue
        if not con.execute("SELECT 1 FROM decisao_campo WHERE piloto_id=?", (p["id"],)).fetchone():
            melhor_motivo = "a comparação do conjunto de validação não foi feita ('lutz pilot compare')"
            continue
        if ex["tipo"] == "piloto" and ex["id"] == val["id"]:
            return dict(p) | {"validacao": val}, ""
        if val["codebook_id"] != ex["codebook_id"]:
            melhor_motivo = (f"a validação do piloto usou outro codebook (execução {val['id']}); "
                             "a calibração não se aplica a esta execução")
            continue
        lim_val = jload(val["config"])["limiares"]
        if lim_val != settings.limiares.model_dump(mode="json"):
            melhor_motivo = "a execução usou limiares diferentes dos da validação; a calibração não se aplica"
            continue
        return dict(p) | {"validacao": val}, ""
    return None, melhor_motivo


def coletar(projeto, con, execucao_id: int) -> dict:
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,))
    if ex is None:
        raise EstadoInvalido(f"Execução {execucao_id} não existe.")
    if ex["tipo"] == "teste":
        raise EstadoInvalido("Teste rápido não gera relatório.")
    if ex["status"] != "concluida":
        raise EstadoInvalido(f"A execução {execucao_id} não está concluída ({ex['status']}).")
    ocultos = pil.artigos_ocultos(con) & set(jload(ex["artigos"]))
    if ocultos:
        raise EstadoInvalido(
            "Há artigos do piloto cego nesta execução e as planilhas humanas ainda não foram importadas. "
            "Gerar o relatório agora revelaria as respostas do Lutz."
        )
    settings = Settings.model_validate(jload(ex["config"]))
    cb_row = um(con, "SELECT * FROM codebook WHERE id=?", (ex["codebook_id"],))
    cb = cbk.carregar(con, cb_row["versao"])
    projeto_info = dict(con.execute("SELECT * FROM projeto WHERE id=1").fetchone())
    extratores = [dict(r) for r in con.execute(
        "SELECT * FROM extrator WHERE execucao_id=? ORDER BY papel, rotulo", (execucao_id,))]
    obs = {r["rotulo"]: r for r in consumo(con, execucao_id)["por_papel"]}
    for e in extratores:
        e["temperatura"] = temperatura_aplicada(e["provedor"], e["modelo"], e["temperatura"])
        o = obs.get(e["rotulo"])
        e["modelo_observado"] = (o or {}).get("modelo_observado") or ""
    contexto = Counter()
    for r in con.execute("SELECT grupo FROM chamada_llm WHERE execucao_id=? AND papel='extrator'", (execucao_id,)):
        partes = r[0].split(":")
        if len(partes) > 1:
            contexto[partes[1]] += 1
    artigos = [dict(r) for r in con.execute(
        f"SELECT * FROM artigo WHERE id IN ({','.join('?' * len(jload(ex['artigos'])))}) ORDER BY chave",
        jload(ex["artigos"]))]
    fora = [dict(r) for r in con.execute("SELECT chave, titulo, status, erro FROM artigo WHERE status!='pronto'")]
    m_auto = metricas(con, execucao_id)

    p_aplic, motivo_sem_piloto = _piloto_aplicavel(con, ex, settings)
    calib = None
    m_cal: dict = {}
    decisoes: dict = {}
    if p_aplic:
        val_id = p_aplic["validacao"]["id"]
        for r in con.execute("SELECT * FROM metrica WHERE execucao_id=? AND piloto_id=? AND escopo='calibrado'",
                             (val_id, p_aplic["id"])):
            m_cal.setdefault(r["campo_chave"], {}).setdefault(r["par"], {})[r["nome"]] = dict(r)
        decisoes = {r["campo_chave"]: dict(r) for r in con.execute(
            "SELECT * FROM decisao_campo WHERE piloto_id=? AND execucao_id=?", (p_aplic["id"], val_id))}
        niveis = {r["nome"].removeprefix("acerto_"): dict(r) for r in con.execute(
            "SELECT * FROM metrica WHERE execucao_id=? AND piloto_id=? AND escopo='nivel'", (val_id, p_aplic["id"]))}
        st = pil.estado(con, p_aplic["id"])
        calib = {
            "piloto": p_aplic, "niveis": niveis, "rodadas": st["rodadas"], "amostra": st["amostra"],
            "avaliadores": jload(p_aplic["avaliadores"]), "hash_plano": p_aplic["hash_plano"],
            "consenso": st["consenso"], "semente": p_aplic["semente"],
            "n_rodadas_ajuste": sum(1 for r in st["rodadas"] if r["conjunto_piloto"] == "ajuste"),
            "validacao_id": val_id, "forcada": con.execute(
                "SELECT count(*) FROM execucao WHERE piloto_id=? AND conjunto_piloto='validacao'",
                (p_aplic["id"],)).fetchone()[0] > 1,
        }

    est_adj = adj.estatisticas(con, execucao_id)
    alter_campo: dict[str, dict] = {}
    for d in est_adj["por_campo_nivel"]:
        x = alter_campo.setdefault(d["campo"], {"enviadas": 0, "decididas": 0, "alteradas": 0})
        for k in x:
            x[k] += d[k]
    auditoria = aud.resultado(con, execucao_id)

    campos = []
    for nome in jload(ex["campos"]):
        c = cb.campo(nome)
        ma = m_auto.get(nome, {})
        mc = m_cal.get(nome, {})
        ouro = next((v for k, v in mc.items() if k.startswith("lutz×")), {})
        hh = next((v for k, v in mc.items() if not k.startswith("lutz×")), {})
        principal = next((ouro[k] for k in ("kappa", "kappa_ponderado", "icc", "pct_equivalencia") if k in ouro), None)
        hh_principal = next((hh[k] for k in ("kappa", "kappa_ponderado", "icc", "pct_equivalencia") if k in hh), None)
        campos.append({
            "nome": nome, "rotulo": c.rotulo, "tipo": c.tipo, "papel": c.papel,
            "alfa": ma.get("alfa"), "unanimes": ma.get("unanimes"),
            "pct": {n: (ma.get(f"pct_{n}") or {}).get("valor") for n in ("alta", "media", "baixa")},
            "evidencia_exata": (ma.get("pct_evidencia_exata") or {}).get("valor"),
            "nao_reportado": ma.get("pct_nao_reportado"),
            "ouro": principal, "ouro_concordancia": ouro.get("pct_concordancia"), "pabak": ouro.get("pabak"),
            "pct_exato": ouro.get("pct_exato"), "erro_mediano": ouro.get("erro_abs_mediano"),
            "erro_maximo": ouro.get("erro_abs_maximo"), "humano_humano": hh_principal,
            "decisao": decisoes.get(nome), "adjudicacao": alter_campo.get(nome),
        })

    leg = []
    for a in artigos:
        cel = [dict(r) for r in con.execute("SELECT * FROM celula WHERE execucao_id=? AND artigo_id=?",
                                            (execucao_id, a["id"]))]
        com_valor = [c for c in cel if not c["nao_reportado"] and c["valor_final"] is not None]
        frac_e1 = (sum(1 for c in com_valor if (c["e"] or 0) >= 1) / len(com_valor)) if com_valor else 0.0
        frac_nr = sum(1 for c in cel if c["nao_reportado"] and (c["a"] or 0) >= 0.999) / (len(cel) or 1)
        ing = legibilidade(a)
        indice = round((ing + frac_e1 + (1 - frac_nr)) / 3, 3)
        leg.append({"chave": a["chave"], "titulo": a["titulo"], "indice": indice, "ingestao": ing,
                    "frac_evidencia_exata": frac_e1, "frac_nao_reportado_unanime": frac_nr,
                    "duas_colunas": bool(a["duas_colunas"]), "frac_oculto": a["frac_oculto"]})
    excedeu = sorted({r[0] for r in con.execute(
        """SELECT DISTINCT a.chave FROM extracao_bruta b JOIN celula c ON c.id=b.celula_id
           JOIN artigo a ON a.id=c.artigo_id WHERE c.execucao_id=? AND b.erro LIKE '%janela de contexto%'""",
        (execucao_id,))})
    total_celulas = con.execute("SELECT count(*) FROM celula WHERE execucao_id=?", (execucao_id,)).fetchone()[0]
    falhas = [dict(r) for r in con.execute(
        """SELECT b.rotulo, count(*) n FROM extracao_bruta b JOIN celula c ON c.id=b.celula_id
           WHERE c.execucao_id=? AND b.status='falha' GROUP BY b.rotulo""", (execucao_id,))]
    return {
        "projeto": projeto_info, "execucao": ex, "settings": settings, "codebook": cb, "codebook_row": cb_row,
        "extratores": extratores, "contexto": dict(contexto), "artigos": artigos, "fora_do_corpus": fora,
        "campos": campos, "geral": m_auto.get(None, {}), "calibracao": calib, "motivo_sem_piloto": motivo_sem_piloto,
        "adjudicacao": est_adj, "auditoria": auditoria, "legibilidade": leg, "excedeu_contexto": excedeu,
        "total_celulas": total_celulas, "falhas_extratores": falhas, "consumo": consumo(con, execucao_id),
        "historico_codebook": cbk.historico(con),
    }


def faixa(campos: list[dict], chave: str = "alfa") -> tuple[float, float] | None:
    vals = [c[chave]["valor"] for c in campos if c.get(chave) and not _nan(c[chave].get("valor"))]
    if not vals:
        return None
    return min(vals), max(vals)
