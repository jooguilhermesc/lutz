"""Provider adapters. One function per vendor family, all returning :class:`Resposta`.

* ``anthropic``: official Anthropic SDK. JSON is enforced with structured outputs
  (``output_config.format``). Sampling parameters are not sent: current Claude models reject
  them, so the configured temperature is recorded as "not applicable".
* ``openai`` / ``openrouter`` / ``docker_model_runner``: OpenAI-compatible Chat Completions.
  JSON uses ``response_format`` (``json_schema`` on OpenAI, ``json_object`` elsewhere) and falls
  back to plain text plus parsing when the endpoint rejects it.
* ``fake``: deterministic in-process responders for tests and demos.
"""

from __future__ import annotations

import json
import re
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


# ── anthropic ────────────────────────────────────────────────────────────────


def _anthropic(cfg: ModeloPapel, req: Requisicao, env: dict[str, str], timeout: float) -> Resposta:
    import anthropic

    kwargs = {"api_key": env.get("ANTHROPIC_API_KEY") or None, "timeout": timeout, "max_retries": 0}
    base = cfg.base_url or env.get("ANTHROPIC_BASE_URL")
    if base:
        kwargs["base_url"] = base
    cliente = anthropic.Anthropic(**kwargs)
    params: dict = {
        "model": cfg.modelo,
        "max_tokens": cfg.max_tokens,
        "system": req.sistema,
        "messages": [{"role": "user", "content": req.usuario}],
    }
    output_config: dict = {}
    if req.schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": req.schema}
    if cfg.esforco:
        output_config["effort"] = cfg.esforco
    if output_config:
        params["output_config"] = output_config
    t0 = time.perf_counter()
    try:
        r = cliente.messages.create(**params)
    except anthropic.RateLimitError as exc:
        espera = _retry_after(getattr(exc, "response", None))
        raise ErroTransitorio(f"limite de requisições: {exc.message}", espera) from exc
    except (anthropic.InternalServerError, anthropic.APITimeoutError,
            anthropic.APIConnectionError) as exc:
        raise ErroTransitorio(f"erro transitório da Anthropic: {exc}") from exc
    except anthropic.APIStatusError as exc:
        if exc.status_code in (408, 409, 529):
            raise ErroTransitorio(f"erro transitório da Anthropic ({exc.status_code})") from exc
        raise ErroDefinitivo(f"Anthropic recusou a requisição ({exc.status_code}): {exc.message}") from exc
    lat = int((time.perf_counter() - t0) * 1000)
    if r.stop_reason == "refusal":
        cat = getattr(getattr(r, "stop_details", None), "category", None)
        raise ErroDefinitivo(f"o modelo recusou a requisição (categoria: {cat})")
    texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    if r.stop_reason == "max_tokens":
        raise ErroDefinitivo(
            f"resposta cortada em max_tokens={cfg.max_tokens}; aumente max_tokens no lutz.yaml"
        )
    return Resposta(
        texto=texto,
        tokens_entrada=getattr(r.usage, "input_tokens", 0) or 0,
        tokens_saida=getattr(r.usage, "output_tokens", 0) or 0,
        modelo_observado=r.model,
        fingerprint=getattr(r, "id", "") or "",
        latencia_ms=lat,
    )


# ── openai-compatible ────────────────────────────────────────────────────────

