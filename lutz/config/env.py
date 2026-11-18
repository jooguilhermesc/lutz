"""Secrets and provider URLs: the ``.env`` file of the project.

This is the configuration mechanism kept from Lutz 0.5 (``SettingsModal`` + ``/config``):

* one ``.env`` per project, never committed;
* variables exported in the process environment take precedence over the file;
* the web modal reads the current values and writes changes back to ``.env``.

Changes from 0.5: only whitelisted keys can be written, a value can be cleared, values are
quoted by python-dotenv, and every value is reported with its origin so the modal can say
"this key comes from your shell; editing .env will not change it".

Models, thresholds and budget do NOT live here; they live in ``lutz.yaml``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import dotenv_values, set_key, unset_key

from lutz.core.errors import ConfigInvalida
from lutz.core.project import Projeto


@dataclass(frozen=True)
class ChaveEnv:
    nome: str
    rotulo: str
    segredo: bool
    padrao: str = ""


CHAVES: tuple[ChaveEnv, ...] = (
    ChaveEnv("ANTHROPIC_API_KEY", "Anthropic API key", True),
    ChaveEnv("OPENAI_API_KEY", "OpenAI API key", True),
    ChaveEnv("OPENROUTER_API_KEY", "OpenRouter API key", True),
    ChaveEnv("OPENAI_BASE_URL", "OpenAI-compatible base URL", False),
    ChaveEnv("ANTHROPIC_BASE_URL", "Anthropic base URL", False),
    ChaveEnv("OPENROUTER_BASE_URL", "OpenRouter base URL", False, "https://openrouter.ai/api/v1"),
    ChaveEnv(
        "DOCKER_MODEL_HOST",
        "Docker Model Runner URL",
        False,
        "http://localhost:12434/engines/v1",
    ),
)
_POR_NOME = {c.nome: c for c in CHAVES}

ENV_EXEMPLO = """\
# Lutz 1.0 — secrets and provider URLs for this project.
# Models, thresholds and budget live in lutz.yaml, not here.
# Variables exported in your shell take precedence over this file.
# Never commit this file.

ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENROUTER_API_KEY=

# Optional URLs
# OPENAI_BASE_URL=
# ANTHROPIC_BASE_URL=
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# Docker Model Runner (local models, no key). Inside a container use
# http://model-runner.docker.internal/engines/v1
# DOCKER_MODEL_HOST=http://localhost:12434/engines/v1
"""


def _arquivo(projeto: Projeto) -> dict[str, str]:
    if not projeto.env.exists():
        return {}
    return {k: v for k, v in dotenv_values(projeto.env).items() if v is not None}


def carregar_env(projeto: Projeto) -> dict[str, str]:
    """Merged view: defaults < .env < process environment."""
    valores = {c.nome: c.padrao for c in CHAVES if c.padrao}
    valores.update({k: v for k, v in _arquivo(projeto).items() if v != ""})
    for c in CHAVES:
        if os.environ.get(c.nome):
            valores[c.nome] = os.environ[c.nome]
    return valores


def mascarar(valor: str) -> str:
    if not valor:
        return ""
    if len(valor) <= 8:
        return "••••"
    return f"{valor[:4]}••••{valor[-3:]}"


def valores_com_origem(projeto: Projeto) -> list[dict]:
    arquivo = _arquivo(projeto)
    saida = []
    for c in CHAVES:
        if os.environ.get(c.nome):
            valor, origem = os.environ[c.nome], "processo"
        elif arquivo.get(c.nome):
            valor, origem = arquivo[c.nome], ".env"
        elif c.padrao:
            valor, origem = c.padrao, "padrao"
        else:
            valor, origem = "", "ausente"
        saida.append(
            {
                "nome": c.nome,
                "rotulo": c.rotulo,
                "segredo": c.segredo,
                "definido": bool(valor),
                "valor": mascarar(valor) if c.segredo else valor,
                "origem": origem,
                "sombreado": origem == "processo" and c.nome in arquivo,
            }
        )
    return saida


def salvar_env(projeto: Projeto, mudancas: dict[str, str | None]) -> list[str]:
    """Write changes to .env. ``None`` or ``""`` removes the key.

    Returns the keys whose new value will not take effect because the process environment
    defines them.
    """
    desconhecidas = sorted(set(mudancas) - set(_POR_NOME))
    if desconhecidas:
        raise ConfigInvalida(
            "Chaves não permitidas no .env: " + ", ".join(desconhecidas)
            + ". Modelos e limiares ficam no lutz.yaml."
        )
    if not projeto.env.exists():
        projeto.env.write_text(ENV_EXEMPLO, encoding="utf-8")
    sombreadas = []
    for nome, valor in mudancas.items():
        if valor is None or valor == "":
            if nome in _arquivo(projeto):
                unset_key(str(projeto.env), nome)
        else:
            if "\n" in valor:
                raise ConfigInvalida(f"{nome} não pode ter quebra de linha.")
            set_key(str(projeto.env), nome, valor, quote_mode="always")
        if os.environ.get(nome):
            sombreadas.append(nome)
    return sombreadas
