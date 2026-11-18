"""Health check of a project: configuration, keys, providers, database and web assets."""

from __future__ import annotations

from importlib import resources

import pymupdf

from lutz import __version__
from lutz.config.env import carregar_env
from lutz.config.settings import ModeloPapel, avisos, carregar_settings, estrategia_diversidade
from lutz.core.db import VERSAO_SCHEMA, conectar
from lutz.core.errors import LutzError
from lutz.core.lock import ler_lock
from lutz.core.project import Projeto
from lutz.llm.cliente import ClienteLLM, preco_de, tabela_precos
from lutz.llm.provedores import Requisicao

CHAVE_POR_PROVEDOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                      "openrouter": "OPENROUTER_API_KEY"}


def verificar(projeto: Projeto, chamar: bool = False) -> list[dict]:
    """Returns a list of {item, status: ok|aviso|erro, detalhe}."""
    out: list[dict] = []

    def add(item, status, detalhe=""):
        out.append({"item": item, "status": status, "detalhe": detalhe})

    add("Lutz", "ok", __version__)
    add("PyMuPDF", "ok", pymupdf.__version__ if hasattr(pymupdf, "__version__") else pymupdf.VersionBind)
    try:
        s = carregar_settings(projeto)
        add("lutz.yaml", "ok", f"diversidade: {estrategia_diversidade(s.modelos)}")
        for a in avisos(s):
            add("lutz.yaml", "aviso", a)
    except LutzError as exc:
        add("lutz.yaml", "erro", str(exc))
        return out
    env = carregar_env(projeto)
    precos = tabela_precos(s)
    papeis: list[tuple[str, ModeloPapel]] = list(s.modelos.extratores().items())
    if s.modelos.V:
        papeis.append(("V", s.modelos.V))
    if s.modelos.J:
        papeis.append(("J", s.modelos.J))
    for rot, m in papeis:
        chave = CHAVE_POR_PROVEDOR.get(m.provedor)
        if chave and not env.get(chave):
            add(f"{rot} ({m.provedor})", "erro", f"falta {chave} no .env")
        elif preco_de(m, precos) is None:
            add(f"{rot} ({m.modelo})", "aviso", "preço desconhecido: custo não será estimado (defina em 'precos')")
        else:
            add(f"{rot} ({m.modelo})", "ok", m.provedor)
    try:
        con = conectar(projeto)
        v = con.execute("PRAGMA user_version").fetchone()[0]
        add("Banco lutz.db", "ok", f"esquema {v}/{VERSAO_SCHEMA}")
        interrompidas = [r[0] for r in con.execute("SELECT id FROM execucao WHERE status='rodando'")]
        lk = ler_lock(projeto)
        if interrompidas and not lk:
            add("Execuções", "aviso", f"execuções marcadas como rodando sem processo: {interrompidas} "
                                      "(retome com 'lutz extract --retomar ID')")
        con.close()
    except LutzError as exc:
        add("Banco lutz.db", "erro", str(exc))
    lk = ler_lock(projeto)
    if lk:
        add("Bloqueio", "aviso", f"em uso por PID {lk.get('pid')} ({lk.get('comando')})")
    try:
        web = resources.files("lutz").joinpath("web", "index.html")
        add("Interface web", "ok" if web.is_file() else "aviso",
            "" if web.is_file() else "SPA não empacotada (rode 'cd web && npm run build' em desenvolvimento)")
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        add("Interface web", "aviso", "SPA não empacotada")
    if chamar:
        cliente = ClienteLLM(projeto, s, usar_cache=False)
        try:
            for rot, m in papeis:
                r = cliente.chamar(papel="doctor", rotulo=rot, cfg=m,
                                   req=Requisicao("Reply with the JSON object {\"ok\": true} and nothing else.", "ping"),
                                   execucao_id=None, artigo_id=None)
                if r.resposta is None:
                    add(f"Chamada {rot}", "erro", r.erro)
                else:
                    obs = r.resposta.modelo_observado or "?"
                    add(f"Chamada {rot}", "ok" if obs else "aviso",
                        f"modelo observado: {obs} · {r.resposta.latencia_ms} ms")
        finally:
            cliente.fechar()
    return out
