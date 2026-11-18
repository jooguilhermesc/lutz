"""MCP server (stdio), read-only.

Brings the project to the client the researcher already uses (Claude Desktop, Cursor, VS Code,
notebooks). Free-form questions happen there, not inside Lutz. No tool writes to the project:
extraction runs, adjudication and report generation stay in the CLI and the web interface.
Cells of a blind pilot stay hidden until the human sheets are imported.
"""

from __future__ import annotations

import math
from typing import Any

from rapidfuzz import fuzz

from lutz.calibrated import piloto as pil
from lutz.core import codebook as cbk
from lutz.core.db import conectar, um
from lutz.core.inicializar import info_projeto
from lutz.core.project import Projeto
from lutz.core.texto import normalizar
from lutz.extraction import executor as ex
from lutz.extraction.metricas_autonomo import metricas
from lutz.report import render
from lutz.report.dados import coletar
from lutz.revisao import adjudicacao as adj

FERRAMENTAS = [
    {"nome": "listar_projeto", "descricao": "Projeto, artigos, codebook ativo e execuções com status e custo."},
    {"nome": "ler_codebook", "descricao": "Codebook de uma versão: tipo, instrução, valores e regra de ausência."},
    {"nome": "consultar_celulas", "descricao": "Células com valor, nível de confiança, trecho e página; filtra por "
                                                "campo, nível e artigo."},
    {"nome": "detalhe_celula", "descricao": "Os três extratores, as checagens e as decisões de uma célula."},
    {"nome": "metricas_execucao", "descricao": "Alfa, % de níveis e evidência por campo de uma execução."},
    {"nome": "buscar_trechos", "descricao": "Busca textual nas frases e linhas de tabela, sempre com artigo e página."},
    {"nome": "ler_relatorio", "descricao": "Relatório de confiabilidade de uma execução, em Markdown."},
]


