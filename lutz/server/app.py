"""Local REST API (FastAPI) and the web interface.

Binds to 127.0.0.1 only (no authentication: single researcher on her own computer). The web
SPA consumes this API; the CLI and the MCP server call the same domain modules in-process.
Long operations (import, extraction, quick test, report) run as background jobs and answer
``202`` with a job id; progress is streamed with Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import re
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from lutz import __version__
from lutz.calibrated import piloto as pil
from lutz.config.env import salvar_env, valores_com_origem
from lutz.config.settings import avisos, carregar_settings, estrategia_diversidade, validar_yaml
from lutz.core import assistente
from lutz.core import codebook as cbk
from lutz.core import metricas as M
from lutz.core.db import conectar, jload, um
from lutz.core.errors import (
    CodebookInvalido,
    ConfigInvalida,
    EstadoInvalido,
    LutzError,
    ProjetoOcupado,
)
from lutz.core.ingestao import importar_pdf, legibilidade
from lutz.core.inicializar import info_projeto
from lutz.core.lock import bloqueio
from lutz.core.project import Projeto
from lutz.extraction import executor as ex
from lutz.extraction.metricas_autonomo import metricas
from lutz.llm.cliente import consumo
from lutz.report import render
from lutz.report.dados import coletar
from lutz.report.gerar import gerar, tabela_larga, tabela_longa
from lutz.revisao import adjudicacao as adj
from lutz.revisao import auditoria as aud
from lutz.server.jobs import GerenciadorJobs


def _limpo(obj: Any) -> Any:
    """JSON-safe: NaN/inf become null."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {k: _limpo(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_limpo(v) for v in obj]
    return obj


def _dist_web() -> Path | None:
    try:
        p = Path(str(resources.files("lutz").joinpath("web")))
        if (p / "index.html").is_file():
            return p
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        pass
    dev = Path(__file__).resolve().parents[2] / "web" / "dist"
    return dev if (dev / "index.html").is_file() else None


