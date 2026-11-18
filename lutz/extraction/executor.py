"""Autonomous mode: plan, estimate, run, resume and recompute an extraction run.

Life of a cell (``celula.estado``)::

    pendente -> extraida (all extractors answered) -> verificada (V done or skipped)
             -> consolidada (cross-field rules applied, level set) -> adjudicada

* One LLM call per article × extractor × group of fields that share sections.
* Resuming never repeats work: a group is re-requested for an extractor only when some cell
  of that group has no raw answer from it, and identical requests are served from the cache.
* Only one process writes at a time (``core.lock``); inside that process, articles run in
  parallel threads, each with its own SQLite connection.
* A run always uses the settings stored when it was planned, so a resumed run cannot mix
  models. Secrets are read from the current ``.env``.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from lutz import __version__
from lutz.config.settings import ModeloPapel, Settings, estrategia_diversidade
from lutz.core import codebook as cbk
from lutz.core.codebook import Campo, Codebook
from lutz.core.db import agora, conectar, jdump, jload, transacao, um
from lutz.core.errors import EstadoInvalido, LutzError, OrcamentoExcedido
from lutz.core.ingestao import textos_paginas
from lutz.core.project import Projeto
from lutz.core.texto import estimar_tokens, normalizar
from lutz.extraction import consolidacao as cons
from lutz.extraction import contexto as ctxm
from lutz.extraction import prompts as P
from lutz.extraction.evidencia import TextoArtigo, avaliar
from lutz.extraction.regras import checar_artigo, checar_bruta
from lutz.llm.cliente import ClienteLLM, custo, gasto_total, preco_de, tabela_precos
from lutz.llm.provedores import Requisicao, extrair_json

EXTRATORES = ("E1", "E2", "E3")
Progresso = Callable[[dict], None]


class Interrompido(LutzError):
    pass


# ── planning ─────────────────────────────────────────────────────────────────


def planejar(
    projeto: Projeto, con, settings: Settings, *, tipo: str = "autonoma",
    codebook_versao: int | None = None, campos: list[str] | None = None,
    artigos: list[str] | None = None, piloto_id: int | None = None,
    conjunto: str | None = None, forcar: bool = False,
) -> int:
    if tipo == "teste":
        cb_row = cbk.linha_codebook(con, codebook_versao)
    elif codebook_versao:
        cb_row = cbk.linha_codebook(con, codebook_versao)
        if cb_row and not cb_row["congelado"]:
            raise EstadoInvalido(f"O codebook v{codebook_versao} não está congelado.")
    else:
        cb_row = cbk.ultimo_congelado(con)
    if cb_row is None:
        raise EstadoInvalido(
            "Não há codebook congelado. Importe um ('lutz codebook import') e congele "
            "('lutz codebook freeze') antes de extrair."
        )
    cb = cbk.carregar(con, cb_row["versao"])
    nomes = [c.nome for c in cb.campos]
    if campos:
        faltam = [c for c in campos if c not in nomes]
        if faltam:
            raise EstadoInvalido(f"Campos inexistentes no codebook v{cb_row['versao']}: {', '.join(faltam)}")
        nomes = [n for n in nomes if n in campos]

    if piloto_id is not None:
        if conjunto not in ("ajuste", "validacao"):
            raise EstadoInvalido("Informe o conjunto do piloto: ajuste ou validacao.")
        ids = [r[0] for r in con.execute(
            "SELECT artigo_id FROM piloto_amostra WHERE piloto_id=? AND conjunto=? ORDER BY artigo_id",
            (piloto_id, conjunto))]
        if not ids:
            raise EstadoInvalido("O piloto ainda não foi sorteado ('lutz pilot sample').")
        if conjunto == "validacao":
            if not cb_row["congelado"]:
                raise EstadoInvalido("A validação exige codebook congelado.")
            ja = con.execute(
                """SELECT id FROM execucao WHERE piloto_id=? AND conjunto_piloto='validacao'
                   AND status IN ('concluida','rodando','pausada')""", (piloto_id,)).fetchone()
            if ja and not forcar:
                raise EstadoInvalido(
                    f"O conjunto de validação já foi usado na execução {ja[0]}. A validação roda uma "
                    "única vez; uma segunda rodada torna as métricas otimistas. Use --forcar só se "
                    "a primeira falhou por motivo técnico (isso fica registrado no relatório)."
                )
        tipo = "piloto"
    elif artigos:
        ids = []
        for chave in artigos:
            r = con.execute("SELECT id, status FROM artigo WHERE chave=?", (chave,)).fetchone()
            if r is None:
                raise EstadoInvalido(f"Artigo não encontrado: {chave}")
            if r["status"] != "pronto":
                raise EstadoInvalido(f"O artigo {chave} não está pronto para extração ({r['status']}).")
            ids.append(r["id"])
    else:
        ids = [r[0] for r in con.execute("SELECT id FROM artigo WHERE status='pronto' ORDER BY id")]
    if not ids:
        raise EstadoInvalido("Nenhum artigo pronto para extração. Importe PDFs com 'lutz load'.")

    extratores = ("E1",) if tipo == "teste" else EXTRATORES
    with transacao(con):
        cur = con.execute(
            """INSERT INTO execucao (tipo, codebook_id, piloto_id, conjunto_piloto, estrategia_diversidade,
               config, hash_config, hash_prompts, versao_lutz, artigos, campos, status, criada_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'planejada',?)""",
            (tipo, cb_row["id"], piloto_id, conjunto, estrategia_diversidade(settings.modelos),
             jdump(settings.dump()), settings.hash()[:16], P.hash_prompts(), __version__,
             jdump(ids), jdump(nomes), agora()),
        )
        eid = cur.lastrowid
        papeis = [(r, "extrator", getattr(settings.modelos, r)) for r in extratores]
        if tipo != "teste":
            if settings.modelos.V:
                papeis.append(("V", "verificador", settings.modelos.V))
            if settings.modelos.J:
                papeis.append(("J", "juiz", settings.modelos.J))
        for rot, papel, m in papeis:
            con.execute(
                """INSERT INTO extrator (execucao_id, papel, rotulo, provedor, modelo, temperatura,
                   max_tokens, variante_prompt) VALUES (?,?,?,?,?,?,?,?)""",
                (eid, papel, rot, m.provedor, m.modelo, m.temperatura, m.max_tokens, m.variante_prompt),
            )
        campos_db = {c["chave"]: c["id"] for c in cbk.campos_db(con, cb_row["id"])}
        con.executemany(
            "INSERT INTO celula (execucao_id, artigo_id, campo_id, campo_chave) VALUES (?,?,?,?)",
            [(eid, a, campos_db[n], n) for a in ids for n in nomes],
        )
        if tipo == "teste":
            con.executemany(
                "INSERT INTO teste_rapido (artigo_id, campo_chave, execucao_id, criado_em) VALUES (?,?,?,?)",
                [(a, n, eid, agora()) for a in ids for n in nomes],
            )
    return eid


# ── context shared by planning, estimate and run ─────────────────────────────


@dataclass
class _Ctx:
    projeto: Projeto
    execucao: dict
    settings: Settings
    cb: Codebook
    campos: list[Campo]
    extratores: tuple[str, ...]
    progresso: Progresso | None = None
    parar: threading.Event | None = None
    cliente: ClienteLLM | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def evento(self, **kw) -> None:
        if self.progresso:
            with self._lock:
                self.progresso(kw)


def _carregar_ctx(projeto: Projeto, con, execucao_id: int) -> _Ctx:
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,))
    if ex is None:
        raise EstadoInvalido(f"Execução {execucao_id} não existe.")
    settings = Settings.model_validate(jload(ex["config"]))
    cb_row = um(con, "SELECT versao FROM codebook WHERE id=?", (ex["codebook_id"],))
    cb = cbk.carregar(con, cb_row["versao"])
    nomes = jload(ex["campos"])
    campos = [cb.campo(n) for n in nomes]
    extratores = tuple(r[0] for r in con.execute(
        "SELECT rotulo FROM extrator WHERE execucao_id=? AND papel='extrator' ORDER BY rotulo", (execucao_id,)))
    return _Ctx(projeto, ex, settings, cb, campos, extratores)


def _cabecalho(artigo: dict) -> str:
    partes = [artigo["chave"]]
    if artigo.get("titulo"):
        partes.append(f"— {artigo['titulo']}")
    return " ".join(partes)


def requisicao_extracao(ctx: _Ctx, cfg: ModeloPapel, campos: list[Campo], artigo: dict,
                        unidades, rotulos) -> tuple[Requisicao | None, str]:
    sistema = P.SISTEMA_EXTRATOR[cfg.variante_prompt]
    vazio = P.mensagem_extracao(campos, _cabecalho(artigo), "")
    overhead = estimar_tokens(sistema + vazio)
    c = ctxm.montar(unidades, rotulos, campos, cfg, ctx.settings, overhead)
    if c is None:
        return None, "excede_contexto"
    return Requisicao(sistema, P.mensagem_extracao(campos, _cabecalho(artigo), c.texto),
                      P.SCHEMA_EXTRACAO, "extracao"), c.estrategia


def _texto_artigo(projeto: Projeto, con, artigo_id: int, unidades) -> TextoArtigo:
    oculto = " ".join(r[0] for r in con.execute(
        "SELECT texto_oculto FROM pagina WHERE artigo_id=? AND texto_oculto!=''", (artigo_id,)))
    return TextoArtigo(
        paginas=textos_paginas(projeto, con, artigo_id),
        rotulos=ctxm.rotulos_paginas(con, artigo_id),
        unidades={u.uid: (u.pagina, u.texto) for u in unidades},
        oculto=oculto,
    )


# ── estimate ─────────────────────────────────────────────────────────────────

TOKENS_SAIDA_POR_CAMPO = 90
TOKENS_VERIFICADOR_ENTRADA = 900
TOKENS_VERIFICADOR_SAIDA = 80


def estimar(projeto: Projeto, con, execucao_id: int) -> dict:
    """Upper-bound estimate of the remaining work. Cached requests cost nothing."""
    ctx = _carregar_ctx(projeto, con, execucao_id)
    precos = tabela_precos(ctx.settings)
    por: dict[str, dict] = {}
    excedem: set[str] = set()
    em_cache = 0
    artigos = [dict(r) for r in con.execute(
        f"SELECT * FROM artigo WHERE id IN ({','.join('?' * len(jload(ctx.execucao['artigos'])))})",
        jload(ctx.execucao["artigos"]))]
    grupos = ctxm.grupos(ctx.campos)
    feitas = {(r[0], r[1], r[2]) for r in con.execute(
        """SELECT c.artigo_id, c.campo_chave, b.rotulo FROM extracao_bruta b
           JOIN celula c ON c.id=b.celula_id WHERE c.execucao_id=?""", (execucao_id,))}
    celulas_pend = 0
    for art in artigos:
        unidades = ctxm.carregar_unidades(con, art["id"])
        rotulos = ctxm.rotulos_paginas(con, art["id"])
        for _, campos in grupos:
            for rot in ctx.extratores:
                if all((art["id"], c.nome, rot) in feitas for c in campos):
                    continue
                cfg = getattr(ctx.settings.modelos, rot)
                req, _ = requisicao_extracao(ctx, cfg, campos, art, unidades, rotulos)
                d = por.setdefault(rot, {"papel": "extrator", "rotulo": rot, "provedor": cfg.provedor,
                                         "modelo": cfg.modelo, "chamadas": 0, "tokens_entrada": 0,
                                         "tokens_saida": 0})
                if req is None:
                    excedem.add(art["chave"])
                    continue
                h = ClienteLLM.hash_requisicao(cfg, req)
                if con.execute("SELECT 1 FROM chamada_llm WHERE hash_requisicao=? AND status='ok' LIMIT 1",
                               (h,)).fetchone():
                    em_cache += 1
                    continue
                d["chamadas"] += 1
                d["tokens_entrada"] += estimar_tokens(req.sistema + req.usuario)
                d["tokens_saida"] += TOKENS_SAIDA_POR_CAMPO * len(campos)
        celulas_pend += con.execute(
            "SELECT count(*) FROM celula WHERE execucao_id=? AND artigo_id=? AND estado IN ('pendente','extraida')",
            (execucao_id, art["id"])).fetchone()[0]
    if ctx.settings.modelos.V and ctx.execucao["tipo"] != "teste":
        cfg = ctx.settings.modelos.V
        por["V"] = {"papel": "verificador", "rotulo": "V", "provedor": cfg.provedor, "modelo": cfg.modelo,
                    "chamadas": celulas_pend, "tokens_entrada": celulas_pend * TOKENS_VERIFICADOR_ENTRADA,
                    "tokens_saida": celulas_pend * TOKENS_VERIFICADOR_SAIDA}
    total = 0.0
    sem_preco = []
    for rot, d in por.items():
        cfg = ctx.settings.modelos.V if rot == "V" else getattr(ctx.settings.modelos, rot)
        c = custo(cfg, precos, d["tokens_entrada"], d["tokens_saida"])
        d["custo_usd"] = c
        if c is None:
            if d["chamadas"]:
                sem_preco.append(cfg.modelo)
        else:
            total += c
    gasto = gasto_total(con)
    orc = ctx.settings.custo.orcamento_usd
    return {
        "execucao_id": execucao_id,
        "chamadas": sum(d["chamadas"] for d in por.values()),
        "tokens_entrada": sum(d["tokens_entrada"] for d in por.values()),
        "tokens_saida": sum(d["tokens_saida"] for d in por.values()),
        "custo_usd": None if sem_preco else round(total, 4),
        "custo_conhecido_usd": round(total, 4),
        "por_papel": list(por.values()),
        "sem_preco": sorted(set(sem_preco)),
        "em_cache": em_cache,
        "excedem_contexto": sorted(excedem),
        "gasto_projeto_usd": round(gasto, 4),
        "orcamento_usd": orc,
        "cabe_no_orcamento": orc is None or gasto + total <= orc,
        "artigos": len(artigos),
        "campos": len(ctx.campos),
    }


# ── run ──────────────────────────────────────────────────────────────────────


def _checar(ctx: _Ctx, con) -> None:
    if ctx.parar is not None and ctx.parar.is_set():
        raise Interrompido("execução pausada")
    st = con.execute("SELECT status FROM execucao WHERE id=?", (ctx.execucao["id"],)).fetchone()[0]
    if st == "pausada":
        raise Interrompido("execução pausada")
    orc = ctx.settings.custo.orcamento_usd
    if orc is not None and gasto_total(con) >= orc:
        raise OrcamentoExcedido(
            f"Orçamento do projeto atingido (US$ {orc:.2f}). Aumente custo.orcamento_usd no lutz.yaml "
            "e retome a execução."
        )


def _parse_pagina(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    m = re.search(r"\d+", str(v))
    return int(m.group(0)) if m else None


def parse_extracao(texto: str, campos: list[Campo]) -> dict[str, dict]:
    obj = extrair_json(texto)
    itens = obj.get("campos")
    if itens is None and len(campos) == 1 and "valor" in obj:
        itens = [obj]
    if not isinstance(itens, list):
        raise ValueError("faltou a lista 'campos' na resposta")
    nomes = {c.nome for c in campos}
    out: dict[str, dict] = {}
    for i, it in enumerate(itens):
        if not isinstance(it, dict):
            continue
        nome = str(it.get("nome", "")).strip()
        if nome not in nomes and len(itens) == len(campos):
            nome = campos[i].nome
        if nome not in nomes:
            continue
        nr = it.get("nao_reportado", False)
        if isinstance(nr, str):
            nr = nr.strip().lower() in ("true", "sim", "yes", "1")
        valor = it.get("valor")
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            valor = str(valor)
        if isinstance(valor, (list, dict)):
            valor = json.dumps(valor, ensure_ascii=False)
        if isinstance(valor, str) and normalizar(valor) in ("nao_reportado", "não reportado",
                                                            "not reported", "null", "none", "n/a"):
            nr, valor = True, None
        unidades = it.get("unidades") or []
        if isinstance(unidades, str):
            unidades = re.findall(r"p\d+\.(?:s\d+|t\d+\.r\d+)", unidades)
        out[nome] = {
            "valor": valor,
            "nao_reportado": bool(nr),
            "unidades": [str(u).strip("[] ") for u in unidades if u],
            "trecho": it.get("trecho") if isinstance(it.get("trecho"), str) else None,
            "pagina": _parse_pagina(it.get("pagina")),
        }
    if not out:
        raise ValueError("nenhum campo do formulário foi encontrado na resposta")
    return out


def _gravar_falhas(con, ctx: _Ctx, artigo_id: int, campos: list[Campo], rot: str, erro: str,
                   chamada_id: int | None) -> None:
    with transacao(con):
        for c in campos:
            cel = con.execute("SELECT id FROM celula WHERE execucao_id=? AND artigo_id=? AND campo_chave=?",
                              (ctx.execucao["id"], artigo_id, c.nome)).fetchone()
            con.execute(
                """INSERT OR REPLACE INTO extracao_bruta (celula_id, rotulo, status, erro, chamada_id)
                   VALUES (?,?,'falha',?,?)""", (cel[0], rot, erro, chamada_id))


def _gravar_brutas(con, ctx: _Ctx, artigo_id: int, campos: list[Campo], rot: str, itens: dict,
                   chamada_id: int, texto: TextoArtigo) -> None:
    lim = ctx.settings.limiares
    with transacao(con):
        for c in campos:
            cel = con.execute("SELECT id FROM celula WHERE execucao_id=? AND artigo_id=? AND campo_chave=?",
                              (ctx.execucao["id"], artigo_id, c.nome)).fetchone()[0]
            it = itens.get(c.nome)
            if it is None:
                con.execute("""INSERT OR REPLACE INTO extracao_bruta (celula_id, rotulo, status, erro,
                               chamada_id) VALUES (?,?,'falha','campo ausente na resposta',?)""",
                            (cel, rot, chamada_id))
                continue
            ok, det, norm = checar_bruta(c, it["valor"], it["nao_reportado"])
            ev = avaliar(texto, c, norm, it["nao_reportado"], it["trecho"], it["pagina"], it["unidades"], lim)
            con.execute(
                """INSERT OR REPLACE INTO extracao_bruta (celula_id, rotulo, status, valor, valor_normalizado,
                   nao_reportado, trecho, pagina, unidades, e, e_detalhe, regras_ok, regras_detalhe,
                   chamada_id) VALUES (?,?,'ok',?,?,?,?,?,?,?,?,?,?,?)""",
                (cel, rot, it["valor"], norm, int(it["nao_reportado"]), ev.trecho or it["trecho"],
                 ev.pagina or it["pagina"], jdump(it["unidades"]), ev.e, ev.detalhe, int(ok), det,
                 chamada_id),
            )
            n = con.execute("SELECT count(*) FROM extracao_bruta WHERE celula_id=?", (cel,)).fetchone()[0]
            if n >= len(ctx.extratores):
                con.execute("UPDATE celula SET estado='extraida', atualizada_em=? WHERE id=? AND estado='pendente'",
                            (agora(), cel))


def _extrair_grupo(ctx: _Ctx, con, artigo: dict, campos: list[Campo], grupo: str, rot: str,
                   unidades, rotulos, texto: TextoArtigo) -> None:
    feitas = {r[0] for r in con.execute(
        """SELECT c.campo_chave FROM extracao_bruta b JOIN celula c ON c.id=b.celula_id
           WHERE c.execucao_id=? AND c.artigo_id=? AND b.rotulo=?""",
        (ctx.execucao["id"], artigo["id"], rot))}
    if all(c.nome in feitas for c in campos):
        return
    _checar(ctx, con)
    cfg: ModeloPapel = getattr(ctx.settings.modelos, rot)
    req, estrategia = requisicao_extracao(ctx, cfg, campos, artigo, unidades, rotulos)
    if req is None:
        _gravar_falhas(con, ctx, artigo["id"], campos, rot,
                       f"o artigo excede a janela de contexto de {cfg.modelo}", None)
        ctx.evento(tipo="falha", artigo=artigo["chave"], extrator=rot, erro="excede_contexto")
        return
    assert ctx.cliente is not None
    res = ctx.cliente.chamar(papel="extrator", rotulo=rot, cfg=cfg, req=req,
                             execucao_id=ctx.execucao["id"], artigo_id=artigo["id"],
                             grupo=f"{grupo}:{estrategia}")
    if res.resposta is None:
        _gravar_falhas(con, ctx, artigo["id"], campos, rot, res.erro or "falha na chamada", res.chamada_id)
        ctx.evento(tipo="falha", artigo=artigo["chave"], extrator=rot, erro=res.erro)
        return
    try:
        itens = parse_extracao(res.resposta.texto, campos)
    except ValueError as exc:
        ctx.cliente.marcar_malformada(res.chamada_id, str(exc))
        req2 = Requisicao(req.sistema, req.usuario + f"\n\nYour previous answer was invalid ({exc}). "
                          "Answer again with the JSON object only.", req.schema, req.nome_schema)
        res = ctx.cliente.chamar(papel="extrator", rotulo=rot, cfg=cfg, req=req2,
                                 execucao_id=ctx.execucao["id"], artigo_id=artigo["id"],
                                 grupo=f"{grupo}:{estrategia}:retry")
        try:
            if res.resposta is None:
                raise ValueError(res.erro)
            itens = parse_extracao(res.resposta.texto, campos)
        except ValueError as exc2:
            if res.resposta is not None:
                ctx.cliente.marcar_malformada(res.chamada_id, str(exc2))
            _gravar_falhas(con, ctx, artigo["id"], campos, rot, f"resposta malformada: {exc2}",
                           res.chamada_id)
            ctx.evento(tipo="falha", artigo=artigo["chave"], extrator=rot, erro=str(exc2))
            return
    _gravar_brutas(con, ctx, artigo["id"], campos, rot, itens, res.chamada_id, texto)
    ctx.evento(tipo="extracao", artigo=artigo["chave"], extrator=rot, grupo=grupo,
               cache=res.cache)


def _brutas_celula(con, celula_id: int, extratores) -> list[cons.Bruta]:
    por = {r["rotulo"]: dict(r) for r in con.execute(
        "SELECT * FROM extracao_bruta WHERE celula_id=?", (celula_id,))}
    out = []
    for rot in extratores:
        r = por.get(rot)
        if r is None or r["status"] != "ok":
            out.append(cons.Bruta(rot, False, None, False, None, erro=(r or {}).get("erro", "sem resposta")))
            continue
        out.append(cons.Bruta(
            rot, bool(r["regras_ok"]), r["valor_normalizado"], bool(r["nao_reportado"]), r["e"],
            jload(r["unidades"], []), r["trecho"], r["pagina"],
            erro="" if r["regras_ok"] else r["regras_detalhe"],
        ))
    return out


def _verificar(ctx: _Ctx, con, artigo: dict, campo: Campo, c: cons.Consolidado, unidades,
               texto: TextoArtigo, permitir_chamadas: bool = True) -> tuple[float | None, dict]:
    """Returns (v, record). v None = verifier not configured or not applicable (declared 1)."""
    cfg = ctx.settings.modelos.V
    if cfg is None or c.empate or c.vencedor is None:
        return None, {}
    if c.nao_reportado:
        alvo = ctxm.secoes_canonicas(campo.secoes)
        if not alvo:
            return None, {"papel": "V_ausencia", "nota": "campo sem 'secoes': ausência não verificada"}
        sel = [u for u in unidades if u.secao in alvo]
        if not sel:
            return None, {"papel": "V_ausencia", "nota": "seções indicadas não foram detectadas no artigo"}
        contexto = ctxm.renderizar(sel, texto.rotulos)
        if estimar_tokens(contexto) > ctxm.orcamento_tokens(cfg, ctx.settings) - 1500:
            return None, {"papel": "V_ausencia", "nota": "seções maiores que a janela do verificador"}
        req = Requisicao(P.SISTEMA_AUSENCIA, P.mensagem_ausencia(campo, contexto), P.SCHEMA_AUSENCIA,
                         "ausencia")
        papel = "verificador_ausencia"
    else:
        w = c.vencedor
        janela = ctxm.janela_unidades(unidades, w.unidades) if w.unidades else ""
        if not janela and w.pagina in texto.paginas and w.trecho:
            pag = texto.paginas[w.pagina][0]
            pos = normalizar(pag).find(normalizar(w.trecho)[:40])
            ini = max(0, pos - 600) if pos >= 0 else 0
            janela = pag[ini: ini + 1500]
        req = Requisicao(P.SISTEMA_VERIFICADOR,
                         P.mensagem_verificador(campo, c.valor or "", w.trecho or "", janela),
                         P.SCHEMA_VERIFICADOR, "verificacao")
        papel = "verificador"
    assert ctx.cliente is not None
    if not permitir_chamadas:
        h = ClienteLLM.hash_requisicao(cfg, req)
        if not con.execute("SELECT 1 FROM chamada_llm WHERE hash_requisicao=? AND status='ok'", (h,)).fetchone():
            return None, {"papel": papel, "nota": "verificador não reexecutado no recálculo"}
    else:
        _checar(ctx, con)
    res = ctx.cliente.chamar(papel=papel, rotulo="V", cfg=cfg, req=req, execucao_id=ctx.execucao["id"],
                             artigo_id=artigo["id"], grupo=campo.nome)
    if res.resposta is None:
        return None, {"papel": papel, "nota": f"verificador falhou: {res.erro}", "falhou": True}
    try:
        obj = extrair_json(res.resposta.texto)
        ver = str(obj.get("veredito", "")).strip().lower()
    except ValueError as exc:
        ctx.cliente.marcar_malformada(res.chamada_id, str(exc))
        return None, {"papel": papel, "nota": f"resposta do verificador malformada: {exc}", "falhou": True}
    mapa = ({"sustenta": 1.0, "parcial": 0.5, "nao_sustenta": 0.0} if papel == "verificador"
            else {"ausente": 1.0, "incerto": 0.5, "presente": 0.0})
    if ver not in mapa:
        return None, {"papel": papel, "nota": f"veredito desconhecido: {ver}", "falhou": True}
    return mapa[ver], {"papel": papel, "rotulo": c.vencedor.rotulo, "veredito": ver,
                       "justificativa": str(obj.get("justificativa", ""))[:500],
                       "trecho": obj.get("trecho")}


def _consolidar_artigo(ctx: _Ctx, con, artigo: dict, unidades, texto: TextoArtigo,
                       permitir_chamadas: bool = True) -> None:
    eid = ctx.execucao["id"]
    celulas = [dict(r) for r in con.execute(
        "SELECT * FROM celula WHERE execucao_id=? AND artigo_id=?", (eid, artigo["id"]))]
    if ctx.execucao["tipo"] == "teste":
        with transacao(con):
            for cel in celulas:
                b = _brutas_celula(con, cel["id"], ctx.extratores)[0]
                con.execute(
                    """UPDATE celula SET valor_final=?, nao_reportado=?, e=?, trecho=?, pagina=?, unidades=?,
                       motivos=?, estado='extraida', atualizada_em=? WHERE id=?""",
                    (b.valor, int(b.nao_reportado), b.e, b.trecho, b.pagina, jdump(b.unidades),
                     jdump([b.erro] if b.erro else []), agora(), cel["id"]))
        return

    resultados: dict[str, tuple] = {}
    for cel in celulas:
        brutas = _brutas_celula(con, cel["id"], ctx.extratores)
        campo = ctx.cb.campo(cel["campo_chave"])
        c = cons.consolidar(campo, brutas, ctx.settings.limiares)
        v_ant = jload(cel["v_justificativa"], {}) if cel["v_justificativa"] else {}
        if (cel["estado"] in ("verificada", "consolidada", "adjudicada") and v_ant
                and not v_ant.get("falhou") and c.vencedor is not None
                and v_ant.get("rotulo") == c.vencedor.rotulo):
            v, reg = cel["v"], v_ant
        else:
            v, reg = _verificar(ctx, con, artigo, campo, c, unidades, texto, permitir_chamadas)
        resultados[cel["campo_chave"]] = (cel, campo, c, v, reg)
        con.execute("UPDATE celula SET estado=CASE WHEN estado IN ('pendente','extraida') THEN 'verificada' "
                    "ELSE estado END, v=?, v_justificativa=? WHERE id=?", (v, jdump(reg) if reg else "", cel["id"]))

    valores = {k: (c.valor, c.nao_reportado) for k, (_, _, c, _, _) in resultados.items() if not c.empate}
    falhas = checar_artigo(ctx.cb, valores)
    with transacao(con):
        for chave, (cel, _campo, c, v, reg) in resultados.items():
            regras_ok = chave not in falhas
            if c.vencedor is not None and not c.vencedor.ok:
                regras_ok = False
            niv, escore, e, extra = cons.nivel(c, v, regras_ok, ctx.settings.limiares)
            motivos = c.motivos + extra + falhas.get(chave, [])
            if reg.get("nota"):
                motivos.append(reg["nota"])
            w = c.vencedor
            if cel["estado"] == "adjudicada":
                con.execute(
                    """UPDATE celula SET a=?, e=?, escore=?, nivel=?, motivos=?, regras_ok=?, extrator_vencedor=?,
                       trecho=?, pagina=?, unidades=?, atualizada_em=? WHERE id=?""",
                    (c.a, e, escore, niv, jdump(motivos), int(regras_ok), w.rotulo if w else None,
                     w.trecho if w else None, w.pagina if w else None, jdump(w.unidades if w else []),
                     agora(), cel["id"]))
                continue
            con.execute(
                """UPDATE celula SET valor_final=?, nao_reportado=?, a=?, e=?, escore=?, nivel=?, motivos=?,
                   regras_ok=?, extrator_vencedor=?, trecho=?, pagina=?, unidades=?, estado='consolidada',
                   atualizada_em=? WHERE id=?""",
                (c.valor, int(c.nao_reportado), c.a, e, escore, niv, jdump(motivos), int(regras_ok),
                 w.rotulo if w else None, w.trecho if w else None, w.pagina if w else None,
                 jdump(w.unidades if w else []), agora(), cel["id"]))
            ctx.evento(tipo="celula", artigo=artigo["chave"], campo=chave, nivel=niv)


def _processar_artigo(ctx: _Ctx, artigo_id: int) -> None:
    con = conectar(ctx.projeto)
    try:
        artigo = um(con, "SELECT * FROM artigo WHERE id=?", (artigo_id,))
        unidades = ctxm.carregar_unidades(con, artigo_id)
        rotulos = ctxm.rotulos_paginas(con, artigo_id)
        texto = _texto_artigo(ctx.projeto, con, artigo_id, unidades)
        for grupo, campos in ctxm.grupos(ctx.campos):
            for rot in ctx.extratores:
                _extrair_grupo(ctx, con, artigo, campos, grupo, rot, unidades, rotulos, texto)
        _consolidar_artigo(ctx, con, artigo, unidades, texto)
        con.execute("UPDATE execucao SET atualizada_em=? WHERE id=?", (agora(), ctx.execucao["id"]))
        ctx.evento(tipo="artigo", artigo=artigo["chave"])
    finally:
        con.close()


def executar(projeto: Projeto, execucao_id: int, *, progresso: Progresso | None = None,
             parar: threading.Event | None = None, cliente: ClienteLLM | None = None,
             max_threads: int = 8) -> dict:
    """Run (or resume) a planned execution. The caller must hold the project lock."""
    con = conectar(projeto)
    try:
        ctx = _carregar_ctx(projeto, con, execucao_id)
        if ctx.execucao["status"] == "concluida":
            return resumo(con, execucao_id)
        ctx.progresso, ctx.parar = progresso, parar
        ctx.cliente = cliente or ClienteLLM(projeto, ctx.settings)
        con.execute("UPDATE execucao SET status='rodando', motivo_status='', iniciada_em=coalesce(iniciada_em, ?), "
                    "atualizada_em=? WHERE id=?", (agora(), agora(), execucao_id))
        ids = jload(ctx.execucao["artigos"])
        pendentes = [a for a in ids if con.execute(
            "SELECT 1 FROM celula WHERE execucao_id=? AND artigo_id=? AND estado IN ('pendente','extraida','verificada')",
            (execucao_id, a)).fetchone()]
        ctx.evento(tipo="inicio", execucao=execucao_id, artigos=len(ids), pendentes=len(pendentes))
        erro: BaseException | None = None
        with ThreadPoolExecutor(max_workers=max(1, min(max_threads, len(pendentes) or 1))) as pool:
            futuros = [pool.submit(_processar_artigo, ctx, a) for a in pendentes]
            for f in as_completed(futuros):
                try:
                    f.result()
                except (Interrompido, OrcamentoExcedido) as exc:
                    erro = erro or exc
                    if ctx.parar is None:
                        ctx.parar = threading.Event()
                    ctx.parar.set()
                except Exception as exc:  # noqa: BLE001 - recorded and re-raised below
                    erro = erro or exc
                    if ctx.parar is None:
                        ctx.parar = threading.Event()
                    ctx.parar.set()
        if isinstance(erro, (Interrompido, OrcamentoExcedido)):
            con.execute("UPDATE execucao SET status='pausada', motivo_status=?, atualizada_em=? WHERE id=?",
                        (str(erro), agora(), execucao_id))
            ctx.evento(tipo="pausa", motivo=str(erro))
            return resumo(con, execucao_id)
        if erro is not None:
            con.execute("UPDATE execucao SET status='falhou', motivo_status=?, atualizada_em=? WHERE id=?",
                        (f"{type(erro).__name__}: {erro}", agora(), execucao_id))
            raise erro
        if ctx.execucao["tipo"] != "teste":
            from lutz.extraction.metricas_autonomo import calcular

            calcular(con, execucao_id, ctx.settings)
        con.execute("UPDATE execucao SET status='concluida', concluida_em=?, atualizada_em=? WHERE id=?",
                    (agora(), agora(), execucao_id))
        ctx.evento(tipo="fim", execucao=execucao_id)
        return resumo(con, execucao_id)
    finally:
        if cliente is None and "ctx" in locals() and ctx.cliente is not None:
            ctx.cliente.fechar()
        con.close()


def recalcular(projeto: Projeto, execucao_id: int, *, usar_limiares_atuais: Settings | None = None) -> dict:
    """Recompute evidence, rules, consolidation, levels and metrics from stored answers.

    No new LLM calls: the verifier is reused when the winning extractor did not change, and
    otherwise served from the cache when possible. With *usar_limiares_atuais*, the thresholds
    of the current lutz.yaml replace the stored ones (recorded in the run config).
    """
    con = conectar(projeto)
    try:
        ctx = _carregar_ctx(projeto, con, execucao_id)
        if usar_limiares_atuais is not None:
            cfg = jload(ctx.execucao["config"])
            cfg["limiares"] = usar_limiares_atuais.limiares.model_dump(mode="json")
            ctx.settings = Settings.model_validate(cfg)
            con.execute("UPDATE execucao SET config=?, motivo_status=? WHERE id=?",
                        (jdump(cfg), "limiares recalculados em " + agora(), execucao_id))
        ctx.cliente = ClienteLLM(projeto, ctx.settings)
        for aid in jload(ctx.execucao["artigos"]):
            artigo = um(con, "SELECT * FROM artigo WHERE id=?", (aid,))
            unidades = ctxm.carregar_unidades(con, aid)
            texto = _texto_artigo(projeto, con, aid, unidades)
            with transacao(con):
                for cel in con.execute("SELECT id, campo_chave FROM celula WHERE execucao_id=? AND artigo_id=?",
                                       (execucao_id, aid)).fetchall():
                    campo = ctx.cb.campo(cel["campo_chave"])
                    for b in con.execute("SELECT * FROM extracao_bruta WHERE celula_id=? AND status='ok'",
                                         (cel["id"],)).fetchall():
                        ok, det, norm = checar_bruta(campo, b["valor"], bool(b["nao_reportado"]))
                        ev = avaliar(texto, campo, norm, bool(b["nao_reportado"]), b["trecho"], b["pagina"],
                                     jload(b["unidades"], []), ctx.settings.limiares)
                        con.execute("UPDATE extracao_bruta SET valor_normalizado=?, e=?, e_detalhe=?, regras_ok=?, "
                                    "regras_detalhe=? WHERE id=?", (norm, ev.e, ev.detalhe, int(ok), det, b["id"]))
            n_brutas_ok = all(
                con.execute("SELECT count(*) FROM extracao_bruta WHERE celula_id=?", (r[0],)).fetchone()[0]
                >= len(ctx.extratores)
                for r in con.execute("SELECT id FROM celula WHERE execucao_id=? AND artigo_id=?", (execucao_id, aid)))
            if n_brutas_ok:
                _consolidar_artigo(ctx, con, artigo, unidades, texto, permitir_chamadas=False)
        if ctx.execucao["tipo"] != "teste":
            from lutz.extraction.metricas_autonomo import calcular

            calcular(con, execucao_id, ctx.settings)
        ctx.cliente.fechar()
        return resumo(con, execucao_id)
    finally:
        con.close()


def reparar_interrompidas(con) -> list[int]:
    """Runs left 'rodando' by a process that died become 'pausada' (resumable)."""
    ids = [r[0] for r in con.execute("SELECT id FROM execucao WHERE status='rodando'")]
    for i in ids:
        con.execute("UPDATE execucao SET status='pausada', motivo_status='interrompida (processo encerrado)' "
                    "WHERE id=?", (i,))
    return ids


def pausar(con, execucao_id: int) -> None:
    con.execute("UPDATE execucao SET status='pausada', motivo_status='pausada pelo usuário', "
                "atualizada_em=? WHERE id=? AND status IN ('rodando','planejada')", (agora(), execucao_id))


def resumo(con, execucao_id: int) -> dict:
    ex = um(con, "SELECT * FROM execucao WHERE id=?", (execucao_id,))
    if ex is None:
        raise EstadoInvalido(f"Execução {execucao_id} não existe.")
    cont = {r[0]: r[1] for r in con.execute(
        "SELECT estado, count(*) FROM celula WHERE execucao_id=? GROUP BY estado", (execucao_id,))}
    niveis = {r[0]: r[1] for r in con.execute(
        "SELECT nivel, count(*) FROM celula WHERE execucao_id=? AND nivel IS NOT NULL GROUP BY nivel",
        (execucao_id,))}
    cst = con.execute("""SELECT coalesce(sum(custo_usd),0), coalesce(sum(tokens_entrada+tokens_saida),0),
                         count(*), sum(cache), sum(custo_usd IS NULL AND status='ok')
                         FROM chamada_llm WHERE execucao_id=?""", (execucao_id,)).fetchone()
    total = sum(cont.values())
    prontas = cont.get("consolidada", 0) + cont.get("adjudicada", 0) + (
        cont.get("extraida", 0) if ex["tipo"] == "teste" else 0)
    artigos = jload(ex["artigos"])
    artigos_prontos = con.execute(
        """SELECT count(DISTINCT artigo_id) FROM celula WHERE execucao_id=? AND artigo_id NOT IN
           (SELECT artigo_id FROM celula WHERE execucao_id=? AND estado IN ('pendente','extraida','verificada'))""",
        (execucao_id, execucao_id)).fetchone()[0] if ex["tipo"] != "teste" else len(artigos)
    return {
        "id": ex["id"], "tipo": ex["tipo"], "status": ex["status"], "motivo": ex["motivo_status"],
        "codebook_id": ex["codebook_id"], "piloto_id": ex["piloto_id"], "conjunto": ex["conjunto_piloto"],
        "estrategia_diversidade": ex["estrategia_diversidade"],
        "celulas": total, "celulas_prontas": prontas, "estados": cont, "niveis": niveis,
        "artigos": len(artigos), "artigos_prontos": artigos_prontos,
        "custo_usd": round(cst[0], 6), "tokens": cst[1], "chamadas": cst[2], "chamadas_cache": cst[3] or 0,
        "chamadas_sem_preco": cst[4] or 0,
        "criada_em": ex["criada_em"], "iniciada_em": ex["iniciada_em"], "concluida_em": ex["concluida_em"],
        "atualizada_em": ex["atualizada_em"],
    }


def preco_conhecido(cfg: ModeloPapel, settings: Settings) -> bool:
    return preco_de(cfg, tabela_precos(settings)) is not None