_BASES = {
    "openai": ("OPENAI_BASE_URL", None),
    "openrouter": ("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    "docker_model_runner": ("DOCKER_MODEL_HOST", "http://localhost:12434/engines/v1"),
}
_CHAVES = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def _openai_compat(cfg: ModeloPapel, req: Requisicao, env: dict[str, str], timeout: float) -> Resposta:
    import openai

    var_base, padrao = _BASES[cfg.provedor]
    base = cfg.base_url or env.get(var_base) or padrao
    chave = env.get(_CHAVES.get(cfg.provedor, ""), "") or (
        "docker-model-runner" if cfg.provedor == "docker_model_runner" else ""
    )
    if not chave:
        raise ErroDefinitivo(f"Defina {_CHAVES[cfg.provedor]} no .env para usar {cfg.provedor}.")
    cliente = openai.OpenAI(api_key=chave, base_url=base, timeout=timeout, max_retries=0)
    mensagens = [{"role": "system", "content": req.sistema}, {"role": "user", "content": req.usuario}]
    params: dict = {"model": cfg.modelo, "messages": mensagens, "temperature": cfg.temperatura}
    if cfg.provedor == "openai":
        params["max_completion_tokens"] = cfg.max_tokens
        params["seed"] = 42
    else:
        params["max_tokens"] = cfg.max_tokens
    formatos: list[dict] = []
    if req.schema is not None:
        schema = req.schema if cfg.provedor == "openai" else _limitar_schema(req.schema)
        formatos = [
            {"type": "json_schema", "json_schema": {"name": req.nome_schema, "schema": schema, "strict": True}},
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
                raise ErroDefinitivo(f"{cfg.provedor} recusou a requisição: {exc}") from exc
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
            raise ErroDefinitivo(f"{cfg.provedor} recusou a requisição: {exc}") from exc
        except openai.RateLimitError as exc:
            raise ErroTransitorio(f"limite de requisições: {exc}",
                                  _retry_after(getattr(exc, "response", None))) from exc
        except (openai.InternalServerError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise ErroTransitorio(f"erro transitório de {cfg.provedor}: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code in (408, 409, 425, 503, 529):
                raise ErroTransitorio(f"erro transitório ({exc.status_code})") from exc
            raise ErroDefinitivo(f"{cfg.provedor} recusou a requisição ({exc.status_code}): {exc}") from exc
    lat = int((time.perf_counter() - t0) * 1000)
    if not r.choices:
        raise ErroTransitorio(f"{cfg.provedor} devolveu resposta vazia")
    escolha = r.choices[0]
    texto = escolha.message.content or ""
    if escolha.finish_reason == "length":
        raise ErroDefinitivo(
            f"resposta cortada em max_tokens={cfg.max_tokens}; aumente max_tokens no lutz.yaml"
        )
    uso = r.usage
    observado = getattr(r, "model", "") or ""
    digest = re.search(r"sha256[:/]([0-9a-f]{12})", observado)
    if digest:  # Docker Model Runner answers with the bundle path; keep the model name and digest
        observado = f"{cfg.modelo}@sha256:{digest.group(1)}"
    return Resposta(
        texto=texto,
        tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
        tokens_saida=getattr(uso, "completion_tokens", 0) or 0,
        modelo_observado=observado,
        fingerprint=getattr(r, "system_fingerprint", "") or getattr(r, "provider", "") or "",
        latencia_ms=lat,
    )


def _limitar_schema(schema: dict) -> dict:
    """Bounded copy of a JSON schema for grammar-constrained local models (llama.cpp).

    Small models loop on open-ended arrays; ``maxItems`` and ``maxLength`` keep them finite.
    """
    import copy

    s = copy.deepcopy(schema)

    def visitar(no):
        if isinstance(no, dict):
            if no.get("type") == "array" and "maxItems" not in no and no.get("items", {}).get("type") == "string":
                no["maxItems"] = 3
            if no.get("type") == "string" and "enum" not in no and "maxLength" not in no:
                no["maxLength"] = 600
            for v in no.values():
                visitar(v)
        elif isinstance(no, list):
            for v in no:
                visitar(v)

    visitar(s)
    return s


def _retry_after(resp) -> float | None:
    try:
        v = resp.headers.get("retry-after")
        return float(v) if v else None
    except Exception:  # pragma: no cover
        return None


def completar(cfg: ModeloPapel, req: Requisicao, env: dict[str, str], timeout: float) -> Resposta:
    if cfg.provedor == "fake":
        return _fake(cfg, req)
    if cfg.provedor == "anthropic":
        return _anthropic(cfg, req, env, timeout)
    return _openai_compat(cfg, req, env, timeout)


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