def criar_app(projeto: Projeto) -> FastAPI:
    app = FastAPI(title="Lutz", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    jobs = GerenciadorJobs(projeto)
    app.state.projeto = projeto
    app.state.jobs = jobs

    if not (projeto.estado / "lock").exists():
        con0 = conectar(projeto)
        ex.reparar_interrompidas(con0)
        con0.close()

    from pydantic import ValidationError as _ErroValidacao

    @app.exception_handler(_ErroValidacao)
    async def _erro_validacao(_: Request, exc: _ErroValidacao):
        msgs = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"erro": "Dados inválidos:\n" + "\n".join(msgs)}, status_code=422)

    @app.exception_handler(LutzError)
    async def _erro_dominio(_: Request, exc: LutzError):
        status = 409 if isinstance(exc, (EstadoInvalido, ProjetoOcupado)) else 422 if isinstance(
            exc, (CodebookInvalido, ConfigInvalida)) else 400
        return JSONResponse({"erro": str(exc)}, status_code=status)

    def con():
        return conectar(projeto)

    def ler(fn):
        c = con()
        try:
            return _limpo(fn(c))
        finally:
            c.close()

    def escrever(comando: str, fn):
        with bloqueio(projeto, f"lutz web: {comando}"):
            c = con()
            try:
                return _limpo(fn(c))
            finally:
                c.close()

    def iniciar_job(tipo, descricao, fn, execucao_id=None):
        job = jobs.iniciar(tipo, descricao, fn, execucao_id)
        return JSONResponse({"job_id": job.id, "execucao_id": execucao_id}, status_code=202)

    api = "/api/v1"

    # ── project ─────────────────────────────────────────────────────────────

    @app.get(f"{api}/projeto")
    def projeto_info():
        def f(c):
            info = info_projeto(c)
            cont = {r[0]: r[1] for r in c.execute("SELECT status, count(*) FROM artigo GROUP BY status")}
            cb_row = cbk.linha_codebook(c)
            cong = cbk.ultimo_congelado(c)
            ult = c.execute("SELECT id FROM execucao WHERE tipo!='teste' ORDER BY id DESC LIMIT 1").fetchone()
            ult_conc = c.execute("SELECT id FROM execucao WHERE tipo!='teste' AND status='concluida' "
                                 "ORDER BY id DESC LIMIT 1").fetchone()
            fila = len(adj.fila(c, ult_conc[0], ocultos=pil.artigos_ocultos(c))) if ult_conc else 0
            tot = consumo(c)["total"]
            return {
                "nome": info.get("nome"), "pergunta": info.get("pergunta"), "tipo_revisao": info.get("tipo_revisao"),
                "raiz": str(projeto.raiz), "versao_lutz": __version__,
                "artigos": {"total": sum(cont.values()), "prontos": cont.get("pronto", 0),
                            "sem_texto": cont.get("sem_texto", 0), "erro": cont.get("erro", 0),
                            "duas_colunas": c.execute("SELECT count(*) FROM artigo WHERE duas_colunas=1").fetchone()[0]},
                "codebook": {k: cb_row[k] for k in ("versao", "hash", "congelado")} if cb_row else None,
                "codebook_congelado": {k: cong[k] for k in ("versao", "hash")} if cong else None,
                "ultima_execucao": ex.resumo(c, ult[0]) if ult else None,
                "ultima_concluida": ult_conc[0] if ult_conc else None,
                "fila_adjudicacao": fila,
                "piloto": (lambda p: {"id": p["id"], "sorteado": bool(p["sorteado_em"]),
                                      "cegamento_aberto": bool(p["cegamento_aberto"])} if p else None)(pil.atual(c)),
                "consumo": {"chamadas": tot["chamadas"], "custo_usd": tot["custo_usd"] or 0,
                            "tokens": (tot["tokens_entrada"] or 0) + (tot["tokens_saida"] or 0)},
            }
        return ler(f)

    @app.put(f"{api}/projeto")
    def projeto_atualizar(body: dict):
        campos = {k: v for k, v in body.items() if k in ("nome", "pergunta", "tipo_revisao")}

        def f(c):
            for k, v in campos.items():
                c.execute(f"UPDATE projeto SET {k}=? WHERE id=1", (str(v),))
            return info_projeto(c)
        return escrever("projeto", f)

    # ── library ─────────────────────────────────────────────────────────────

    @app.get(f"{api}/artigos")
    def artigos():
        def f(c):
            out = []
            for a in c.execute("SELECT * FROM artigo ORDER BY chave"):
                d = dict(a)
                d["secoes"] = jload(d["secoes"], [])
                d["legibilidade"] = legibilidade(d)
                d.pop("hash_pdf", None)
                out.append(d)
            return out
        return ler(f)

    @app.post(f"{api}/artigos", status_code=202)
    async def importar(arquivos: list[UploadFile] = File(...)):
        tmp = Path(tempfile.mkdtemp(prefix="lutz-upload-"))
        caminhos = []
        for i, up in enumerate(arquivos):
            nome = Path(up.filename or f"arquivo{i}.pdf").name
            destino = tmp / f"{i:04d}_{nome}"
            destino.write_bytes(await up.read())
            caminhos.append(destino)

        def tarefa(publicar, parar):
            c = con()
            res = []
            try:
                publicar({"tipo": "inicio", "total": len(caminhos)})
                for p in caminhos:
                    if parar.is_set():
                        break
                    r = importar_pdf(projeto, c, p)
                    item = {"arquivo": p.name.split("_", 1)[-1], "status": r.status, "chave": r.chave,
                            "mensagem": r.mensagem}
                    res.append(item)
                    publicar({"tipo": "artigo", **item})
            finally:
                c.close()
                for p in caminhos:
                    p.unlink(missing_ok=True)
            return res
        return iniciar_job("importacao", f"importar {len(caminhos)} PDF(s)", tarefa)

    @app.get(f"{api}/artigos/{{chave}}")
    def artigo(chave: str):
        def f(c):
            a = um(c, "SELECT * FROM artigo WHERE chave=?", (chave,))
            if a is None:
                raise HTTPException(404, "artigo não encontrado")
            a["secoes"] = jload(a["secoes"], [])
            a["paginas"] = [dict(r) for r in c.execute(
                "SELECT numero, rotulo, n_chars, frac_oculto, secao FROM pagina WHERE artigo_id=? ORDER BY numero",
                (a["id"],))]
            return a
        return ler(f)

    @app.get(f"{api}/artigos/{{chave}}/paginas/{{n}}")
    def pagina(chave: str, n: int):
        def f(c):
            a = um(c, "SELECT id FROM artigo WHERE chave=?", (chave,))
            if a is None:
                raise HTTPException(404, "artigo não encontrado")
            p = um(c, "SELECT * FROM pagina WHERE artigo_id=? AND numero=?", (a["id"], n))
            if p is None:
                raise HTTPException(404, "página não encontrada")
            p["texto"] = projeto.abs(p["caminho_texto"]).read_text(encoding="utf-8")
            p["unidades"] = [dict(r) for r in c.execute(
                "SELECT uid, tipo, secao, texto FROM unidade WHERE artigo_id=? AND pagina=? ORDER BY ordem", (a["id"], n))]
            return p
        return ler(f)

    @app.get(f"{api}/artigos/{{chave}}/pdf")
    def pdf(chave: str):
        c = con()
        try:
            a = um(c, "SELECT caminho_pdf FROM artigo WHERE chave=?", (chave,))
        finally:
            c.close()
        if a is None:
            raise HTTPException(404, "artigo não encontrado")
        return FileResponse(projeto.abs(a["caminho_pdf"]), media_type="application/pdf")

    # ── codebook ────────────────────────────────────────────────────────────

    def _codebook_payload(c, versao=None):
        row = cbk.linha_codebook(c, versao)
        if row is None:
            return None
        cb = cbk.carregar(c, row["versao"])
        testados = {r[0] for r in c.execute("SELECT DISTINCT campo_chave FROM teste_rapido")}
        return {"versao": row["versao"], "hash": row["hash"], "congelado": bool(row["congelado"]),
                "origem": row["origem"], "nota": row["nota"], "criado_em": row["criado_em"],
                "descricao": cb.descricao, "campos": [c_.model_dump(mode="json") | {"hash": c_.hash(),
                                                                                   "testado": c_.nome in testados}
                                                      for c_ in cb.campos],
                "lint": cbk.lint(cb), "yaml": cb.para_yaml()}

    @app.get(f"{api}/codebooks")
    def codebooks():
        return ler(lambda c: cbk.historico(c))

    @app.get(f"{api}/codebooks/atual")
    def codebook_atual():
        return ler(lambda c: _codebook_payload(c))

    @app.get(f"{api}/codebooks/diff")
    def codebook_diff(v1: int, v2: int):
        return ler(lambda c: cbk.diff(c, v1, v2))

    @app.get(f"{api}/codebooks/{{versao}}")
    def codebook_versao(versao: int):
        r = ler(lambda c: _codebook_payload(c, versao))
        if r is None:
            raise HTTPException(404, "versão não encontrada")
        return r

    @app.put(f"{api}/codebooks/rascunho")
    def codebook_rascunho(body: dict):
        cb = cbk.de_dict({"campos": body.get("campos", []), "descricao": body.get("descricao", "")})
        origem = "assistente" if any(c.origem == "assistente" for c in cb.campos) else "manual"
        return escrever("codebook", lambda c: (cbk.salvar_rascunho(c, cb, origem=origem, nota=body.get("nota", "")),
                                                _codebook_payload(c))[1])

    @app.post(f"{api}/codebooks/importar")
    def codebook_importar(body: dict):
        cb = cbk.ler_yaml(body.get("yaml", ""))
        return escrever("codebook", lambda c: (cbk.salvar_rascunho(c, cb, nota=body.get("nota", "")),
                                                _codebook_payload(c))[1])

    @app.post(f"{api}/codebooks/lint")
    def codebook_lint(body: dict, semantico: bool = False):
        cb = cbk.de_dict({"campos": body.get("campos", []), "descricao": body.get("descricao", "")})
        achados = cbk.lint(cb)
        if semantico:
            achados += assistente.lint_semantico(projeto, carregar_settings(projeto), cb)
        return {"achados": achados, "erros": cbk.tem_erros(achados)}

    @app.post(f"{api}/codebooks/congelar")
    def codebook_congelar(body: dict | None = None):
        versao = (body or {}).get("versao")
        return escrever("codebook", lambda c: (cbk.congelar(c, versao), _codebook_payload(c, versao))[1])

    @app.get(f"{api}/assistente/modelos")
    def assistente_modelos():
        return [{"id": k, "rotulo": v["rotulo"], "n_campos": len(v["campos"])} for k, v in assistente.MODELOS.items()]

    @app.post(f"{api}/assistente/modelo")
    def assistente_modelo(body: dict):
        return {"campos": [c.model_dump(mode="json") for c in assistente.modelo_de_partida(body.get("area", ""))]}

    @app.post(f"{api}/assistente/sugestoes")
    def assistente_sugestoes(body: dict):
        r = assistente.sugerir_campos(projeto, carregar_settings(projeto), pergunta=body.get("pergunta", ""),
                                      componentes=body.get("componentes") or {}, variaveis=body.get("variaveis") or [],
                                      tipo_revisao=body.get("tipo_revisao", "sistematica"),
                                      existentes=body.get("existentes") or [])
        return {"campos": [c.model_dump(mode="json") for c in r["campos"]], "descartados": r["descartados"]}

    @app.post(f"{api}/codebooks/teste", status_code=202)
    def codebook_teste(body: dict):
        campos = body.get("campos") or []
        n = int(body.get("n", 3))
        s = carregar_settings(projeto)

        def tarefa(publicar, parar):
            c = con()
            try:
                chaves = body.get("artigos") or [r[0] for r in c.execute(
                    "SELECT chave FROM artigo WHERE status='pronto' ORDER BY id LIMIT ?", (n,))]
                eid = ex.planejar(projeto, c, s, tipo="teste", campos=campos, artigos=chaves)
                est = ex.estimar(projeto, c, eid)
                publicar({"tipo": "estimativa", **est})
                ex.executar(projeto, eid, progresso=publicar, parar=parar)
                linhas = []
                for r in c.execute("""SELECT a.chave, c.campo_chave, c.valor_final, c.nao_reportado, c.trecho, c.pagina,
                                      c.e, b.e_detalhe, b.erro, b.regras_detalhe FROM celula c JOIN artigo a ON a.id=c.artigo_id
                                      LEFT JOIN extracao_bruta b ON b.celula_id=c.id WHERE c.execucao_id=?""", (eid,)):
                    linhas.append(dict(r))
                return {"execucao_id": eid, "estimativa": est, "resultados": linhas}
            finally:
                c.close()
        return iniciar_job("teste", f"teste rápido: {', '.join(campos)}", tarefa)

    # ── runs ────────────────────────────────────────────────────────────────

    @app.get(f"{api}/execucoes")
    def execucoes():
        return ler(lambda c: [ex.resumo(c, r[0]) for r in c.execute("SELECT id FROM execucao ORDER BY id DESC")])

    @app.post(f"{api}/execucoes/estimativa")
    def execucao_estimar(body: dict):
        """Plans a run (status 'planejada') and returns its cost estimate. Nothing runs yet."""
        s = carregar_settings(projeto)

        def f(c):
            conjunto = body.get("conjunto")
            p = pil.atual(c) if conjunto else None
            eid = ex.planejar(projeto, c, s, campos=body.get("campos"), artigos=body.get("artigos"),
                              piloto_id=p["id"] if p else None, conjunto=conjunto, forcar=bool(body.get("forcar")))
            return ex.estimar(projeto, c, eid)
        return escrever("planejar execução", f)

    @app.post(f"{api}/execucoes/{{eid}}/iniciar", status_code=202)
    def execucao_iniciar(eid: int, body: dict | None = None):
        def tarefa(publicar, parar):
            return ex.executar(projeto, eid, progresso=publicar, parar=parar)
        if (body or {}).get("confirmar") is not True and carregar_settings(projeto).custo.confirmar:
            raise LutzError("Confirme o custo estimado antes de iniciar (envie {\"confirmar\": true}).")
        return iniciar_job("extracao", f"execução {eid}", tarefa, execucao_id=eid)

    @app.post(f"{api}/execucoes/{{eid}}/pausar")
    def execucao_pausar(eid: int):
        for j in jobs.jobs.values():
            if j.execucao_id == eid and j.status == "rodando":
                j.parar.set()
        c = con()
        try:
            ex.pausar(c, eid)
            return _limpo(ex.resumo(c, eid))
        finally:
            c.close()

    @app.post(f"{api}/execucoes/{{eid}}/recalcular", status_code=202)
    def execucao_recalcular(eid: int, body: dict | None = None):
        atuais = bool((body or {}).get("limiares_atuais"))
        return iniciar_job("recalculo", f"recalcular execução {eid}",
                           lambda pub, parar: ex.recalcular(projeto, eid, usar_limiares_atuais=carregar_settings(projeto)
                                                            if atuais else None), execucao_id=eid)

    @app.get(f"{api}/execucoes/{{eid}}")
    def execucao(eid: int):
        def f(c):
            r = ex.resumo(c, eid)
            e = um(c, "SELECT * FROM execucao WHERE id=?", (eid,))
            r["extratores"] = [dict(x) for x in c.execute("SELECT * FROM extrator WHERE execucao_id=? ORDER BY rotulo",
                                                          (eid,))]
            obs = {x["rotulo"]: x["modelo_observado"] for x in consumo(c, eid)["por_papel"]}
            for x in r["extratores"]:
                x["modelo_observado"] = obs.get(x["rotulo"], "")
            r["campos"] = jload(e["campos"])
            r["hash_config"], r["hash_prompts"], r["versao_lutz"] = e["hash_config"], e["hash_prompts"], e["versao_lutz"]
            r["codebook"] = um(c, "SELECT versao, hash FROM codebook WHERE id=?", (e["codebook_id"],))
            r["orcamento_usd"] = jload(e["config"])["custo"]["orcamento_usd"]
            r["job"] = next((j.publico() for j in jobs.jobs.values() if j.execucao_id == eid and j.status == "rodando"),
                            None)
            return r
        return ler(f)

    @app.get(f"{api}/execucoes/{{eid}}/estimativa")
    def execucao_estimativa(eid: int):
        return ler(lambda c: ex.estimar(projeto, c, eid))

    @app.get(f"{api}/execucoes/{{eid}}/metricas")
    def execucao_metricas(eid: int):
        def f(c):
            m = metricas(c, eid)
            campos = {r["chave"]: dict(r) for r in c.execute(
                "SELECT cp.chave, cp.rotulo, cp.tipo FROM campo cp JOIN execucao e ON e.codebook_id=cp.codebook_id "
                "WHERE e.id=? ORDER BY cp.ordem", (eid,))}
            return {"campos": [{**info, "metricas": m.get(k, {})} for k, info in campos.items()],
                    "geral": m.get(None, {})}
        return ler(f)

    @app.get(f"{api}/execucoes/{{eid}}/checagens")
    def execucao_checagens(eid: int):
        def f(c):
            cel = [dict(r) for r in c.execute("SELECT a, e, v, nivel, regras_ok, valor_final, nao_reportado, escore "
                                              "FROM celula WHERE execucao_id=? AND nivel IS NOT NULL", (eid,))]
            com_valor = [x for x in cel if not x["nao_reportado"] and x["valor_final"] is not None]
            tot = len(cel) or 1
            tv = len(com_valor) or 1
            vs = [x for x in cel if x["v"] is not None]
            return {
                "celulas": len(cel),
                "concordancia": {"unanimes": sum(1 for x in cel if (x["a"] or 0) >= 0.999),
                                 "dois_de_tres": sum(1 for x in cel if 0.6 < (x["a"] or 0) < 0.999),
                                 "empates": sum(1 for x in cel if x["escore"] is None)},
                "evidencia": {"exata": sum(1 for x in com_valor if (x["e"] or 0) >= 1) / tv,
                              "parcial": sum(1 for x in com_valor if x["e"] == 0.5) / tv,
                              "nao_encontrada": sum(1 for x in com_valor if (x["e"] or 0) == 0) / tv},
                "verificador": {"sustenta": sum(1 for x in vs if x["v"] == 1) / (len(vs) or 1),
                                "parcial": sum(1 for x in vs if x["v"] == 0.5) / (len(vs) or 1),
                                "nao_sustenta": sum(1 for x in vs if x["v"] == 0) / (len(vs) or 1),
                                "n": len(vs)},
                "regras_barradas": sum(1 for x in cel if x["regras_ok"] == 0),
                "niveis": {n: sum(1 for x in cel if x["nivel"] == n) for n in ("alta", "media", "baixa")},
                "pct_niveis": {n: sum(1 for x in cel if x["nivel"] == n) / tot for n in ("alta", "media", "baixa")},
            }
        return ler(f)

    @app.get(f"{api}/execucoes/{{eid}}/log")
    def execucao_log(eid: int, limite: int = 50):
        def f(c):
            ocultos = pil.artigos_ocultos(c)
            out = []
            for r in c.execute("""SELECT c.id, c.artigo_id, a.chave, c.campo_chave, c.valor_final, c.nao_reportado, c.nivel,
                                  c.a, c.e, c.v, c.pagina, c.estado, c.motivos, c.atualizada_em FROM celula c
                                  JOIN artigo a ON a.id=c.artigo_id WHERE c.execucao_id=? AND c.atualizada_em IS NOT NULL
                                  ORDER BY c.atualizada_em DESC, c.id DESC LIMIT ?""", (eid, limite)):
                d = dict(r)
                if d["artigo_id"] in ocultos:
                    continue
                d["motivos"] = jload(d["motivos"], [])
                out.append(d)
            return out
        return ler(f)

    # ── results and cells ───────────────────────────────────────────────────

    @app.get(f"{api}/execucoes/{{eid}}/tabela")
    def tabela(eid: int, nivel: str | None = None, campo: str | None = None):
        def f(c):
            ocultos = pil.artigos_ocultos(c)
            campos = [dict(r) for r in c.execute(
                """SELECT cp.chave, cp.rotulo, cp.tipo FROM campo cp JOIN execucao e ON e.codebook_id=cp.codebook_id
                   WHERE e.id=? AND cp.chave IN (SELECT value FROM json_each(e.campos)) ORDER BY cp.ordem""", (eid,))]
            linhas: dict[int, dict] = {}
            n_oc = 0
            for r in c.execute("""SELECT c.*, a.chave, a.titulo, a.autores, a.ano FROM celula c JOIN artigo a ON a.id=c.artigo_id
                                  WHERE c.execucao_id=? ORDER BY a.chave""", (eid,)):
                if r["artigo_id"] in ocultos:
                    n_oc += 1
                    continue
                if campo and r["campo_chave"] != campo:
                    continue
                ln = linhas.setdefault(r["artigo_id"], {"artigo": r["chave"], "titulo": r["titulo"],
                                                         "autores": r["autores"], "ano": r["ano"], "celulas": {}})
                ln["celulas"][r["campo_chave"]] = {
                    "id": r["id"], "valor": r["valor_final"], "nao_reportado": bool(r["nao_reportado"]),
                    "nivel": r["nivel"], "origem": r["origem"], "pagina": r["pagina"], "escore": r["escore"],
                    "estado": r["estado"]}
            lista = list(linhas.values())
            if nivel:
                lista = [x for x in lista if any(cel["nivel"] == nivel for cel in x["celulas"].values())]
            return {"campos": campos, "linhas": lista, "ocultos_piloto": n_oc}
        return ler(f)

    @app.get(f"{api}/execucoes/{{eid}}/exportar.csv")
    def exportar_csv(eid: int, formato: str = "largo"):
        def f(c):
            if pil.artigos_ocultos(c) & set(jload(um(c, "SELECT artigos FROM execucao WHERE id=?", (eid,))["artigos"])):
                raise EstadoInvalido("Há artigos do piloto cego nesta execução.")
            cab, linhas = (tabela_larga if formato == "largo" else tabela_longa)(c, eid)
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(cab)
            w.writerows([["" if x is None else x for x in ln] for ln in linhas])
            return buf.getvalue()
        texto = ler(f)
        return Response("﻿" + texto, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="resultados_{eid}_{formato}.csv"'})

    def _celula_visivel(c, cid: int):
        r = um(c, "SELECT artigo_id FROM celula WHERE id=?", (cid,))
        if r is None:
            raise HTTPException(404, "célula não encontrada")
        if r["artigo_id"] in pil.artigos_ocultos(c):
            raise EstadoInvalido("Célula de artigo do piloto cego: oculta até a importação das planilhas humanas.")

    @app.get(f"{api}/celulas/{{cid}}")
    def celula(cid: int):
        def f(c):
            _celula_visivel(c, cid)
            d = adj.detalhe_celula(c, cid)
            d["unidades_texto"] = [dict(r) for r in c.execute(
                f"SELECT uid, pagina, tipo, texto FROM unidade WHERE artigo_id=? AND uid IN "
                f"({','.join('?' * len(d['unidades']))})", (d["artigo_id"], *d["unidades"]))] if d["unidades"] else []
            return d
        return ler(f)

    @app.post(f"{api}/celulas/{{cid}}/enviar")
    def celula_enviar(cid: int, body: dict | None = None):
        def f(c):
            _celula_visivel(c, cid)
            adj.enviar_manual(c, cid, (body or {}).get("nota", ""))
            return {"ok": True}
        return escrever("enviar célula", f)

    # ── adjudication and audit ──────────────────────────────────────────────

    @app.get(f"{api}/execucoes/{{eid}}/fila")
    def fila(eid: int, decididas: bool = False):
        def f(c):
            itens = adj.fila(c, eid, incluir_decididas=decididas, ocultos=pil.artigos_ocultos(c))
            for it in itens:
                it["brutas"] = [{k: b[k] for k in ("rotulo", "status", "valor", "valor_normalizado", "nao_reportado",
                                                   "e", "e_detalhe", "trecho", "pagina", "erro")}
                                for b in adj.brutas(c, it["id"])]
            return itens
        return ler(f)

    @app.get(f"{api}/execucoes/{{eid}}/adjudicacao/estatisticas")
    def adj_estatisticas(eid: int):
        def f(c):
            r = adj.estatisticas(c, eid)
            r["auditoria"] = aud.resultado(c, eid)
            return r
        return ler(f)

    @app.post(f"{api}/adjudicacoes")
    def adjudicar(body: dict):
        cid = int(body["celula_id"])

        def f(c):
            _celula_visivel(c, cid)
            return adj.decidir(c, cid, valor=body.get("valor"), nao_reportado=bool(body.get("nao_reportado")),
                               justificativa=body.get("justificativa", ""))
        return escrever("adjudicação", f)

    @app.get(f"{api}/execucoes/{{eid}}/adjudicacao.csv")
    def adj_csv(eid: int):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "adj.csv"
            ler(lambda c: adj.exportar_csv(c, eid, destino, ocultos=pil.artigos_ocultos(c)))
            dados = destino.read_bytes()
        return Response(dados, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="adjudicacao_{eid}.csv"'})

    @app.post(f"{api}/adjudicacao/importar")
    async def adj_importar(arquivo: UploadFile = File(...)):
        dados = await arquivo.read()
        return escrever("importar adjudicação", lambda c: adj.importar_csv(c, dados))

    @app.post(f"{api}/execucoes/{{eid}}/auditoria")
    def auditoria_criar(eid: int, body: dict | None = None):
        n = (body or {}).get("n")
        return escrever("auditoria", lambda c: aud.criar(c, eid, carregar_settings(projeto), n=n,
                                                         ocultos=pil.artigos_ocultos(c)))

    @app.get(f"{api}/execucoes/{{eid}}/auditoria")
    def auditoria(eid: int):
        def f(c):
            a = aud.atual(c, eid)
            if a is None:
                n_alta = c.execute("SELECT count(*) FROM celula WHERE execucao_id=? AND nivel='alta'", (eid,)).fetchone()[0]
                s = carregar_settings(projeto)
                return {"auditoria": None, "n_alta": n_alta,
                        "n_sugerido": min(n_alta, M.n_para_meia_largura(s.auditoria.meia_largura_alvo,
                                                                          s.auditoria.p_esperado))}
            return {"auditoria": a, "resultado": aud.resultado(c, eid), "itens": aud.itens(c, a["id"])}
        return ler(f)

    @app.post(f"{api}/auditoria/itens/{{item_id}}")
    def auditoria_item(item_id: int, body: dict):
        return escrever("auditoria", lambda c: (aud.registrar(c, item_id, bool(body.get("correto")),
                                                              body.get("valor_correto"),
                                                              bool(body.get("nao_reportado_correto")),
                                                              body.get("nota", "")), {"ok": True})[1])

    # ── pilot ───────────────────────────────────────────────────────────────

    @app.get(f"{api}/piloto")
    def piloto():
        def f(c):
            n_corpus = c.execute("SELECT count(*) FROM artigo WHERE status='pronto'").fetchone()[0]
            st = pil.estado(c)
            return {"estado": st, "n_corpus": n_corpus, "tamanho": M.tabela_tamanho_piloto(),
                    "avisos": pil.avisos_plano(n_corpus, st["piloto"]["n_validacao"]) if st else
                    pil.avisos_plano(n_corpus, 20)}
        return ler(f)

    @app.post(f"{api}/piloto/plano")
    def piloto_plano(body: dict):
        s = carregar_settings(projeto)

        def f(c):
            p = pil.planejar(c, s, n_ajuste=int(body.get("n_ajuste", 10)), n_validacao=int(body.get("n_validacao", 20)),
                             n_reserva=int(body.get("n_reserva", 0)), estratos=body.get("estratos", ""),
                             avaliadores=body.get("avaliadores") or ["A", "B"])
            return p | {"plano": jload(p["plano"]), "avaliadores": jload(p["avaliadores"])}
        return escrever("piloto", f)

    @app.post(f"{api}/piloto/sorteio")
    def piloto_sorteio():
        return escrever("piloto", lambda c: pil.sortear(c, pil.atual(c)["id"]))

    @app.get(f"{api}/piloto/planilha/{{avaliador}}.csv")
    def piloto_planilha(avaliador: str):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "p.csv"
            ler(lambda c: pil.exportar_planilha(c, pil.atual(c)["id"], avaliador, destino))
            dados = destino.read_bytes()
        return Response(dados, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="piloto_{avaliador}.csv"'})

    @app.post(f"{api}/piloto/importacao")
    async def piloto_importacao(avaliador: str = Form(...), arquivo: UploadFile = File(...)):
        dados = await arquivo.read()
        return escrever("piloto", lambda c: pil.importar_planilha(c, pil.atual(c)["id"], avaliador, dados))

    @app.get(f"{api}/piloto/formulario/{{avaliador}}")
    def piloto_formulario(avaliador: str):
        return ler(lambda c: pil.formulario(c, pil.atual(c)["id"], avaliador))

    @app.post(f"{api}/piloto/respostas")
    def piloto_resposta(body: dict):
        return escrever("piloto", lambda c: pil.salvar_resposta(
            c, pil.atual(c)["id"], body["avaliador"], body["artigo"], body["campo"], body.get("valor"),
            bool(body.get("nao_reportado")), body.get("pagina")))

    @app.get(f"{api}/piloto/consenso.csv")
    def piloto_consenso_csv():
        s = carregar_settings(projeto)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "c.csv"
            ler(lambda c: pil.exportar_consenso(c, pil.atual(c)["id"], destino, s))
            dados = destino.read_bytes()
        return Response(dados, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="consenso.csv"'})

    @app.post(f"{api}/piloto/consenso")
    async def piloto_consenso(arquivo: UploadFile = File(...)):
        dados = await arquivo.read()
        s = carregar_settings(projeto)
        return escrever("piloto", lambda c: pil.importar_consenso(c, pil.atual(c)["id"], dados, s))

    @app.post(f"{api}/piloto/comparacao")
    def piloto_comparacao(body: dict):
        s = carregar_settings(projeto)
        return escrever("piloto", lambda c: pil.comparar(c, pil.atual(c)["id"], body.get("conjunto", "validacao"), s))

    # ── reports ─────────────────────────────────────────────────────────────

    @app.get(f"{api}/relatorios")
    def relatorios():
        def f(c):
            out = []
            for r in c.execute("SELECT DISTINCT execucao_id FROM relatorio ORDER BY execucao_id DESC"):
                pasta = projeto.relatorios / f"execucao-{r[0]:04d}"
                out.append({"execucao_id": r[0], "arquivos": sorted(p.name for p in pasta.glob("*")) if pasta.exists() else [],
                            "gerado_em": c.execute("SELECT max(gerado_em) FROM relatorio WHERE execucao_id=?",
                                                   (r[0],)).fetchone()[0]})
            return out
        return ler(f)

    @app.post(f"{api}/relatorios", status_code=202)
    def relatorio_gerar(body: dict):
        eid = int(body["execucao_id"])

        def tarefa(publicar, parar):
            c = con()
            try:
                return gerar(projeto, c, eid, idiomas=body.get("idiomas"), formatos=body.get("formatos"))
            finally:
                c.close()
        return iniciar_job("relatorio", f"relatório da execução {eid}", tarefa, execucao_id=eid)

    @app.get(f"{api}/relatorios/{{eid}}/previa")
    def relatorio_previa(eid: int, idioma: str = "pt"):
        def f(c):
            d = coletar(projeto, c, eid)
            return {"markdown": render.markdown(d, "en" if idioma == "en" else "pt")}
        return ler(f)

    @app.get(f"{api}/relatorios/{{eid}}/arquivos/{{nome}}")
    def relatorio_arquivo(eid: int, nome: str):
        if not re.fullmatch(r"[\w.\-]+", nome):
            raise HTTPException(400, "nome inválido")
        p = projeto.relatorios / f"execucao-{eid:04d}" / nome
        if not p.is_file():
            raise HTTPException(404, "arquivo não encontrado")
        return FileResponse(p, filename=nome)

    # ── jobs ────────────────────────────────────────────────────────────────

    @app.get(f"{api}/jobs")
    def listar_jobs():
        return _limpo(jobs.listar())

    @app.get(f"{api}/jobs/{{job_id}}")
    def job(job_id: str):
        j = jobs.obter(job_id)
        if j is None:
            raise HTTPException(404, "job não encontrado")
        d = j.publico()
        d["resultado"] = j.resultado
        d["eventos"] = j.eventos[-200:]
        return _limpo(d)

    @app.get(f"{api}/jobs/{{job_id}}/eventos")
    async def job_eventos(job_id: str):
        j = jobs.obter(job_id)
        if j is None:
            raise HTTPException(404, "job não encontrado")

        async def fluxo():
            i = 0
            while True:
                while i < len(j.eventos):
                    yield f"data: {json.dumps(_limpo(j.eventos[i]), ensure_ascii=False, default=str)}\n\n"
                    i += 1
                if j.status != "rodando" and i >= len(j.eventos):
                    break
                await asyncio.sleep(0.3)
        return StreamingResponse(fluxo(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── configuration (kept from 0.5: .env read/write through the settings modal) ──

    @app.get(f"{api}/config")
    def config():
        texto = projeto.yaml.read_text(encoding="utf-8") if projeto.yaml.exists() else ""
        resumo: dict = {"valido": True, "erro": ""}
        try:
            s = validar_yaml(texto)
            papeis = [{"rotulo": r, **m.model_dump(mode="json"), "temperatura": m.temperatura_efetiva()}
                      for r, m in s.modelos.extratores().items()]
            for r in ("V", "J"):
                m = getattr(s.modelos, r)
                if m:
                    papeis.append({"rotulo": r, **m.model_dump(mode="json"), "temperatura": m.temperatura_efetiva()})
            resumo.update({"papeis": papeis, "estrategia": estrategia_diversidade(s.modelos), "avisos": avisos(s),
                           "hash": s.hash()[:16], "orcamento_usd": s.custo.orcamento_usd,
                           "idiomas": s.relatorio.idiomas, "formatos": s.relatorio.formatos,
                           "limiares": s.limiares.model_dump()})
        except ConfigInvalida as exc:
            resumo.update({"valido": False, "erro": str(exc)})
        return _limpo({"env": valores_com_origem(projeto), "lutz_yaml": {"caminho": str(projeto.yaml),
                                                                          "texto": texto, **resumo}})

    @app.put(f"{api}/config")
    def config_salvar(body: dict):
        mudancas = {k: (v if v not in ("",) else None) for k, v in body.items()}
        sombreadas = salvar_env(projeto, mudancas)
        return {"ok": True, "sombreadas": sombreadas}

    @app.get(f"{api}/consumo")
    def consumo_api(execucao: int | None = None, limite: int = 200):
        def f(c):
            r = consumo(c, execucao)
            filtro, params = ("WHERE l.execucao_id=?", (execucao,)) if execucao else ("", ())
            r["chamadas"] = [dict(x) for x in c.execute(
                f"""SELECT l.id, l.execucao_id, l.papel, l.rotulo, a.chave artigo, l.provedor, l.modelo_pedido,
                    l.modelo_observado, l.tokens_entrada, l.tokens_saida, l.custo_usd, l.latencia_ms, l.status,
                    l.cache, l.criado_em FROM chamada_llm l LEFT JOIN artigo a ON a.id=l.artigo_id {filtro}
                    ORDER BY l.id DESC LIMIT ?""", (*params, limite))]
            r["por_execucao"] = [dict(x) for x in c.execute(
                """SELECT execucao_id, count(*) chamadas, sum(tokens_entrada+tokens_saida) tokens, sum(custo_usd) custo_usd
                   FROM chamada_llm GROUP BY execucao_id ORDER BY execucao_id DESC""")]
            return r
        return ler(f)

    @app.get(f"{api}/consumo.csv")
    def consumo_csv():
        def f(c):
            buf = io.StringIO()
            w = csv.writer(buf)
            cols = ["id", "execucao_id", "papel", "rotulo", "provedor", "modelo_pedido", "modelo_observado",
                    "tokens_entrada", "tokens_saida", "custo_usd", "latencia_ms", "status", "cache", "criado_em"]
            w.writerow(cols)
            for r in c.execute(f"SELECT {', '.join(cols)} FROM chamada_llm ORDER BY id"):
                w.writerow(["" if x is None else x for x in r])
            return buf.getvalue()
        return Response("﻿" + ler(f), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="lutz_consumo.csv"'})

    @app.get(f"{api}/mcp")
    def mcp_info():
        from lutz.server.mcp import FERRAMENTAS

        cfg = {"mcpServers": {"lutz": {"command": "lutz", "args": ["mcp", "--projeto", str(projeto.raiz)]}}}
        return {"comando": f"lutz mcp --projeto {projeto.raiz}", "transporte": "stdio", "somente_leitura": True,
                "config_claude_desktop": cfg, "config_cursor": cfg,
                "config_vscode": {"servers": {"lutz": {"type": "stdio", "command": "lutz",
                                                       "args": ["mcp", "--projeto", str(projeto.raiz)]}}},
                "ferramentas": FERRAMENTAS, "openapi": "/api/docs"}

    @app.get("/api/v1")
    def raiz_api():
        return {"lutz": __version__, "docs": "/api/docs"}

    # ── SPA ─────────────────────────────────────────────────────────────────

    dist = _dist_web()
    if dist is not None:
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{caminho:path}", include_in_schema=False)
        def spa(caminho: str):
            if caminho.startswith("api/") or caminho == "api":
                raise HTTPException(404, "rota da API não encontrada")
            alvo = (dist / caminho).resolve()
            if caminho and alvo.is_file() and dist.resolve() in alvo.parents:
                return FileResponse(alvo)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def sem_spa():
            return PlainTextResponse("Interface web não empacotada. Em desenvolvimento: cd web && npm run build. "
                                     "A API está em /api/docs.")

    return app
