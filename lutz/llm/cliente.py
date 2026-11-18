"""Single gateway for every LLM call.

Each call:

1. is looked up in the cache (same provider, model, parameters and prompt hash, answered with
   status ``ok`` before). A cache hit is recorded as a new ``chamada_llm`` row with cost 0,
   so resuming or re-running after a codebook change only pays for what changed;
2. waits for a per-provider slot (``concorrencia.por_provedor``);
3. retries transient errors with exponential backoff (honouring ``retry-after``);
4. is recorded in ``chamada_llm`` with request, response, observed model, tokens, cost and
   latency. Those rows feed the cost tracking of the web interface and annex C of the report.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from importlib import resources

import yaml

from lutz.config.env import carregar_env
from lutz.config.settings import ModeloPapel, Settings, hash_obj
from lutz.core.db import agora, conectar, jdump
from lutz.core.project import Projeto
from lutz.llm.provedores import ErroDefinitivo, ErroTransitorio, Requisicao, Resposta, completar


def tabela_precos(settings: Settings) -> dict[str, tuple[float, float]]:
    base = yaml.safe_load(resources.files("lutz.data").joinpath("precos.yaml").read_text("utf-8")) or {}
    out = {k: (float(v["entrada"]), float(v["saida"])) for k, v in base.items()}
    for k, p in settings.precos.items():
        out[k] = (p.entrada, p.saida)
    return out


def preco_de(cfg: ModeloPapel, precos: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    if cfg.provedor == "docker_model_runner":
        return (0.0, 0.0)
    if cfg.modelo in precos:
        return precos[cfg.modelo]
    curto = cfg.modelo.split("/")[-1]
    if curto in precos:
        return precos[curto]
    if cfg.provedor == "fake":
        return (0.0, 0.0)
    return None


def custo(cfg: ModeloPapel, precos, tokens_entrada: int, tokens_saida: int) -> float | None:
    p = preco_de(cfg, precos)
    if p is None:
        return None
    return (tokens_entrada * p[0] + tokens_saida * p[1]) / 1_000_000


@dataclass
class ResultadoChamada:
    resposta: Resposta | None
    chamada_id: int
    cache: bool
    erro: str = ""


_SEMAFOROS: dict[str, threading.BoundedSemaphore] = {}
_SEM_LOCK = threading.Lock()


def _semaforo(provedor: str, n: int) -> threading.BoundedSemaphore:
    with _SEM_LOCK:
        chave = f"{provedor}:{n}"
        if chave not in _SEMAFOROS:
            _SEMAFOROS[chave] = threading.BoundedSemaphore(n)
        return _SEMAFOROS[chave]


class ClienteLLM:
    def __init__(self, projeto: Projeto, settings: Settings, usar_cache: bool = True,
                 dormir=time.sleep):
        self.projeto = projeto
        self.settings = settings
        self.env = carregar_env(projeto)
        self.precos = tabela_precos(settings)
        self.usar_cache = usar_cache
        self._dormir = dormir
        self._local = threading.local()

    def _con(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = conectar(self.projeto)
            self._local.con = con
        return con

    def fechar(self) -> None:
        con = getattr(self._local, "con", None)
        if con is not None:
            con.close()
            self._local.con = None

    @staticmethod
    def hash_requisicao(cfg: ModeloPapel, req: Requisicao) -> str:
        return hash_obj({
            "provedor": cfg.provedor, "modelo": cfg.modelo, "temperatura": cfg.temperatura_efetiva(),
            "max_tokens": cfg.max_tokens, "esforco": cfg.esforco, "req": req.para_hash(),
        })

    def chamar(self, *, papel: str, rotulo: str, cfg: ModeloPapel, req: Requisicao,
               execucao_id: int | None, artigo_id: int | None, grupo: str = "") -> ResultadoChamada:
        con = self._con()
        h = self.hash_requisicao(cfg, req)
        requisicao_json = jdump({"sistema": req.sistema, "usuario": req.usuario, "schema": req.schema,
                                 "provedor": cfg.provedor, "modelo": cfg.modelo,
                                 "temperatura": cfg.temperatura_efetiva(), "max_tokens": cfg.max_tokens,
                                 "esforco": cfg.esforco})
        if self.usar_cache:
            anterior = con.execute(
                "SELECT * FROM chamada_llm WHERE hash_requisicao=? AND status='ok' ORDER BY id DESC LIMIT 1",
                (h,),
            ).fetchone()
            if anterior is not None:
                cur = con.execute(
                    """INSERT INTO chamada_llm (execucao_id, papel, rotulo, artigo_id, grupo, provedor,
                       modelo_pedido, modelo_observado, fingerprint, tokens_entrada, tokens_saida,
                       custo_usd, latencia_ms, status, tentativas, cache, hash_requisicao, requisicao,
                       resposta, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,0,'ok',0,1,?,?,?,?)""",
                    (execucao_id, papel, rotulo, artigo_id, grupo, cfg.provedor, cfg.modelo,
                     anterior["modelo_observado"], anterior["fingerprint"], anterior["tokens_entrada"],
                     anterior["tokens_saida"], h, requisicao_json, anterior["resposta"], agora()),
                )
                resp = Resposta(texto=anterior["resposta"], tokens_entrada=anterior["tokens_entrada"],
                                tokens_saida=anterior["tokens_saida"],
                                modelo_observado=anterior["modelo_observado"],
                                fingerprint=anterior["fingerprint"])
                return ResultadoChamada(resp, cur.lastrowid, True)

        conc = self.settings.concorrencia
        tentativas = 0
        erro = ""
        resp: Resposta | None = None
        status = "erro"
        while tentativas < conc.tentativas:
            tentativas += 1
            sem = _semaforo(cfg.provedor, conc.por_provedor)
            with sem:
                try:
                    resp = completar(cfg, req, self.env, conc.timeout_s)
                    status = "ok"
                    break
                except ErroDefinitivo as exc:
                    erro = str(exc)
                    break
                except ErroTransitorio as exc:
                    erro = str(exc)
                    espera = exc.espera or min(60.0, 2 ** tentativas + random.random())
            if tentativas < conc.tentativas:
                self._dormir(espera)
        c = custo(cfg, self.precos, resp.tokens_entrada, resp.tokens_saida) if resp else 0.0
        cur = con.execute(
            """INSERT INTO chamada_llm (execucao_id, papel, rotulo, artigo_id, grupo, provedor,
               modelo_pedido, modelo_observado, fingerprint, tokens_entrada, tokens_saida, custo_usd,
               latencia_ms, status, erro, tentativas, cache, hash_requisicao, requisicao, resposta,
               criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)""",
            (execucao_id, papel, rotulo, artigo_id, grupo, cfg.provedor, cfg.modelo,
             resp.modelo_observado if resp else "", resp.fingerprint if resp else "",
             resp.tokens_entrada if resp else 0, resp.tokens_saida if resp else 0, c,
             resp.latencia_ms if resp else 0, status, erro, tentativas, h, requisicao_json,
             resp.texto if resp else "", agora()),
        )
        return ResultadoChamada(resp if status == "ok" else None, cur.lastrowid, False, erro)

    def marcar_malformada(self, chamada_id: int, erro: str) -> None:
        """A syntactically broken answer must not be served from the cache again."""
        self._con().execute("UPDATE chamada_llm SET status='malformada', erro=? WHERE id=?",
                            (erro, chamada_id))


def gasto_total(con) -> float:
    return float(con.execute("SELECT coalesce(sum(custo_usd),0) FROM chamada_llm").fetchone()[0])


def consumo(con, execucao_id: int | None = None) -> dict:
    filtro, params = ("WHERE execucao_id=?", (execucao_id,)) if execucao_id else ("", ())
    tot = dict(con.execute(
        f"""SELECT count(*) chamadas, coalesce(sum(tokens_entrada),0) tokens_entrada,
            coalesce(sum(tokens_saida),0) tokens_saida, sum(custo_usd) custo_usd,
            sum(cache) em_cache, sum(status!='ok') falhas,
            sum(custo_usd IS NULL AND status='ok') sem_preco FROM chamada_llm {filtro}""", params,
    ).fetchone())
    por = [dict(r) for r in con.execute(
        f"""SELECT papel, rotulo, provedor, modelo_pedido, max(modelo_observado) modelo_observado,
            count(*) chamadas, sum(tokens_entrada) tokens_entrada, sum(tokens_saida) tokens_saida,
            sum(custo_usd) custo_usd, avg(latencia_ms) latencia_media_ms, sum(status!='ok') falhas
            FROM chamada_llm {filtro} GROUP BY papel, rotulo, provedor, modelo_pedido
            ORDER BY rotulo""", params)]
    return {"total": tot, "por_papel": por}
