"""OpenRouter account and model catalog (no LLM calls here).

* ``catalogo``: the public model list (``GET /models``) with context window and prices. It is
  cached in ``.lutz/openrouter_modelos.json`` for a day; cost estimates read only the cache, so
  extraction never waits on the network for prices.
* ``conta``: usage and limit of the API key (``GET /key``) and, when the key may read it, the
  credit balance of the account (``GET /credits``).

LLM calls go through :class:`lutz.llm.cliente.ClienteLLM`; this module only reads metadata.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from lutz.core.errors import ProvedorErro
from lutz.core.project import Projeto

URL_PADRAO = "https://openrouter.ai/api/v1"
VALIDADE_CATALOGO_S = 24 * 3600
ARQUIVO_CATALOGO = "openrouter_modelos.json"


def base_url(env: dict[str, str]) -> str:
    base = (env.get("OPENROUTER_BASE_URL") or URL_PADRAO).rstrip("/")
    if urllib.parse.urlparse(base).scheme not in ("https", "http"):
        raise ProvedorErro(f"OPENROUTER_BASE_URL inválida: {base}")
    return base


def _get_json(url: str, chave: str | None = None, timeout: float = 20) -> dict:
    """GET a JSON document. The scheme was checked by :func:`base_url`."""
    cab = {"Accept": "application/json", "User-Agent": "lutz", "X-Title": "Lutz"}
    if chave:
        cab["Authorization"] = f"Bearer {chave}"
    req = urllib.request.Request(url, headers=cab)
    try:
        # base_url() admits only http(s), so urlopen cannot open file:// or other schemes.
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ProvedorErro("O OpenRouter recusou a chave (401). Confira OPENROUTER_API_KEY.") from exc
        raise ProvedorErro(f"O OpenRouter respondeu {exc.code} em {url}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProvedorErro(f"Sem conexão com o OpenRouter ({url}): {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProvedorErro(f"O OpenRouter devolveu algo que não é JSON em {url}.") from exc


def _por_milhao(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x < 0 else round(x * 1_000_000, 6)


def _normalizar(item: dict) -> dict:
    preco = item.get("pricing") or {}
    return {
        "id": item.get("id", ""),
        "nome": item.get("name") or item.get("id", ""),
        "fornecedor": (item.get("id", "").split("/")[0] if "/" in item.get("id", "") else ""),
        "contexto": item.get("context_length"),
        "entrada": _por_milhao(preco.get("prompt")),
        "saida": _por_milhao(preco.get("completion")),
        "parametros": sorted(item.get("supported_parameters") or []),
        "criado": item.get("created"),
    }


def _arquivo(projeto: Projeto):
    return projeto.estado / ARQUIVO_CATALOGO


def _ler_cache(projeto: Projeto) -> dict | None:
    try:
        return json.loads(_arquivo(projeto).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gravar_cache(projeto: Projeto, dados: dict) -> None:
    destino = _arquivo(projeto)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destino)


def catalogo(projeto: Projeto, env: dict[str, str] | None = None, *, atualizar: bool = False,
             rede: bool = True, agora=time.time) -> dict:
    """``{"modelos": [...], "atualizado_em": iso, "origem": "rede"|"cache"|"vazio", "erro": str}``.

    Without *rede* only the cache is read. A network failure falls back to the cache.
    """
    cache = _ler_cache(projeto)
    fresco = cache is not None and agora() - cache.get("ts", 0) < VALIDADE_CATALOGO_S
    if cache is not None and (not rede or (fresco and not atualizar)):
        return {**cache, "origem": "cache", "erro": ""}
    if not rede:
        return {"modelos": [], "atualizado_em": None, "origem": "vazio", "erro": ""}
    try:
        bruto = _get_json(f"{base_url(env or {})}/models")
    except ProvedorErro as exc:
        if cache is not None:
            return {**cache, "origem": "cache", "erro": str(exc)}
        return {"modelos": [], "atualizado_em": None, "origem": "vazio", "erro": str(exc)}
    modelos = sorted((_normalizar(m) for m in bruto.get("data") or [] if m.get("id")), key=lambda m: m["id"])
    t = agora()
    dados = {"ts": t, "atualizado_em": datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds"),
             "modelos": modelos}
    _gravar_cache(projeto, dados)
    return {**dados, "origem": "rede", "erro": ""}


def precos_catalogo(projeto: Projeto) -> dict[str, tuple[float, float]]:
    """USD per million tokens from the cached catalog (never touches the network)."""
    out = {}
    for m in catalogo(projeto, rede=False)["modelos"]:
        if m["entrada"] is not None and m["saida"] is not None:
            out[m["id"]] = (m["entrada"], m["saida"])
    return out


def ids_catalogo(projeto: Projeto) -> set[str]:
    return {m["id"] for m in catalogo(projeto, rede=False)["modelos"]}


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def conta(env: dict[str, str]) -> dict:
    """Usage of the key and, when available, the credit balance of the account (USD)."""
    chave = env.get("OPENROUTER_API_KEY")
    if not chave:
        raise ProvedorErro("Defina OPENROUTER_API_KEY para ver o consumo da conta.")
    base = base_url(env)
    k = _get_json(f"{base}/key", chave).get("data") or {}
    out = {
        "rotulo": k.get("label") or "",
        "uso_usd": _num(k.get("usage")),
        "uso_dia_usd": _num(k.get("usage_daily")),
        "uso_semana_usd": _num(k.get("usage_weekly")),
        "uso_mes_usd": _num(k.get("usage_monthly")),
        "limite_usd": _num(k.get("limit")),
        "limite_restante_usd": _num(k.get("limit_remaining")),
        "gratuito": bool(k.get("is_free_tier")),
        "creditos_usd": None,
        "creditos_usados_usd": None,
        "saldo_usd": None,
    }
    try:
        c = _get_json(f"{base}/credits", chave).get("data") or {}
    except ProvedorErro:
        return out  # some keys cannot read the account balance; the key usage is still useful
    total, usado = _num(c.get("total_credits")), _num(c.get("total_usage"))
    out.update({"creditos_usd": total, "creditos_usados_usd": usado,
                "saldo_usd": None if total is None or usado is None else round(total - usado, 6)})
    return out