def _limpo(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if isinstance(obj, dict):
        return {k: _limpo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_limpo(v) for v in obj]
    return obj


def _ultima(c, execucao_id: int | None) -> int | None:
    if execucao_id:
        return execucao_id
    r = c.execute("SELECT id FROM execucao WHERE tipo!='teste' AND status='concluida' ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else None


class Ferramentas:
    """Plain functions (testable without an MCP client)."""

    def __init__(self, projeto: Projeto):
        self.projeto = projeto

    def _con(self):
        return conectar(self.projeto)

    def listar_projeto(self) -> dict:
        c = self._con()
        try:
            info = info_projeto(c)
            cb = cbk.linha_codebook(c)
            return _limpo({
                "nome": info.get("nome"), "pergunta": info.get("pergunta"),
                "artigos": [dict(r) for r in c.execute("SELECT chave, titulo, ano, status FROM artigo ORDER BY chave")],
                "codebook": {k: cb[k] for k in ("versao", "hash", "congelado")} if cb else None,
                "execucoes": [ex.resumo(c, r[0]) for r in c.execute("SELECT id FROM execucao ORDER BY id")],
            })
        finally:
            c.close()

    def ler_codebook(self, versao: int | None = None) -> dict:
        c = self._con()
        try:
            cb = cbk.carregar(c, versao)
            row = cbk.linha_codebook(c, cb.versao)
            return {"versao": cb.versao, "hash": row["hash"], "congelado": bool(row["congelado"]),
                    "campos": [x.model_dump(mode="json") for x in cb.campos]}
        finally:
            c.close()

    def consultar_celulas(self, campo: str | None = None, nivel: str | None = None, artigo: str | None = None,
                          execucao_id: int | None = None, limite: int = 100) -> dict:
        c = self._con()
        try:
            eid = _ultima(c, execucao_id)
            if eid is None:
                return {"execucao_id": None, "celulas": [], "nota": "nenhuma execução concluída"}
            ocultos = pil.artigos_ocultos(c)
            sql = """SELECT c.id, c.artigo_id, a.chave artigo, c.campo_chave campo, c.valor_final valor, c.nao_reportado,
                     c.nivel, c.escore, c.trecho, c.pagina, c.origem FROM celula c JOIN artigo a ON a.id=c.artigo_id
                     WHERE c.execucao_id=?"""
            params: list = [eid]
            if campo:
                sql += " AND c.campo_chave=?"
                params.append(campo)
            if nivel:
                sql += " AND c.nivel=?"
                params.append(nivel)
            if artigo:
                sql += " AND a.chave=?"
                params.append(artigo)
            sql += " ORDER BY a.chave, c.campo_chave LIMIT ?"
            params.append(max(1, min(int(limite), 1000)))
            linhas = []
            n_oc = 0
            for r in c.execute(sql, params):
                if r["artigo_id"] in ocultos:
                    n_oc += 1
                    continue
                d = dict(r)
                d.pop("artigo_id")
                d["nao_reportado"] = bool(d["nao_reportado"])
                linhas.append(d)
            return _limpo({"execucao_id": eid, "celulas": linhas, "ocultas_piloto_cego": n_oc})
        finally:
            c.close()

    def detalhe_celula(self, celula_id: int) -> dict:
        c = self._con()
        try:
            r = um(c, "SELECT artigo_id FROM celula WHERE id=?", (celula_id,))
            if r is None:
                return {"erro": "célula não encontrada"}
            if r["artigo_id"] in pil.artigos_ocultos(c):
                return {"erro": "célula de artigo do piloto cego: oculta até a importação das planilhas humanas"}
            d = adj.detalhe_celula(c, celula_id)
            d.pop("caminho_pdf", None)
            return _limpo(d)
        finally:
            c.close()

    def metricas_execucao(self, execucao_id: int | None = None) -> dict:
        c = self._con()
        try:
            eid = _ultima(c, execucao_id)
            if eid is None:
                return {"erro": "nenhuma execução concluída"}
            m = metricas(c, eid)
            return _limpo({"execucao_id": eid, "por_campo": {k: v for k, v in m.items() if k},
                           "geral": m.get(None, {}),
                           "nota": "alfa e % unânimes medem consistência entre extratores, não acerto"})
        finally:
            c.close()

    def buscar_trechos(self, consulta: str, artigo: str | None = None, limite: int = 10) -> dict:
        c = self._con()
        try:
            q = normalizar(consulta)
            termos = [t for t in q.split() if len(t) > 2]
            sql = "SELECT a.chave, u.uid, u.pagina, u.secao, u.texto FROM unidade u JOIN artigo a ON a.id=u.artigo_id"
            params: list = []
            if artigo:
                sql += " WHERE a.chave=?"
                params.append(artigo)
            res = []
            for r in c.execute(sql, params):
                t = normalizar(r["texto"])
                score = sum(1 for termo in termos if termo in t) / (len(termos) or 1)
                if score == 0:
                    continue
                score = 0.7 * score + 0.3 * fuzz.partial_ratio(q, t) / 100
                res.append((score, dict(r)))
            res.sort(key=lambda x: -x[0])
            return {"consulta": consulta, "resultados": [{"score": round(s, 3), **d}
                                                         for s, d in res[: max(1, min(int(limite), 50))]]}
        finally:
            c.close()

    def ler_relatorio(self, execucao_id: int | None = None, idioma: str = "pt") -> dict:
        c = self._con()
        try:
            eid = _ultima(c, execucao_id)
            if eid is None:
                return {"erro": "nenhuma execução concluída"}
            arq = self.projeto.relatorios / f"execucao-{eid:04d}" / f"relatorio_{idioma}.md"
            if arq.exists():
                return {"execucao_id": eid, "fonte": str(arq), "markdown": arq.read_text(encoding="utf-8")}
            return {"execucao_id": eid, "fonte": "prévia (relatório ainda não gerado)",
                    "markdown": render.markdown(coletar(self.projeto, c, eid), "en" if idioma == "en" else "pt")}
        except Exception as exc:  # noqa: BLE001 - reported to the client
            return {"erro": str(exc)}
        finally:
            c.close()


def servidor(projeto: Projeto):
    from mcp.server.mcpserver import MCPServer

    f = Ferramentas(projeto)
    s = MCPServer("lutz", instructions=(
        "Lutz: tabela de extração validada de uma revisão sistemática. Somente leitura. Cada célula tem valor, "
        "nível de confiança (alta, media, baixa), trecho literal e página. O alfa mede consistência entre "
        "extratores, não acerto; o acerto vem do piloto ou da auditoria."))

    @s.tool(description=FERRAMENTAS[0]["descricao"])
    def listar_projeto() -> dict:
        return f.listar_projeto()

    @s.tool(description=FERRAMENTAS[1]["descricao"])
    def ler_codebook(versao: int | None = None) -> dict:
        return f.ler_codebook(versao)

    @s.tool(description=FERRAMENTAS[2]["descricao"])
    def consultar_celulas(campo: str | None = None, nivel: str | None = None, artigo: str | None = None,
                          execucao_id: int | None = None, limite: int = 100) -> dict:
        return f.consultar_celulas(campo, nivel, artigo, execucao_id, limite)

    @s.tool(description=FERRAMENTAS[3]["descricao"])
    def detalhe_celula(celula_id: int) -> dict:
        return f.detalhe_celula(celula_id)

    @s.tool(description=FERRAMENTAS[4]["descricao"])
    def metricas_execucao(execucao_id: int | None = None) -> dict:
        return f.metricas_execucao(execucao_id)

    @s.tool(description=FERRAMENTAS[5]["descricao"])
    def buscar_trechos(consulta: str, artigo: str | None = None, limite: int = 10) -> dict:
        return f.buscar_trechos(consulta, artigo, limite)

    @s.tool(description=FERRAMENTAS[6]["descricao"])
    def ler_relatorio(execucao_id: int | None = None, idioma: str = "pt") -> dict:
        return f.ler_relatorio(execucao_id, idioma)

    return s
