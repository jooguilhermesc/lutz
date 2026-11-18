"""Provider adapters, all returning :class:`Resposta` (ADR-004: OpenRouter only).

* ``openrouter``: OpenAI-compatible Chat Completions on OpenRouter. JSON uses ``response_format``
  (``json_schema``, then ``json_object``) and falls back to plain text plus parsing when the
  model rejects it. Anthropic models get no sampling parameters (they reject them), so their
  temperature is recorded as "not applicable". The billed cost reported by OpenRouter is kept.
* ``fake``: deterministic in-process responders for tests and demos.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from lutz.config.settings import ModeloPapel
from lutz.core.errors import ProvedorErro


@dataclass
class Requisicao:
    sistema: str
    usuario: str
    schema: dict | None = None
    nome_schema: str = "resposta"

    def para_hash(self) -> dict:
        return {"sistema": self.sistema, "usuario": self.usuario, "schema": self.schema}


@dataclass
class Resposta:
    texto: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    modelo_observado: str = ""
    fingerprint: str = ""
    latencia_ms: int = 0
    extra: dict = field(default_factory=dict)


class ErroTransitorio(ProvedorErro):
    """Rate limit, server error, timeout or connection problem: worth retrying."""

    def __init__(self, msg: str, espera: float | None = None):
        super().__init__(msg)
        self.espera = espera


class ErroDefinitivo(ProvedorErro):
    """Bad request, authentication, unknown model: retrying will not help."""


# ── fake ─────────────────────────────────────────────────────────────────────

RespondedorFake = Callable[[ModeloPapel, Requisicao], str]
_FAKES: dict[str, RespondedorFake] = {}


def registrar_fake(modelo: str, funcao: RespondedorFake | None) -> None:
    if funcao is None:
        _FAKES.pop(modelo, None)
    else:
        _FAKES[modelo] = funcao


def _fake(cfg: ModeloPapel, req: Requisicao) -> Resposta:
    f = _FAKES.get(cfg.modelo) or _FAKES.get("*")
    if f is None:
        raise ErroDefinitivo(f"Nenhum respondedor fake registrado para '{cfg.modelo}'.")
    t0 = time.perf_counter()
    texto = f(cfg, req)
    from lutz.core.texto import estimar_tokens

    return Resposta(
        texto=texto,
        tokens_entrada=estimar_tokens(req.sistema + req.usuario),
        tokens_saida=estimar_tokens(texto),
        modelo_observado=cfg.modelo,
        fingerprint="fake",
        latencia_ms=int((time.perf_counter() - t0) * 1000),
    )


# ── openrouter ───────────────────────────────────────────────────────────────


def _openrouter(cfg: ModeloPapel, req: Requisicao, env: dict[str, str], timeout: float) -> Resposta:
    import openai

    from lutz.llm.openrouter import base_url

    base = cfg.base_url or base_url(env)
    chave = env.get("OPENROUTER_API_KEY", "")
    if not chave:
        raise ErroDefinitivo("Defina OPENROUTER_API_KEY no .env (ou na tela de Configurações).")
    cliente = openai.OpenAI(api_key=chave, base_url=base, timeout=timeout, max_retries=0,
                            default_headers={"X-Title": "Lutz"})
    mensagens = [{"role": "system", "content": req.sistema}, {"role": "user", "content": req.usuario}]
    params: dict = {"model": cfg.modelo, "messages": mensagens, "max_tokens": cfg.max_tokens, "seed": 42}
    if cfg.temperatura_efetiva() is not None:
        params["temperature"] = cfg.temperatura
    extra: dict = {"usage": {"include": True}}  # OpenRouter reports the billed cost of the call
    if cfg.esforco:
        extra["reasoning"] = {"effort": cfg.esforco}
    params["extra_body"] = extra
    formatos: list[dict] = []
    if req.schema is not None:
        formatos = [
            {"type": "json_schema", "json_schema": {"name": req.nome_schema, "schema": req.schema, "strict": True}},
            {"type": "json_object"},
        ]
        params["response_format"] = formatos.pop(0)

    t0 = time.perf_counter()
    tentativas_param = 0
    while True:
        try:
            r = cliente.chat.completions.create(**params)
            break
        except openai.BadRequestError as exc:
            msg = str(exc).lower()
            tentativas_param += 1
            if tentativas_param > 3:
                raise ErroDefinitivo(f"o OpenRouter recusou a requisição: {exc}") from exc
            if ("response_format" in msg or "json" in msg or "schema" in msg) and "response_format" in params:
                if formatos:
                    params["response_format"] = formatos.pop(0)
                else:
                    params.pop("response_format", None)
                continue
            if "temperature" in msg and "temperature" in params:
                params.pop("temperature")
                continue
            if "seed" in msg and "seed" in params:
                params.pop("seed")
                continue
            if "context" in msg and ("length" in msg or "window" in msg or "size" in msg):
                raise ErroDefinitivo(
                    f"o texto excede a janela de contexto de {cfg.modelo}; ajuste janela_tokens "
                    f"no lutz.yaml ({exc})"
                ) from exc
            raise ErroDefinitivo(f"o OpenRouter recusou a requisição: {exc}") from exc
        except openai.RateLimitError as exc:
            raise ErroTransitorio(f"limite de requisições: {exc}",
                                  _retry_after(getattr(exc, "response", None))) from exc
        except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise ErroTransitorio(f"erro transitório do OpenRouter: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code in (408, 409, 425, 503, 529):
                raise ErroTransitorio(f"erro transitório do OpenRouter ({exc.status_code})") from exc
            if exc.status_code == 402:
                raise ErroDefinitivo("sem créditos no OpenRouter (402): adicione créditos ou aumente o "
                                     "limite da chave") from exc
            raise ErroDefinitivo(f"o OpenRouter recusou a requisição ({exc.status_code}): {exc}") from exc
    lat = int((time.perf_counter() - t0) * 1000)
    if not r.choices:
        raise ErroTransitorio("o OpenRouter devolveu resposta vazia")
    escolha = r.choices[0]
    texto = escolha.message.content or ""
    if escolha.finish_reason == "length":
        raise ErroDefinitivo(
            f"resposta cortada em max_tokens={cfg.max_tokens}; aumente max_tokens no lutz.yaml"
        )
    uso = r.usage
    custo = getattr(uso, "cost", None)
    return Resposta(
        texto=texto,
        tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
        tokens_saida=getattr(uso, "completion_tokens", 0) or 0,
        modelo_observado=getattr(r, "model", "") or "",
        fingerprint=getattr(r, "provider", "") or getattr(r, "system_fingerprint", "") or "",
        latencia_ms=lat,
        extra={"custo_usd": float(custo)} if isinstance(custo, (int, float)) else {},
    )


def _retry_after(resp) -> float | None:
    try:
        v = resp.headers.get("retry-after")
        return float(v) if v else None
    except Exception:  # pragma: no cover
        return None


def completar(cfg: ModeloPapel, req: Requisicao, env: dict[str, str], timeout: float) -> Resposta:
    if cfg.provedor == "fake":
        return _fake(cfg, req)
    return _openrouter(cfg, req, env, timeout)


def extrair_json(texto: str) -> dict:
    """Parse a JSON object from a model answer (tolerates ``` fences and leading prose)."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        ini, fim = t.find("{"), t.rfind("}")
        if ini < 0 or fim <= ini:
            raise ValueError("a resposta não contém um objeto JSON") from None
        obj = json.loads(t[ini : fim + 1])
    if not isinstance(obj, dict):
        raise ValueError("a resposta JSON não é um objeto")
    return obj
